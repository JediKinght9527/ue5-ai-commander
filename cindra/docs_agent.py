"""docs_agent —— CindraDocs 的 Claude agent (UE 问答 RAG 的 G)。

共享 loop/helper 在 base_agent.CindraAgent; 这里只声明 CindraDocs 特有的系统提示
和工具结果格式化。与 CindraChat 同构: agent 调 search_docs 读回真实片段再作答 ==
CindraChat 调 list_actors 自检, 都强制"基于真实证据"。
"""
from __future__ import annotations

import anthropic

from . import docs_tools
from .base_agent import CindraAgent, _json

MODEL = "claude-opus-4-8"

SYSTEM_PROMPT = """你是 CindraDocs —— 嵌在 UE5 编辑器里的 AI 文档问答助手。
用户问虚幻引擎 (UE5) 相关的问题, 你基于本地知识库检索到的内容作答。

工作方式 (retrieve before answer):
- 回答任何 UE 问题前, 先用 search_docs 检索相关片段 —— 不要凭记忆直接答。
- 复杂问题可拆成多次检索 (例如"Actor 和 Pawn 区别"可分别检索 Actor、Pawn)。
- 只依据检索到的片段作答。检索不到支撑时, 明说"知识库里没有相关内容", 不要编造
  UE 的类名、API 或行为。
- 答案末尾标注引用来源, 格式: [来源: 文件名#标题], 多个来源逗号分隔。

回答简洁、准确、像给同事讲清楚一个概念。"""


class CindraDocsAgent(CindraAgent):
    SYSTEM_PROMPT = SYSTEM_PROMPT
    TOOL_EMOJI = "🔎"

    def __init__(self, index, client: anthropic.Anthropic | None = None,
                 verbose: bool = True) -> None:
        super().__init__(index, docs_tools, client=client, verbose=verbose)

    def _fmt_result(self, r: dict) -> str:
        if not r.get("ok", True):
            return f"❌ {r.get('error')}"
        if r.get("action") == "search":
            hits = r.get("results", [])
            return f"{len(hits)} 片段: " + ", ".join(
                f"{h['file']}#{h['title']}" for h in hits)
        if r.get("action") == "list_topics":
            return f"{r.get('count')} 个主题文件"
        return _json({k: v for k, v in r.items() if k != "ok"})
