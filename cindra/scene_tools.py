"""scene_tools —— Claude 的场景工具 schema + 工具调用 -> transport 派发。

把 Cindra "改场景" 能力暴露成几个 dedicated 工具 (而非一个 bash):
spawn / spawn_grid / delete / move / list / clear。dedicated 工具让我们能
对每步做校验、渲染、审计 —— agent-design.md 里 "promote to dedicated tool"
的理由。每个工具直接映射到引擎侧一个 cnd_*() 函数。
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any

from .transport import Transport

CINDRA_ACTOR_PREFIX = "Cindra_"


@dataclass
class ChatContext:
    """dispatch 的上下文: transport + 可选资产索引。

    向后兼容: dispatch 第一参也接受裸 transport (mock_ue 自检等旧调用方),
    此时资产检索按需懒加载 mock 清单。
    """
    transport: Transport
    asset_index: Any = None
    extras: dict = field(default_factory=dict)

    def ensure_asset_index(self):
        if self.asset_index is None:
            from .asset_index import load_asset_index
            self.asset_index = load_asset_index()
        return self.asset_index


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
        "name": "search_assets",
        "description": "用自然语言搜索工程里的真实资产 (mesh/材质/蓝图/PCG图)。"
                       "想放'木箱/石头/树'这类真东西时先用它拿到 asset path, "
                       "再 spawn_asset —— 别再用基础几何体凑合。",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "如 'wooden crate 木箱'"},
                "class_filter": {"type": "string",
                                 "enum": ["static_mesh", "material", "blueprint",
                                          "pcg_graph", "niagara", "any"],
                                 "description": "限定资产类型, 默认 any"},
                "k": {"type": "integer", "description": "返回条数, 默认 8"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "spawn_asset",
        "description": "按资产路径生成真实资产 Actor (StaticMesh/Blueprint)。"
                       "path 必须来自 search_assets 的结果, 不要凭空猜路径。"
                       "返回真实包围盒, 便于按尺寸摆位。",
        "input_schema": {
            "type": "object",
            "properties": {
                "asset_path": {"type": "string"},
                "name": {"type": "string", "description": "可选, 不给则自动命名"},
                "location": {"type": "array", "items": {"type": "number"}},
                "rotation": {"type": "array", "items": {"type": "number"}},
                "scale": {"type": "array", "items": {"type": "number"}},
            },
            "required": ["asset_path"],
        },
    },
    {
        "name": "set_material",
        "description": "给一个 Actor 换材质。material_path 来自 search_assets "
                       "(class_filter=material)。",
        "input_schema": {
            "type": "object",
            "properties": {
                "actor_name": {"type": "string"},
                "material_path": {"type": "string"},
                "slot": {"type": "integer", "description": "材质槽, 默认 0"},
            },
            "required": ["actor_name", "material_path"],
        },
    },
    {
        "name": "spawn_light",
        "description": "生成一盏灯 (point/spot/rect/directional)。单灯精调用它; "
                       "整体布光氛围 (恐怖/黄金时刻/摄影棚/霓虹夜/阴天) 用 light_rig "
                       "一步到位。",
        "input_schema": {
            "type": "object",
            "properties": {
                "light_type": {"type": "string",
                               "enum": ["point", "spot", "rect", "directional"]},
                "name": {"type": "string"},
                "location": {"type": "array", "items": {"type": "number"}},
                "rotation": {"type": "array", "items": {"type": "number"},
                             "description": "spot/directional 的照射朝向"},
                "intensity": {"type": "number", "description": "默认 5000"},
                "color": {"type": "array", "items": {"type": "number"},
                          "description": "[r,g,b] 0~1"},
                "temperature": {"type": "number",
                                "description": "开尔文色温 (设了会覆盖 color 的冷暖)"},
                "cone_angle": {"type": "number", "description": "spot 外锥角, 默认 44"},
            },
            "required": ["light_type"],
        },
    },
    {
        "name": "light_rig",
        "description": "一句话整套布光: 读回场景包围盒, 按风格生成一组灯 + 雾 + "
                       "后处理 + 太阳。用户说'恐怖氛围/黄金时刻/摄影棚打光/赛博霓虹夜/"
                       "阴天'这类整体光效时用它, 别逐盏摆。",
        "input_schema": {
            "type": "object",
            "properties": {
                "style": {"type": "string",
                          "enum": ["horror", "golden_hour", "studio",
                                   "night_neon", "overcast"]},
                "intensity": {"type": "number",
                              "description": "强度 0~1, 默认 0.6"},
                "prefix": {"type": "string",
                           "description": "可选, 只按此前缀的 Actor 算包围盒"},
            },
            "required": ["style"],
        },
    },
    {
        "name": "setup_environment",
        "description": "单独设置环境要素: 天空大气/高度雾/后处理体积/天光/太阳。"
                       "每类是单例, 重复设置会整体替换。",
        "input_schema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string",
                         "enum": ["sky_atmosphere", "exp_height_fog",
                                  "post_process", "sky_light", "sun"]},
                "params": {"type": "object",
                           "description": "按 kind: fog {density, height_falloff}; "
                                          "post_process {bloom_intensity, "
                                          "auto_exposure_bias, vignette_intensity, "
                                          "film_grain_intensity}; sun {rotation, "
                                          "intensity, temperature}"},
            },
            "required": ["kind"],
        },
    },
    {
        "name": "pcg_scatter",
        "description": "用 PCG 程序化填充一片区域 (森林/石滩/草地)。graph_path 来自 "
                       "search_assets (class_filter=pcg_graph)。生成是异步的, 之后用 "
                       "list_actors/look_at_scene 验证。",
        "input_schema": {
            "type": "object",
            "properties": {
                "graph_path": {"type": "string"},
                "origin": {"type": "array", "items": {"type": "number"}},
                "size": {"type": "array", "items": {"type": "number"},
                         "description": "[x, y, z] cm, 默认 [2000,2000,500]"},
                "name": {"type": "string"},
            },
            "required": ["graph_path"],
        },
    },
    {
        "name": "set_viewport_camera",
        "description": "移动编辑器视口相机。orbit 模式最常用: 给中心/距离/角度环绕摆位。"
                       "也可 location+look_at 或 location+rotation。",
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {"type": "array", "items": {"type": "number"}},
                "rotation": {"type": "array", "items": {"type": "number"},
                             "description": "[pitch, yaw, roll] 度"},
                "look_at": {"type": "array", "items": {"type": "number"},
                            "description": "看向的点 [x,y,z]"},
                "orbit": {"type": "object",
                          "properties": {
                              "center": {"type": "array",
                                         "items": {"type": "number"}},
                              "distance": {"type": "number"},
                              "yaw": {"type": "number"},
                              "pitch": {"type": "number"}}},
            },
        },
    },
    {
        "name": "frame_scene",
        "description": "自动把相机摆到能框住全场景 (或某前缀 Actor) 的位置。"
                       "look_at_scene 前先调它, 保证看得到全貌。",
        "input_schema": {
            "type": "object",
            "properties": {"prefix": {"type": "string"}},
        },
    },
    {
        "name": "look_at_scene",
        "description": "截一张当前视口的图, 你会真的看到画面。搭建/修改场景后必须"
                       "调用它检查实际效果: 布局是否符合要求、比例是否协调、有没有"
                       "穿插或漂浮。看到问题就修, 修完再看, 最多 3 轮。",
        "input_schema": {
            "type": "object",
            "properties": {
                "view": {"type": "string", "enum": ["camera", "topdown"],
                         "description": "camera=当前视口透视 (默认), "
                                        "topdown=俯视布局图"},
            },
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



def _wait_for_file(path: str, timeout: float = 15.0) -> bool:
    """等真 UE 侧的截图/渲染文件落盘 (存在且体积稳定两拍)。"""
    deadline = time.time() + timeout
    last_size = -1
    while time.time() < deadline:
        if os.path.isfile(path):
            size = os.path.getsize(path)
            if size > 0 and size == last_size:
                return True
            last_size = size
        time.sleep(0.3)
    return False


def _resolve_screenshot(result: dict) -> dict:
    """截图结果归一: mock 直接带 images; 真侧 pending -> 轮询文件再挂 images。"""
    if result.get("ok") and result.get("pending"):
        path = result.get("path", "")
        if path and _wait_for_file(path):
            result = dict(result)
            result.pop("pending", None)
            result["images"] = [path]
        else:
            result = {"ok": False,
                      "error": f"截图超时未落盘: {path} (viewport 是否可见?)"}
    return result


def dispatch(ctx, name: str, args: dict[str, Any]) -> dict:
    """执行一个工具调用, 返回结果 dict (给 agent 当 tool_result)。

    ctx: ChatContext 或裸 transport (向后兼容)。
    """
    transport: Transport = getattr(ctx, "transport", ctx)

    if name == "search_assets":
        index = (ctx.ensure_asset_index() if isinstance(ctx, ChatContext)
                 else ChatContext(transport).ensure_asset_index())
        cf = args.get("class_filter")
        hits = index.search(args["query"],
                            k=int(args.get("k", 8)),
                            class_filter=None if cf in (None, "any") else cf)
        if not hits:
            return {"ok": False,
                    "error": f"没搜到匹配 {args['query']!r} 的资产, 换个说法试试"}
        return {"ok": True, "action": "search_assets", "hits": hits}

    if name == "spawn_asset":
        return transport.call(
            "cnd_spawn_asset",
            asset_path=args["asset_path"],
            name=args.get("name"),
            location=args.get("location", [0, 0, 0]),
            rotation=args.get("rotation", [0, 0, 0]),
            scale=args.get("scale", [1, 1, 1]),
        )

    if name == "set_material":
        return transport.call("cnd_set_material",
                              name=args["actor_name"],
                              material_path=args["material_path"],
                              slot=int(args.get("slot", 0)))

    if name == "spawn_light":
        kw = {"light_type": args["light_type"]}
        for key in ("name", "location", "rotation", "intensity", "color",
                    "temperature", "cone_angle"):
            if args.get(key) is not None:
                kw[key] = args[key]
        return transport.call("cnd_spawn_light", **kw)

    if name == "light_rig":
        from .lighting_rigs import RIG_PREFIX, build_rig

        listed = transport.call("cnd_list")
        if not listed.get("ok", True):
            return {"ok": False, "error": listed.get("error", "list 失败")}
        actors = listed.get("actors", [])
        prefix = args.get("prefix")
        if prefix:
            actors = [a for a in actors if a["name"].startswith(prefix)]
        # 旧 rig 灯先清 (环境单例自己会替换), 保证换风格干净
        for a in actors:
            if a["name"].startswith(RIG_PREFIX):
                transport.call("cnd_delete", name=a["name"])
        actors = [a for a in actors if not a["name"].startswith(RIG_PREFIX)]
        if actors:
            xs = [a["location"][0] for a in actors]
            ys = [a["location"][1] for a in actors]
            zs = [a["location"][2] for a in actors]
            center = (sum(xs) / len(xs), sum(ys) / len(ys),
                      sum(zs) / len(zs))
            radius = max(max(xs) - min(xs), max(ys) - min(ys), 400.0) / 2.0
        else:
            center, radius = (0.0, 0.0, 0.0), 600.0
        try:
            ops = build_rig(args["style"], center, radius,
                            float(args.get("intensity", 0.6)))
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        applied, errors = 0, []
        for op in ops:
            r = transport.call(op["func"], **op["kwargs"])
            if r.get("ok"):
                applied += 1
            else:
                errors.append(r.get("error"))
        out = {"ok": not errors, "action": "light_rig",
               "style": args["style"], "applied": applied,
               "total": len(ops)}
        if errors:
            out["error"] = "; ".join(str(e) for e in errors[:3])
        return out

    if name == "setup_environment":
        return transport.call("cnd_spawn_env", kind=args["kind"],
                              params=args.get("params") or {})

    if name == "pcg_scatter":
        vol = transport.call(
            "cnd_pcg_spawn_volume",
            graph_path=args["graph_path"],
            name=args.get("name"),
            origin=args.get("origin", [0, 0, 0]),
            size=args.get("size", [2000, 2000, 500]),
        )
        if not vol.get("ok"):
            return vol
        gen = transport.call("cnd_pcg_generate", name=vol["name"])
        if not gen.get("ok"):
            return gen
        gen["volume"] = vol["name"]
        return gen

    if name == "set_viewport_camera":
        kw = {}
        for key in ("location", "rotation", "look_at", "orbit"):
            if args.get(key) is not None:
                kw[key] = args[key]
        return transport.call("cnd_set_camera", **kw)

    if name == "frame_scene":
        kw = {}
        if args.get("prefix"):
            kw["prefix"] = args["prefix"]
        return transport.call("cnd_frame_actors", **kw)

    if name == "look_at_scene":
        kw = {}
        if args.get("view"):
            kw["view"] = args["view"]
        return _resolve_screenshot(transport.call("cnd_screenshot", **kw))

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
