"""blueprint_tools —— CindraBlueprint 的 Claude 工具 schema + 派发。

对照 scene_tools.py。把"操控蓝图图"暴露成 dedicated 工具: 加节点、加变量、
连引脚、列图、删节点、清空。每个工具映射到 transport 的一个 bp_*()。

dedicated 工具的好处 (同 scene_tools): 每步可校验、可渲染、可审计。连线的
合法性校验在图模型/真 UE schema 里做, 工具层只负责派发并把结果回给 agent。
"""
from __future__ import annotations

from typing import Any

from .blueprint_model import node_templates

# 节点类型枚举从模板派生, 保证工具 schema 和模型一致。
_NODE_TYPES = list(node_templates().keys())

TOOLS: list[dict] = [
    {
        "name": "list_node_types",
        "description": "列出可用的蓝图节点类型及它们的引脚 (名字/方向/类别/类型)。"
                       "动手建图前先用它了解有哪些节点、各有哪些引脚, 才能正确连线。",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "add_node",
        "description": "在事件图里加一个节点。node_type 必须是 list_node_types 里的一种"
                       " (如 Event_BeginPlay/Branch/PrintString)。可给 name, 不给则自动命名。",
        "input_schema": {
            "type": "object",
            "properties": {
                "node_type": {"type": "string", "enum": _NODE_TYPES},
                "name": {"type": "string", "description": "可选节点 id"},
            },
            "required": ["node_type"],
        },
    },
    {
        "name": "add_variable",
        "description": "给蓝图加一个成员变量。",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "var_type": {"type": "string",
                             "enum": ["bool", "int", "float", "string", "object"],
                             "description": "默认 float"},
                "default": {"description": "可选默认值"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "connect_pins",
        "description": "连两个引脚, 必须从某节点的 output 引脚连到另一节点的 input 引脚。"
                       "执行流连 exec 引脚 (then/exec/True/False...), 数据连同类型的 data "
                       "引脚。引脚名见 list_node_types 或 list_graph。",
        "input_schema": {
            "type": "object",
            "properties": {
                "from_node": {"type": "string"},
                "from_pin": {"type": "string"},
                "to_node": {"type": "string"},
                "to_pin": {"type": "string"},
            },
            "required": ["from_node", "from_pin", "to_node", "to_pin"],
        },
    },
    {
        "name": "delete_node",
        "description": "按 id 删除一个节点 (连着它的线一并删除)。",
        "input_schema": {
            "type": "object",
            "properties": {"node_id": {"type": "string"}},
            "required": ["node_id"],
        },
    },
    {
        "name": "list_graph",
        "description": "列出当前图的所有节点、连线、变量。建图过程中和完成后用它读回真实"
                       "结构自检, 确认节点连对了 —— 不要'自信地以为连上了'。",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "clear_graph",
        "description": "清空整张图。破坏性操作, 调用前应向用户确认。",
        "input_schema": {"type": "object", "properties": {}},
    },
]


def dispatch(transport: Any, name: str, args: dict[str, Any]) -> dict:
    """执行一个工具调用, 返回结果 dict (给 agent 当 tool_result)。"""
    if name == "list_node_types":
        return {"ok": True, "action": "list_node_types",
                "node_types": node_templates()}

    if name == "add_node":
        return transport.call("bp_add_node",
                              node_type=args["node_type"],
                              name=args.get("name"))

    if name == "add_variable":
        return transport.call("bp_add_variable",
                              name=args["name"],
                              var_type=args.get("var_type", "float"),
                              default=args.get("default"))

    if name == "connect_pins":
        return transport.call("bp_connect",
                              from_node=args["from_node"],
                              from_pin=args["from_pin"],
                              to_node=args["to_node"],
                              to_pin=args["to_pin"])

    if name == "delete_node":
        return transport.call("bp_delete_node", node_id=args["node_id"])

    if name == "list_graph":
        return transport.call("bp_list")

    if name == "clear_graph":
        return transport.call("bp_clear")

    return {"ok": False, "error": f"unknown tool: {name}"}
