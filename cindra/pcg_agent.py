"""pcg_agent —— CindraPCG 的 Claude agent (自然语言操控 UE5.7 PCG 程序化生成)。

共享 loop/helper 在 base_agent.CindraAgent; 这里只声明 CindraPCG 独有的系统提示和
工具结果格式化。

UE 5.7 PCG 框架正式 production-ready。Cindra 的 PCG 定位: 不是问答 (那是官方 AI
Assistant 的"嘴"), 而是真正搭图、执行、看结果、自我修正的"手和眼"。

和 CindraChat 同构: 操作后用 inspect_pcg_result 亲眼看、run_pcg_graph 看数据,
连错了会报错、agent 据此换方案。

验证闭环 (act → observe → verify → correct):
- 图编辑操作 (add/connect/delete/set_param) 前后拍图快照 → pcg_verifier 对账图结构
- run_pcg_graph 执行后校验产出数据+场景快照 → 确保"工具返回 ok 但引擎没生效"的
  静默失败被抓
"""
from __future__ import annotations

import anthropic

from . import pcg_tools, pcg_verifier
from .base_agent import CindraAgent, _json
from .pcg_model import PCGGraph
from .scene_tools import TOOLS as _CHAT_TOOLS
from .verifier import MUTATING_TOOLS as _CHAT_MUTATING_TOOLS

MODEL = "claude-opus-4-8"

SYSTEM_PROMPT = """你是 CindraPCG —— 嵌在 UE5 编辑器里的 AI 程序化生成 (PCG) 助手。

UE 5.7 的 PCG 框架 (Procedural Content Generation) 正式 production-ready:
它能按规则自动生成植被、建筑、道路、粒子等 —— 不再需要一个一个手摆。你通过
提供的工具, 在 PCG 图里加节点、连引脚、设参数、跑图、看结果。

## 工作方式 (plan the PCG graph before executing)

先想清楚"用哪些数据源 → 怎么采样 → 怎么过滤/变换 → 最终要生成什么"。
这是经典的 PCG 管线: Input → Sampling → Filter/Transform → Spawn。

动手前用 list_pcg_node_types 了解可用节点: 输入 (landscape/volume/spline/actors)、
采样 (surface/volume/spline)、变换 (offset/rotate/scale/jitter/density_noise)、
过滤 (density/height/bounds/slope)、合并 (union/difference/intersection)、
终端 (static_mesh_spawner)。

用 add_pcg_node 加节点 → connect_pcg_pins 连线 → set_pcg_param 调参
→ run_pcg_graph 执行 → inspect_pcg_result 看效果。

连线规则: 只能 output->input, 类型必须兼容 (landscape->landscape input,
point_cloud->point_cloud input, volume->volume input, spline->spline input)。
连错会报错, 用 list_pcg_graph 自检。

## 验证闭环纪律

- 每次图编辑操作后, tools 会自动做图结构校验。如果结果里带 "VERIFY FAILED",
  说明节点/连线没真加进去 —— 不要复述失败, 看具体原因重新操作。
- run_pcg_graph 执行后被自动校验执行结果 (节点数一致? spawn 产出是否为零?)。
  校验失败时如实上报, 根据失败原因调整图或参数。
- 执行完成后必须用 inspect_pcg_result 亲眼看俯视图和统计 —— 统计数字对了
  不等于视觉效果对 (密度分布合理? 区域覆盖对不对?)。

## 参数调优策略

mock 端的关键尺寸单位是 cm (UE 风格)。density_noise 会给每个点赋予 [0,1] 之间的
密度值 (基于位置 hash), slope_filter 按阈值分类 (密度≥阈值 = 平坦)。
mock 里表面采样点的默认密度是 0.5 (无噪声时), 噪声后范围近似
[0.5-amplitude, 0.5+amplitude]。所以:
- landscape width/depth 至少 5000 (50m) 才能有足够采样点
- slope_filter 阈值应设在 [0.2, 0.5] 区间, 太低几乎不过滤, 太高全不过
- density_noise amplitude 默认 0.3 适中, 0.6 是极端

## 典型管线举例

"在地形上, 只在平坦区域长橡树, 斜坡不生成, 树干方向随机偏一点"
-> landscape_input -> surface_sampler -> density_noise (模拟坡度)
-> slope_filter -> transform_points (随机旋转+缩放)
-> static_mesh_spawner(mesh=Oak) -> run

回答简洁。做完用一段话说清你搭了什么管线、最终能在场景里生成什么、多少实例。"""


class CindraPCGAgent(CindraAgent):
    SYSTEM_PROMPT = SYSTEM_PROMPT

    def __init__(self, client: anthropic.Anthropic | None = None,
                 verbose: bool = True) -> None:
        self.pcg_graph = PCGGraph()
        super().__init__(self.pcg_graph, pcg_tools, client=client, verbose=verbose)

    # ═══════════════════════════════════════════════════════════
    # 验证闭环钩子
    # ═══════════════════════════════════════════════════════════

    def _pre_tool(self, name: str, args: dict):
        if name in pcg_verifier.MUTATING_PCG_TOOLS:
            return pcg_verifier.graph_snapshot(self.target)  # self.target = pcg_graph
        return None

    def _post_tool(self, name: str, args: dict, result: dict, ctx) -> dict:
        if name not in pcg_verifier.MUTATING_PCG_TOOLS:
            return result

        if name == "run_pcg_graph":
            # 执行校验: 产出数据的内部一致性
            ok, why = pcg_verifier.verify_execution(result, ctx)
            if not ok:
                return {**result, "ok": False,
                        "error": f"VERIFY FAILED: {why}",
                        "verify": {"ok": False, "why": why}}
            result["verify"] = {"ok": True, "why": why}
            return result

        # 图编辑校验: 结构 diff
        after_snapshot = pcg_verifier.graph_snapshot(self.target)
        ok, why = pcg_verifier.verify_graph_edit(name, args, result, ctx, after_snapshot)
        if not ok:
            return {**result, "ok": False,
                    "error": f"VERIFY FAILED: {why}",
                    "verify": {"ok": False, "why": why}}
        result["verify"] = {"ok": True, "why": why}
        return result

    def _fmt_result(self, r: dict) -> str:
        if not r.get("ok", True):
            return f"❌ {r.get('error')}"
        action = r.get("action", "")
        if action == "list_pcg_node_types":
            return f"{len(r.get('node_types', {}))} 种 PCG 节点"
        if action == "add_pcg_node":
            return f"节点 {r['id']} ({r['type']}): {', '.join(r.get('pins', []))}"
        if action == "connect":
            return r.get("link", "connected")
        if action == "set_param":
            return f"{r['node']}.{r['param']} = {r['value']}"
        if action == "list_pcg_graph":
            return f"{len(r.get('nodes', []))} 节点, {len(r.get('links', []))} 连线"
        if action == "execute_pcg_graph":
            outs = r.get("outputs", [])
            lines = [f"执行 {r['node_count']} 节点", f"序: {r['exec_order']}"]
            for o in outs:
                s = o.get("stats", {})
                lines.append(f"  {o['node_id']}({o['node_type']}): {s.get('count', 0)} 点")
            # 附验证结果
            v = r.get("verify", {})
            if v:
                prefix = "✓" if v.get("ok") else "✗"
                lines.append(f"  {prefix} {v.get('why', '')}")
            return "; ".join(lines)
        if action == "inspect_pcg_result":
            return "俯视图+统计已回喂"
        return _json({k: v for k, v in r.items() if k != "ok"})
