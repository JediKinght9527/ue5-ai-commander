"""code_tools —— CindraCode 的 Claude 工具 schema + 工具调用 -> project_index 派发。

对照 docs_tools.py。把"查工程已有符号/约定"暴露成工具喂给 agent, 让它生成
UE C++ 前先了解本工程: 已有哪些类、命名前缀、组件/委托怎么用 —— 产出符合
现有规范的代码, 而不是凭空写一套不搭调的。这正是 Cindra"项目索引器当上下文"
的护城河。

  search_project(query, k)  -> index.search   找相关已有符号
  list_symbols()            -> 列全部符号      看工程全貌/命名约定
"""
from __future__ import annotations

from typing import Any

TOOLS: list[dict] = [
    {
        "name": "search_project",
        "description": "在当前 UE C++ 工程里检索已有符号 (类/结构体/枚举及其父类、"
                       "UFUNCTION/UPROPERTY 成员)。在生成或修改任何 C++ 前先用它了解"
                       "工程已有什么、命名和写法约定如何, 让产出与现有代码一致。可多次"
                       "检索不同方面 (如先查角色基类, 再查生命值组件)。",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string",
                          "description": "检索词或自然语言, 如'生命值组件'/'character 基类'"},
                "k": {"type": "integer", "description": "返回符号数, 默认 5"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "list_symbols",
        "description": "列出工程里所有已索引符号 (名字、种类、父类、所在文件)。想先看"
                       "工程整体结构和命名约定时用。",
        "input_schema": {"type": "object", "properties": {}},
    },
]


def dispatch(index: Any, name: str, args: dict[str, Any]) -> dict:
    """执行一个工具调用, 返回结果 dict (给 agent 当 tool_result)。"""
    if name == "search_project":
        query = args.get("query", "")
        if not query.strip():
            return {"ok": False, "error": "query 不能为空"}
        k = max(1, min(int(args.get("k", 5) or 5), 10))
        try:
            hits = index.search(query, k=k)
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}
        return {"ok": True, "action": "search_project", "query": query,
                "count": len(hits), "results": hits}

    if name == "list_symbols":
        syms = getattr(index, "symbols", [])
        out = [{"name": s["name"], "kind": s["kind"],
                "parent": s["parent"], "file": s["file"]} for s in syms]
        return {"ok": True, "action": "list_symbols",
                "count": len(out), "symbols": out}

    return {"ok": False, "error": f"unknown tool: {name}"}
