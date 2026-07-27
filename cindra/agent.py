"""agent —— CindraChat 的 agent (改场景)。

共享的 loop/helper 在 base_agent.CindraAgent; 这里只声明 CindraChat 特有的
系统提示和工具结果格式化。

v2: agent 长眼睛了 —— look_at_scene 返回真实截图 (mock 渲染 / 真 UE 视口),
提示词要求"造完必看、看完必评、不对就修"; 截图次数在代码层封顶 (base_agent
的 PER_SEND_TOOL_LIMITS), 不靠提示词自觉。
"""
from __future__ import annotations

from typing import Any

from . import scene_tools
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

视觉闭环 (你有眼睛, 用它):
- 搭建或大改场景后: 先 frame_scene 摆好相机, 再 look_at_scene 真正看一眼。
- 对照用户的要求批判画面: 布局对不对、比例协调吗、有没有物体穿插/漂浮/挤成一团。
- 看到问题就修, 修完再看。最多 3 轮 look-fix, 之后基于现状收尾并如实汇报。
- 文字状态 (list_actors) 和画面不一致时, 以画面为准。

回答简洁。做完一件事用一两句话说清你做了什么、画面里实际看到什么。"""


class CindraChatAgent(CindraAgent):
    SYSTEM_PROMPT = SYSTEM_PROMPT
    # 视觉闭环封顶: 单轮最多 5 张截图 (提示词说 3 轮, 代码留点余量)
    PER_SEND_TOOL_LIMITS = {"look_at_scene": 5}

    def __init__(self, transport: Transport,
                 client: Any | None = None,
                 verbose: bool = True,
                 asset_index: Any | None = None) -> None:
        ctx = ChatContext(transport=transport, asset_index=asset_index)
        super().__init__(ctx, scene_tools, client=client, verbose=verbose)
        self.transport = transport  # 供 CLI/session 直接访问

    def _fmt_result(self, r: dict) -> str:
        if not r.get("ok", True):
            return f"❌ {r.get('error')}"
        if r.get("action") == "list":
            return f"{len(r.get('actors', []))} actors"
        if r.get("action") == "spawn_grid":
            return f"生成 {r.get('count')} 个 {r.get('type')}"
        if r.get("action") == "screenshot":
            return f"📷 {r.get('path')}"
        if r.get("action") == "search_assets":
            hits = r.get("hits", [])
            return f"{len(hits)} 个资产: " + ", ".join(h["name"] for h in hits[:4])
        return _json({k: v for k, v in r.items() if k != "ok"})
