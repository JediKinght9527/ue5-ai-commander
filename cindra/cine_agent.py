"""cine_agent —— CindraCine 的 agent (文字生成运镜)。

共享 loop 在 base_agent; 这里是镜头语言的系统提示 + 审片闭环。
"""

from __future__ import annotations

from typing import Any

from . import cine_tools
from .base_agent import CindraAgent, _json

SYSTEM_PROMPT = """你是 CindraCine —— UE5 里的 AI 摄影指导。
用户描述想要的镜头, 你用工具建序列、摆相机、写运镜、渲染成片。

工作方式:
- 先 list_actors 了解场景里有什么、算出主体的中心和尺度, 再决定运镜参数。
- 标准流程: create_sequence -> add_cinematic_camera -> camera_move -> render_sequence。
- 运镜用预设表达意图: orbit(环绕揭示) / dolly(推近拉远) / crane(升降扫过) /
  flyover(飞掠全景) / static(定机位)。距离取主体半径的 1.5~2.5 倍, 太近会穿模。
- 多机位剪辑才需要 add_camera_cut; 单相机默认整段。

审片闭环 (你能看到渲染结果, 认真看):
- render_sequence 返回首/中/末 3 帧。逐帧审: 主体在画面里吗? 构图舒服吗?
  有没有穿模/黑屏/只拍到天空地板?
- 不满意就改 (调 distance/pitch/height 重新 camera_move 再渲), 最多 2 轮,
  之后基于现状收尾并如实说明遗留问题。
- 需要细看中间帧用 review_render。

回答简洁: 说清建了什么镜头、画面实际什么样。"""


class CindraCineAgent(CindraAgent):
    SYSTEM_PROMPT = SYSTEM_PROMPT
    TOOL_EMOJI = "🎬"
    PER_SEND_TOOL_LIMITS = {"render_sequence": 3, "review_render": 4}

    def __init__(self, transport, client: Any | None = None, verbose: bool = True) -> None:
        super().__init__(transport, cine_tools, client=client, verbose=verbose)
        self.transport = transport

    def _fmt_result(self, r: dict) -> str:
        if not r.get("ok", True):
            return f"❌ {r.get('error')}"
        if r.get("action") == "seq_render":
            n = r.get("frames_rendered") or len(r.get("frames", []))
            return f"🎞 {n} 帧 -> {r.get('out_dir')}"
        if r.get("action") == "seq_add_keys":
            return f"关键帧 x{r.get('total_keys')}"
        return _json({k: v for k, v in r.items() if k not in ("ok", "images")})
