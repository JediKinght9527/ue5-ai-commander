"""scene_tools —— Claude 的场景工具 schema + 工具调用 -> transport 派发。

把 Cindra "改场景" 能力暴露成几个 dedicated 工具 (而非一个 bash):
spawn / spawn_grid / delete / move / list / clear。dedicated 工具让我们能
对每步做校验、渲染、审计 —— agent-design.md 里 "promote to dedicated tool"
的理由。每个工具直接映射到引擎侧一个 cnd_*() 函数。
"""
from __future__ import annotations

from typing import Any

from .transport import Transport

# Claude tool 定义 (JSON schema)。描述里写清"何时用", 对新 Opus 触发率有提升。
TOOLS: list[dict] = [
    {
        "name": "spawn_actor",
        "description": "在场景里生成一个基础形状 Actor (cube/sphere/cylinder/cone/plane)。"
                       "用户说'放一个箱子/球'时调用。可指定名字、坐标、旋转、缩放。",
        "input_schema": {
            "type": "object",
            "properties": {
                "actor_type": {"type": "string",
                               "enum": ["cube", "sphere", "cylinder", "cone", "plane"]},
                "name": {"type": "string", "description": "可选, 不给则自动命名"},
                "location": {"type": "array", "items": {"type": "number"},
                             "description": "[x, y, z], UE 单位 cm。默认 [0,0,0]"},
                "rotation": {"type": "array", "items": {"type": "number"},
                             "description": "[pitch, yaw, roll] 度。默认 [0,0,0]"},
                "scale": {"type": "array", "items": {"type": "number"},
                          "description": "[x, y, z]。默认 [1,1,1]"},
            },
            "required": ["actor_type"],
        },
    },
    {
        "name": "spawn_grid",
        "description": "批量生成 N 个同形状 Actor, 排成网格。用户说'生成 10 个 cube'"
                       "这类批量需求时用这个, 比逐个 spawn 高效。",
        "input_schema": {
            "type": "object",
            "properties": {
                "actor_type": {"type": "string",
                               "enum": ["cube", "sphere", "cylinder", "cone", "plane"]},
                "count": {"type": "integer", "description": "总数量"},
                "spacing": {"type": "number", "description": "间距 cm, 默认 200"},
                "columns": {"type": "integer", "description": "每行几个, 默认自动接近正方"},
                "origin": {"type": "array", "items": {"type": "number"},
                           "description": "网格左上角 [x,y,z], 默认 [0,0,0]"},
            },
            "required": ["actor_type", "count"],
        },
    },
    {
        "name": "delete_actor",
        "description": "按名字删除一个 Actor。",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
    {
        "name": "move_actor",
        "description": "把一个 Actor 移到新坐标。",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "location": {"type": "array", "items": {"type": "number"}},
            },
            "required": ["name", "location"],
        },
    },
    {
        "name": "list_actors",
        "description": "列出场景里所有 Actor 及坐标。做完操作后用它读回状态自检, "
                       "或用户问'现在场景里有什么'时调用。",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "clear_scene",
        "description": "清空场景里所有 StaticMesh Actor。可选 prefix 只清某前缀的。"
                       "破坏性操作, 调用前应向用户确认。",
        "input_schema": {
            "type": "object",
            "properties": {"prefix": {"type": "string"}},
        },
    },
]


def _grid_positions(count, spacing, columns, origin):
    if not columns or columns < 1:
        columns = max(1, int(round(count ** 0.5)))
    origin = list(origin or []) + [0, 0, 0]  # 补齐到至少 3 个
    ox, oy, oz = float(origin[0]), float(origin[1]), float(origin[2])
    for i in range(count):
        r, c = divmod(i, columns)
        yield [ox + c * spacing, oy + r * spacing, oz]


def dispatch(transport: Transport, name: str, args: dict[str, Any]) -> dict:
    """执行一个工具调用, 返回结果 dict (给 agent 当 tool_result)。"""
    if name == "spawn_actor":
        return transport.call(
            "cnd_spawn",
            actor_type=args.get("actor_type", "cube"),
            name=args.get("name"),
            location=args.get("location", [0, 0, 0]),
            rotation=args.get("rotation", [0, 0, 0]),
            scale=args.get("scale", [1, 1, 1]),
        )

    if name == "spawn_grid":
        count = int(args["count"])
        if count > 500:
            return {"ok": False, "error": "数量上限 500, 防止误操作刷爆场景。"}
        spacing = float(args.get("spacing", 200))
        columns = args.get("columns")
        origin = args.get("origin", [0, 0, 0])
        atype = args.get("actor_type", "cube")
        spawned = []
        for pos in _grid_positions(count, spacing, columns, origin):
            r = transport.call("cnd_spawn", actor_type=atype, location=pos)
            if r.get("ok"):
                spawned.append(r["name"])
            else:
                return {"ok": False, "error": r.get("error"), "spawned": spawned}
        return {"ok": True, "action": "spawn_grid", "type": atype,
                "count": len(spawned), "names": spawned}

    if name == "delete_actor":
        return transport.call("cnd_delete", name=args["name"])

    if name == "move_actor":
        return transport.call("cnd_move", name=args["name"],
                              location=args["location"])

    if name == "list_actors":
        return transport.call("cnd_list")

    if name == "clear_scene":
        return transport.call("cnd_clear", prefix=args.get("prefix"))

    return {"ok": False, "error": f"unknown tool: {name}"}
