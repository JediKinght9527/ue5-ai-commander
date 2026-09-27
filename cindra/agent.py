"""agent —— CindraChat 的 agent (改场景)。

共享的 loop/helper 在 base_agent.CindraAgent; 这里只声明 CindraChat 特有的
系统提示和工具结果格式化。

v2: agent 长眼睛了 —— look_at_scene 返回真实截图 (mock 渲染 / 真 UE 视口),
提示词要求"造完必看、看完必评、不对就修"; 截图次数在代码层封顶 (base_agent
的 PER_SEND_TOOL_LIMITS), 不靠提示词自觉。
"""

from __future__ import annotations

from typing import Any

from . import scene_tools, verifier
from .base_agent import CindraAgent, _json
from .scene_tools import ChatContext
from .transport import Transport

MODEL = "claude-opus-4-8"

SYSTEM_PROMPT = """你是 CindraChat —— 嵌在 UE5 编辑器里的 AI 关卡助手。
用户用自然语言描述想要的场景, 你用提供的工具去真正操控引擎实现它。

工作方式 (analyze before acting):
- 动手前先想清楚要哪些步骤, 把复杂请求拆成具体的工具调用。
- 想放真东西 (箱子/石头/树/墙) 先 search_assets 找真实资产, 再 spawn_asset;
  基础几何体 (spawn_actor/spawn_grid) 只用于 blockout 或用户明确要几何体时。
- asset path 必须来自 search_assets 结果, 不要凭空编造路径。
- 批量同形状物体用 spawn_grid, 不要逐个 spawn。
- 整体氛围/语义化效果 (地震、散乱、全部倒下、排整齐、向外炸开) 用 arrange_scene 一步完成,
  不要逐个 move/set_transform —— 它会读回全场再批量变换。
- 要让物体旋转或缩放 (不只是平移) 用 set_transform。
- 坐标用 UE 单位 (厘米); 场景中心约 [0,0,0]。
- 破坏性操作 (clear_scene) 前先向用户确认。

验证闭环 (act → observe → verify → correct):
- 每次改场景的工具调用都会被自动硬校验 (前后快照对账), 结果附在 verify 字段里。
  如果工具结果带 "VERIFY FAILED", 说明操作没真正生效或效果不符 —— 不要复述失败,
  根据失败原因换方案重试; 连续失败 2 次就 undo 回退并如实告诉用户卡在哪。
- 完成一组改动后调用 inspect_viewport 亲眼确认 (mock 是 ASCII 俯视图, 真 UE 是
  视口截图)。看到的效果和用户要求不符时, 主动修正后再看一次, 直到符合。
- 改坏了用 undo 回退, 撤销后确认回退结果。
- 不要"自信地以为成了" —— 只有校验通过 + 亲眼看过才算完成。

回答简洁。做完一件事用一两句话说清你做了什么、验证结果如何。"""


class CindraChatAgent(CindraAgent):
    SYSTEM_PROMPT = SYSTEM_PROMPT
    # 视觉闭环封顶: 单轮最多 5 张截图 (提示词说 3 轮, 代码留点余量)
    PER_SEND_TOOL_LIMITS = {"look_at_scene": 5}

    def __init__(
        self,
        transport: Transport,
        client: Any | None = None,
        verbose: bool = True,
        asset_index: Any | None = None,
    ) -> None:
        ctx = ChatContext(transport=transport, asset_index=asset_index)
        super().__init__(ctx, scene_tools, client=client, verbose=verbose)
        self.transport = transport  # 供 CLI/session 直接访问

    # ---- 验证闭环: 改动前后拍快照, 用 verifier 对账 (见 verifier.py) ----

    def _pre_tool(self, name: str, args: dict):
        if name in verifier.MUTATING_TOOLS:
            return verifier.take_snapshot(self.target)
        return None

    def _post_tool(self, name: str, args: dict, result: dict, ctx) -> dict:
        if name not in verifier.MUTATING_TOOLS:
            return result
        after = verifier.take_snapshot(self.target)
        ok, why = verifier.verify(name, args, result, ctx, after)
        if not ok:
            # 校验覆盖工具自报的 ok —— 失败证据回喂, 让 agent 自己决定
            # 重试/换方案/undo, 而不是在这里写死修正策略。
            return {
                **result,
                "ok": False,
                "error": f"VERIFY FAILED: {why}",
                "verify": {"ok": False, "why": why},
            }
        result["verify"] = {"ok": True, "why": why}
        return result

    def _fmt_result(self, r: dict) -> str:
        if not r.get("ok", True):
            return f"❌ {r.get('error')}"
        v = r.get("verify", {})
        tick = f"  ✓ {v['why']}" if v.get("ok") else ""
        if r.get("action") == "list":
            return f"{len(r.get('actors', []))} actors"
        if r.get("action") == "viewport":
            return "截图已回喂" if r.get("_image_path") else "俯视图已回喂"
        if r.get("action") == "spawn_grid":
            return f"生成 {r.get('count')} 个 {r.get('type')}{tick}"
        return _json({k: v for k, v in r.items() if k not in ("ok", "verify")}) + tick
