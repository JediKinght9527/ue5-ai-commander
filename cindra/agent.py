"""agent —— CindraChat 的 Claude agent (改场景)。

共享的 loop/helper 在 base_agent.CindraAgent; 这里只声明 CindraChat 特有的
系统提示和工具结果格式化。
"""
from __future__ import annotations

import anthropic

from . import scene_tools
from .base_agent import CindraAgent, _json
from .transport import Transport

MODEL = "claude-opus-4-8"

SYSTEM_PROMPT = """你是 CindraChat —— 嵌在 UE5 编辑器里的 AI 关卡助手。
用户用自然语言描述想要的场景, 你用提供的工具去真正操控引擎实现它。

工作方式 (analyze before acting):
- 动手前先想清楚要哪些步骤, 把复杂请求拆成具体的工具调用。
- 批量同形状物体用 spawn_grid, 不要逐个 spawn。
- 坐标用 UE 单位 (厘米); 场景中心约 [0,0,0]。
- 破坏性操作 (clear_scene) 前先向用户确认。
- 关键步骤做完后, 可以用 list_actors 读回状态确认成功 —— 不要"自信地以为成了"。

回答简洁。做完一件事用一两句话说清你做了什么。"""


class CindraChatAgent(CindraAgent):
    SYSTEM_PROMPT = SYSTEM_PROMPT

    def __init__(self, transport: Transport,
                 client: anthropic.Anthropic | None = None,
                 verbose: bool = True) -> None:
        super().__init__(transport, scene_tools, client=client, verbose=verbose)

    def _fmt_result(self, r: dict) -> str:
        if not r.get("ok", True):
            return f"❌ {r.get('error')}"
        if r.get("action") == "list":
            return f"{len(r.get('actors', []))} actors"
        if r.get("action") == "spawn_grid":
            return f"生成 {r.get('count')} 个 {r.get('type')}"
        return _json({k: v for k, v in r.items() if k != "ok"})
