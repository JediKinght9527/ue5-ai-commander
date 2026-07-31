"""pcg_tools —— CindraPCG 的 Claude 工具 schema + 派发。

把"操控 PCG 图"暴露成 dedicated 工具: 加节点、连引脚、设参数、删节点、
运行图、看结果、清空。每个工具映射到 PCGGraph 的一个方法。

和 scene_tools/blueprint_tools 同构: mock 端在 Mac 上离线验证逻辑,
真 UE 端走 ue_pcg_helper (Remote Execution → 引擎内 PCG 图 API)。
"""
from __future__ import annotations

from typing import Any

from .pcg_model import NODE_TEMPLATES, PCGGraph

# 工具定义
TOOLS: list[dict] = [
    {
        "name": "list_pcg_node_types",
        "description": "列出可用的 PCG 节点类型及它们的引脚 (输入/输出名字+类型)和参数。"
                       "建图前用它了解有哪些节点、各需要什么输入、产出什么输出。",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "add_pcg_node",
        "description": "在 PCG 图中加一个节点。node_type 必须是 list_pcg_node_types 里的一种。"
                       "可通过 params 字典传参数 (如 points_per_sqm/seed/mesh_path 等)。"
                       "不给 name 则自动命名。",
        "input_schema": {
            "type": "object",
            "properties": {
                "node_type": {"type": "string",
                              "enum": list(NODE_TEMPLATES.keys())},
                "name": {"type": "string", "description": "可选节点 id"},
                "params": {"type": "object", "description": "可选参数字典, 只传要覆盖的值"},
            },
            "required": ["node_type"],
        },
    },
    {
        "name": "connect_pcg_pins",
        "description": "连两个 PCG 图引脚。从输出节点(out)的输出引脚连到输入节点(in)的输入引脚。"
                       "引脚名见 list_pcg_node_types。必须方向正确且类型兼容 (point_cloud→point_cloud 等)。",
        "input_schema": {
            "type": "object",
            "properties": {
                "from_node": {"type": "string"},
                "from_pin":  {"type": "string"},
                "to_node":   {"type": "string"},
                "to_pin":    {"type": "string"},
            },
            "required": ["from_node", "from_pin", "to_node", "to_pin"],
        },
    },
    {
        "name": "set_pcg_param",
        "description": "修改一个 PCG 节点的参数值 (如调整撒点密度/种子/过滤阈值)。",
        "input_schema": {
            "type": "object",
            "properties": {
                "node_id": {"type": "string"},
                "param":   {"type": "string"},
                "value":   {"description": "新值; number/string/array"},
            },
            "required": ["node_id", "param", "value"],
        },
    },
    {
        "name": "delete_pcg_node",
        "description": "删除一个 PCG 图节点 (连着它的连线一并删除)。",
        "input_schema": {
            "type": "object",
            "properties": {"node_id": {"type": "string"}},
            "required": ["node_id"],
        },
    },
    {
        "name": "list_pcg_graph",
        "description": "列出当前 PCG 图的节点、类型、参数、引脚连接。建图过程中用来自检: "
                       "节点加对了没、连线对不对。",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "run_pcg_graph",
        "description": "执行当前 PCG 图。根据拓扑序跑完所有节点, 返回每个输出节点的统计。"
                       "spawn 类节点不会真的在场景里放东西 (那是真 UE 后端的事), "
                       "但 mock 会算好所有 spawn 点的位置、密度、旋转、缩放, "
                       "可用 inspect_pcg_result 以 ASCII 俯视图查看。",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "inspect_pcg_result",
        "description": "查看 PCG 图执行后的结果: ASCII 俯视图 + 各输出节点的统计摘要。"
                       "和 CindraChat 的 inspect_viewport 同思路 —— agent 亲眼看效果。"
                       "如果想看具体哪些点的数据, 用 list_pcg_graph 看各节点缓存。",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "clear_pcg_graph",
        "description": "清空整张 PCG 图。破坏性操作, 调用前向用户确认。",
        "input_schema": {"type": "object", "properties": {}},
    },
]


def dispatch(graph: PCGGraph, name: str, args: dict[str, Any]) -> dict:
    """执行一个 PCG 工具调用, 返回结果 dict。"""
    if name == "list_pcg_node_types":
        types = {}
        for tname, tmpl in NODE_TEMPLATES.items():
            types[tname] = {
                "cls": tmpl.get("cls", ""),
                "description": tmpl["description"],
                "inputs": [f"{p[0]}({p[1]})" for p in tmpl["inputs"]],
                "outputs": [f"{p[0]}({p[1]})" for p in tmpl["outputs"]],
                "params": {pn: {"type": pi["type"], "desc": pi.get("desc", pi["type"])}
                           for pn, pi in tmpl["params"].items()},
            }
        return {"ok": True, "action": "list_pcg_node_types",
                "node_types": types}

    if name == "add_pcg_node":
        return graph.add_node(
            node_type=args["node_type"],
            name=args.get("name"),
            params=args.get("params"),
        )

    if name == "connect_pcg_pins":
        return graph.connect(
            from_node=args["from_node"], from_pin=args["from_pin"],
            to_node=args["to_node"], to_pin=args["to_pin"],
        )

    if name == "set_pcg_param":
        return graph.set_param(
            node_id=args["node_id"], param=args["param"],
            value=args["value"],
        )

    if name == "delete_pcg_node":
        return graph.delete_node(node_id=args["node_id"])

    if name == "list_pcg_graph":
        return graph.list_graph()

    if name == "run_pcg_graph":
        return graph.execute()

    if name == "inspect_pcg_result":
        viz = graph.render()
        stats = graph.render_stats()
        return {"ok": True, "action": "inspect_pcg_result",
                "view": viz, "stats": stats}

    if name == "clear_pcg_graph":
        return graph.clear()

    return {"ok": False, "error": f"unknown tool: {name}"}
