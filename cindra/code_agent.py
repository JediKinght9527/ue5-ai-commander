"""code_agent —— CindraCode 的 agent (生成符合工程规范的 UE C++)。

共享 loop/helper 在 base_agent.CindraAgent; 这里只声明 CindraCode 特有的系统提示
和工具结果格式化。护城河: 生成前先 search_project 了解工程已有的类/命名/约定。
"""
from __future__ import annotations

from typing import Any

from . import code_tools
from .base_agent import CindraAgent, _json

MODEL = "claude-opus-4-8"

SYSTEM_PROMPT = """你是 CindraCode —— 嵌在 UE5 编辑器里的 AI C++ 助手。
用户用自然语言描述要实现的功能, 你为当前 UE5 工程生成符合规范的 C++ 代码。

工作方式 (study the project before writing):
- 写任何代码前, 先用 search_project / list_symbols 了解工程: 已有哪些类、它们的
  父类和成员、命名前缀 (如本工程业务类用 'Cindra' 前缀 + UE 的 A/U/F 约定)、
  组件和委托怎么组织。复用已有的类型, 别重复造。
- 生成的代码要符合 UE 规范: 正确的 UCLASS/USTRUCT/UFUNCTION/UPROPERTY 宏和
  说明符; 指向 UObject 的成员指针必须加 UPROPERTY (否则被 GC 回收); 头文件配
  .generated.h; 性能敏感处避免无谓 Tick; 可调数值用 EditAnywhere 暴露。
- 优先给出 .h 和 .cpp 两部分, 用代码块包裹, 标清文件名。
- 解释要简洁: 说清楚你基于工程里的哪些已有约定/类型做的决定。

如果工程里查不到相关上下文, 明说你按 UE 通用规范生成, 不要假装工程里有不存在的类。"""


class CindraCodeAgent(CindraAgent):
    SYSTEM_PROMPT = SYSTEM_PROMPT
    TOOL_EMOJI = "🔎"

    def __init__(self, index, client: Any | None = None,
                 verbose: bool = True) -> None:
        super().__init__(index, code_tools, client=client, verbose=verbose)

    def _fmt_result(self, r: dict) -> str:
        if not r.get("ok", True):
            return f"❌ {r.get('error')}"
        if r.get("action") == "search_project":
            hits = r.get("results", [])
            return f"{len(hits)} 符号: " + ", ".join(h["title"] for h in hits)
        if r.get("action") == "list_symbols":
            return f"{r.get('count')} 个符号"
        return _json({k: v for k, v in r.items() if k != "ok"})
