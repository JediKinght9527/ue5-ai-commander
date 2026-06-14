"""scene_tools —— Claude 的场景工具 schema + 工具调用 -> transport 派发。

把 Cindra "改场景" 能力暴露成几个 dedicated 工具 (而非一个 bash):
spawn / spawn_grid / delete / move / list / clear。dedicated 工具让我们能
对每步做校验、渲染、审计 —— agent-design.md 里 "promote to dedicated tool"
的理由。每个工具直接映射到引擎侧一个 cnd_*() 函数。
"""
from __future__ import annotations

from typing import Any

from .transport import Transport

CINDRA_ACTOR_PREFIX = "Cindra_"


def _actor_name(actor_type: str, explicit_name: str | None = None) -> str | None:
    if explicit_name:
        return explicit_name
    return f"{CINDRA_ACTOR_PREFIX}{actor_type.capitalize()}"

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
        "name": "set_transform",
        "description": "一次性设置一个 Actor 的位置/旋转/缩放 (任一可省)。需要让物体"
                       "旋转或缩放 (而不只是平移) 时用它, 比 move_actor 更全。",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "location": {"type": "array", "items": {"type": "number"},
                             "description": "[x,y,z] cm, 省略则不改位置"},
                "rotation": {"type": "array", "items": {"type": "number"},
                             "description": "[pitch,yaw,roll] 度, 省略则不改朝向"},
                "scale": {"type": "array", "items": {"type": "number"},
                          "description": "[x,y,z], 省略则不改缩放"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "arrange_scene",
        "description": "对整个场景(或某区域)做语义化批量变换 —— 一句话改变全场氛围, "
                       "而不用逐个 move。用户说'让这里像被地震砸过/把东西散乱开/全部倒下/"
                       "排整齐/向外炸开'这类整体效果时用它。它会读回当前所有 Actor, 按风格"
                       "给每个算一套新的位置+旋转+缩放并应用。",
        "input_schema": {
            "type": "object",
            "properties": {
                "style": {"type": "string",
                          "enum": ["earthquake", "scatter", "topple", "tidy",
                                   "explode"],
                          "description": "earthquake=震乱+倾斜; scatter=随机散开; "
                                         "topple=全部倒下; tidy=重排整齐网格; "
                                         "explode=从中心向外炸开"},
                "intensity": {"type": "number",
                              "description": "强度 0~1, 默认 0.6。越大位移/倾斜越夸张"},
                "prefix": {"type": "string",
                           "description": "可选, 只对名字以此前缀开头的 Actor 生效"},
            },
            "required": ["style"],
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


# ---- arrange_scene: 语义化批量变换 ----
# 设计要点: dispatch 不需要引擎"懂地震"。agent 调一次 arrange_scene, 我们读回
# 全场 Actor, 在 Python 里按风格算出每个的新 transform, 再逐个 cnd_set_transform。
# 纯编排现有原语, mock 上就能跑通、可确定性复现。

def _rand01(seed_str: str, salt: str) -> float:
    """基于 (名字, salt) 的稳定伪随机 [0,1)。用 md5 而非内置 hash, 不受
    PYTHONHASHSEED 影响 —— 保证同输入永远同输出 (自检要确定性)。"""
    import hashlib
    h = hashlib.md5(f"{seed_str}|{salt}".encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def _plan_transform(style, name, loc, intensity, center):
    """给一个 Actor 算新的 (location, rotation, scale)。返回的 dict 只含要改的键。"""
    k = intensity
    rx = _rand01(name, "x") * 2 - 1   # [-1,1]
    ry = _rand01(name, "y") * 2 - 1
    rz = _rand01(name, "z")
    ryaw = _rand01(name, "yaw") * 2 - 1
    x, y, z = loc[0], loc[1], loc[2]

    if style == "earthquake":
        # 小幅震乱 + 随机倾斜 + 少量下沉
        return {"location": [x + rx * 120 * k, y + ry * 120 * k,
                             max(0.0, z - rz * 40 * k)],
                "rotation": [(_rand01(name, "p") * 2 - 1) * 25 * k,
                             ryaw * 180,
                             (_rand01(name, "r") * 2 - 1) * 25 * k]}
    if style == "scatter":
        # 大幅随机平移, 不倾斜
        return {"location": [x + rx * 400 * k, y + ry * 400 * k, z]}
    if style == "topple":
        # 几乎全部放倒 (roll≈90), 随机朝向
        return {"location": [x, y, z],
                "rotation": [0, ryaw * 180, 90 * (0.6 + 0.4 * rz)]}
    if style == "explode":
        # 从场景中心向外推, 越远推得越多 + 抬升
        dx, dy = x - center[0], y - center[1]
        dist = max(1.0, (dx * dx + dy * dy) ** 0.5)
        push = 1.0 + 1.2 * k
        return {"location": [center[0] + dx / dist * (dist * push),
                             center[1] + dy / dist * (dist * push),
                             z + rz * 200 * k],
                "rotation": [(_rand01(name, "p") * 2 - 1) * 40 * k,
                             ryaw * 180,
                             (_rand01(name, "r") * 2 - 1) * 40 * k]}
    # tidy 在 dispatch 里单独处理 (要全局重排), 这里不该被调到
    return {}


def _arrange(transport, style, intensity, prefix):
    """读回全场 Actor → 按 style 算新 transform → 批量 cnd_set_transform。"""
    listed = transport.call("cnd_list")
    if not listed.get("ok", True):
        return {"ok": False, "error": listed.get("error", "list 失败")}
    actors = listed.get("actors", [])
    if prefix:
        actors = [a for a in actors if a["name"].startswith(prefix)]
    if not actors:
        return {"ok": False, "error": "场景里没有可变换的 Actor"
                + (f" (前缀 {prefix})" if prefix else "")}

    # 场景中心 (explode 用)
    xs = [a["location"][0] for a in actors]
    ys = [a["location"][1] for a in actors]
    center = [sum(xs) / len(xs), sum(ys) / len(ys)]

    changed = 0
    if style == "tidy":
        # 全局重排成整齐网格 (按名字排序保证确定)
        ordered = sorted(actors, key=lambda a: a["name"])
        for pos, a in zip(_grid_positions(len(ordered), 200, None,
                                          [center[0], center[1], 0]), ordered):
            r = transport.call("cnd_set_transform", name=a["name"],
                               location=pos, rotation=[0, 0, 0], scale=[1, 1, 1])
            if r.get("ok"):
                changed += 1
    else:
        for a in actors:
            plan = _plan_transform(style, a["name"], a["location"],
                                   intensity, center)
            r = transport.call("cnd_set_transform", name=a["name"], **plan)
            if r.get("ok"):
                changed += 1

    return {"ok": True, "action": "arrange_scene", "style": style,
            "total": len(actors), "changed": changed}



def dispatch(transport: Transport, name: str, args: dict[str, Any]) -> dict:
    """执行一个工具调用, 返回结果 dict (给 agent 当 tool_result)。"""
    if name == "spawn_actor":
        actor_type = args.get("actor_type", "cube")
        return transport.call(
            "cnd_spawn",
            actor_type=actor_type,
            name=_actor_name(actor_type, args.get("name")),
            location=args.get("location", [0, 0, 300]),
            rotation=args.get("rotation", [0, 0, 0]),
            scale=args.get("scale", [2, 2, 2]),
            folder=args.get("folder"),
            tags=args.get("tags"),
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
        for idx, pos in enumerate(_grid_positions(count, spacing, columns, origin), start=1):
            r = transport.call(
                "cnd_spawn",
                actor_type=atype,
                name=f"{CINDRA_ACTOR_PREFIX}{atype.capitalize()}_{idx:03d}",
                location=pos,
                scale=[1.5, 1.5, 1.5],
            )
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

    if name == "set_transform":
        kw = {"name": args["name"]}
        for key in ("location", "rotation", "scale"):
            if args.get(key) is not None:
                kw[key] = args[key]
        return transport.call("cnd_set_transform", **kw)

    if name == "arrange_scene":
        return _arrange(transport, args["style"],
                        float(args.get("intensity", 0.6)),
                        args.get("prefix"))

    if name == "list_actors":
        return transport.call("cnd_list")

    if name == "clear_scene":
        return transport.call("cnd_clear", prefix=args.get("prefix") or CINDRA_ACTOR_PREFIX)

    return {"ok": False, "error": f"unknown tool: {name}"}
