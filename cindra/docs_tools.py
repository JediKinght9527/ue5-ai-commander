"""docs_tools —— CindraDocs 的 Claude 工具 schema + 工具调用 -> index 派发。

对照 scene_tools.py: 把"检索 UE 知识库"暴露成 dedicated 工具喂给 agent。
检索做成工具 (而非把所有文档塞进 system prompt), 让 agent 按需取片段、
按来源引用, 也能在一次回答里多次检索不同子问题。

  search_docs(query, k)  -> index.search    (对照 scene_tools 的具体操作工具)
  list_topics()          -> 列知识库主题    (对照 list_actors 的"读回状态")
"""

from __future__ import annotations

from typing import Any

# index 后端: 任何暴露 .search(query, k) 的对象 (LexicalIndex / EmbeddingIndex)。
# 这里只依赖那个接口, 不关心底下是关键词还是向量。

TOOLS: list[dict] = [
    {
        "name": "search_docs",
        "description": "在本地 UE5 知识库里检索, 返回最相关的若干文档片段 (带标题和"
        "来源文件)。回答任何 UE/虚幻引擎相关问题前都应先用它取证据, "
        "再根据检索到的片段作答, 不要凭记忆编造 API。一个复杂问题可拆成"
        "多次检索不同子问题。",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "检索关键词或自然语言问题"},
                "k": {"type": "integer", "description": "返回片段数, 默认 4"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "list_topics",
        "description": "列出知识库里有哪些主题 (每个文件的标题)。用户问'你都懂些什么/"
        "知识库覆盖哪些主题'时用, 或你想先看全貌再决定检索什么时用。",
        "input_schema": {"type": "object", "properties": {}},
    },
]


def dispatch(index: Any, name: str, args: dict[str, Any]) -> dict:
    """执行一个工具调用, 返回结果 dict (给 agent 当 tool_result)。"""
    if name == "search_docs":
        query = args.get("query", "")
        if not query.strip():
            return {"ok": False, "error": "query 不能为空"}
        k = int(args.get("k", 4) or 4)
        k = max(1, min(k, 10))
        try:
            hits = index.search(query, k=k)
        except Exception as e:  # noqa: BLE001 - 把错误回给 agent
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}
        return {"ok": True, "action": "search", "query": query, "count": len(hits), "results": hits}

    if name == "list_topics":
        # 从 index 的 chunks 里汇总每个文件的标题
        chunks = getattr(index, "chunks", [])
        topics: dict[str, list[str]] = {}
        for c in chunks:
            topics.setdefault(c["file"], []).append(c["title"])
        out = [{"file": f, "titles": ts} for f, ts in topics.items()]
        return {"ok": True, "action": "list_topics", "count": len(out), "topics": out}

    return {"ok": False, "error": f"unknown tool: {name}"}
