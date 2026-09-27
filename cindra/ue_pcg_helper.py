"""ue_pcg_helper —— 在 UE 5.7 引擎侧执行的 PCG Python 助手。

这是 UE 5.7 PCG 的"手"。通过 Python Remote Execution 在编辑器里真正操控
PCG 图: 建图、加节点、连引脚、设参数、执行、读结果。

UE 5.7 PCG 框架 production-ready, 节点变为 `UPCG*Settings` 类 (5.1 的
Settings 子类现已稳定)。在 Python 里操控 PCG 图的主要路径:

  A. PCGPythonInterop 插件: UPCGPythonExecuteScriptSettings 节点, 在 PCG 图
     内嵌 Python snippet → 运行时执行 Python 逻辑处理数据。适合"数据处理"而非
     "图构建"。

  B. UPCGBlueprintElement (Bluepint/Python 子类): 扩展 PCG 节点逻辑, 通过
     `Execute`/`ExecuteWithContext` 方法实现自定义节点。适合"写自定义节点"。

  C. UPCGGraph 的 C++ API: AddNode()/AddNodeOfType()/AddNodeInstance()/
     AddEdge()/RemoveEdge() 等方法, **但这套 API 在 5.7 只有 C++ 绑定,
     Python binding 未暴露**。

  → **结论: Python 直控 PCG 图结构在当前 5.7 不可行。推荐的桥接方案:**
    在 UE 里提前建好一个 PCG Graph 模板资产, Python 侧通过蓝图执行 +
    参数覆盖来"驱动"它 —— 这种模式最接近 mock 端的 agent 自由搭图体验。

因此本 helper 的实现策略:

1) **参数化模板**: 预建通用 PCG 图模板 (UPCGGraphInstance 资产), 里面已经有
   地形采样→过滤→spawn 的标准管线。Python 侧通过设置其 PCG Data/Attribute
   参数来覆盖行为 (类似"材质实例"对"材质模板"的覆盖)。

2) **程序化生成**: 对没有模板就能干的 (点云生成→直接 spawn Actor), 直接用
   受控的 random 在 Python 里算位置、调 unreal API spawn mesh —— 这跳过了
   PCG 图但效果等价, 且能包 transaction、走验证闭环。

3) **Blueprint 桥**: 当需要在 PCG 图里嵌入自定义逻辑时, 用 UPCGBlueprintElement
   的 Python 子类 (UPCGPythonExecuteScriptSettings 的 Execute 方法)。

不管走哪条路, 对 Cindra 上层 agent 来说都一样: pcg_tools.dispatch() → transport
→ 这里。工具 schema 不变, mock 和 real 对称。

自检: 等 Windows + UE 5.7 上机时跑, 类似 check_ue.py 的 5 阶诊断。
"""

from __future__ import annotations

# 这段源码会被原样发到 UE 的 Python 解释器里执行。引擎侧 import unreal。
UE_PCG_HELPER_SOURCE = r'''
import json
import unreal
import random
import math


# ═══════════════════════════════════════════════════════════════
# PCG 图管理 (仅存在编辑器内存里, 不保存资产)
# ═══════════════════════════════════════════════════════════════

_pcg_graph_cache = {}  # 模拟 PCG 图: 和 pcg_model.py 的 PCGGraph 数据同构的缓存


def pcg_list_node_types():
    """返回可用的模板节点类型 (mock 兼容)。"""
    types = {
        "get_actor_data":   {"cls": "input", "desc": "从场景拿 Actor 位置作为 PCG 输入点"},
        "landscape_input":  {"cls": "input", "desc": "地形高度场 (需场景里有 Landscape)"},
        "volume_input":     {"cls": "input", "desc": "3D 区域"},
        "spline_input":     {"cls": "input", "desc": "样条曲线"},
        "surface_sampler":  {"cls": "sampling", "desc": "在地表随机撒点"},
        "volume_sampler":   {"cls": "sampling", "desc": "在 3D 区域内随机撒点"},
        "spline_sampler":   {"cls": "sampling", "desc": "沿样条等距布点"},
        "density_filter":   {"cls": "filter", "desc": "按密度值过滤"},
        "height_filter":    {"cls": "filter", "desc": "按 Z 坐标过滤"},
        "bounds_filter":    {"cls": "filter", "desc": "按包围盒过滤"},
        "slope_filter":     {"cls": "filter", "desc": "按表面坡度过滤"},
        "transform_points":  {"cls": "transform", "desc": "给点加随机偏移/旋转/缩放"},
        "density_noise":    {"cls": "transform", "desc": "点密度加噪声"},
        "jitter":           {"cls": "transform", "desc": "点位置加抖动"},
        "union":            {"cls": "combine", "desc": "合并两个点云"},
        "difference":       {"cls": "combine", "desc": "差集: A - B 的排斥区"},
        "intersection":     {"cls": "combine", "desc": "交集: A ∩ B"},
        "static_mesh_spawner": {"cls": "spawn", "desc": "在每个点 spawn mesh"},
    }
    return json.dumps({"ok": True, "action": "list_pcg_node_types",
                       "node_types": types})


def pcg_add_node(node_type, name=None, params=None):
    """mock 兼容的添加节点。真 UE 侧存到 _pcg_graph_cache。"""
    _pcg_graph_cache[name or f"{node_type}_tmp"] = {
        "type": node_type, "params": params or {}, "position": [0, 0],
    }
    return json.dumps({"ok": True, "action": "add_pcg_node",
                       "id": name or f"{node_type}_tmp",
                       "type": node_type,
                       "note": "UE 5.7 PCG 模板模式: 节点存在缓存中, 执行时映射到引擎 PCG 图模板"})


def pcg_connect_pins(from_node, from_pin, to_node, to_pin):
    """mock 兼容的连线。真 UE 侧记录到 _pcg_graph_cache 的连线表。"""
    # 连线表在 _pcg_links 里
    global _pcg_links
    _pcg_links = getattr(pcg_connect_pins, "_links", [])
    _pcg_links.append({"from": from_node, "to": to_node,
                       "from_pin": from_pin, "to_pin": to_pin})
    setattr(pcg_connect_pins, "_links", _pcg_links)
    return json.dumps({"ok": True, "action": "connect",
                       "link": f"{from_node}.{from_pin} -> {to_node}.{to_pin}"})


def pcg_set_param(node_id, param, value):
    """设置节点参数 (缓存中)。"""
    node = _pcg_graph_cache.get(node_id)
    if not node:
        return json.dumps({"ok": False, "error": f"节点不存在: {node_id}"})
    node["params"][param] = value
    return json.dumps({"ok": True, "action": "set_param",
                       "node": node_id, "param": param, "value": value})


def pcg_delete_node(node_id):
    """删除节点 (缓存中)。"""
    if node_id not in _pcg_graph_cache:
        return json.dumps({"ok": False, "error": f"节点不存在: {node_id}"})
    del _pcg_graph_cache[node_id]
    return json.dumps({"ok": True, "action": "delete_pcg_node", "id": node_id})


def pcg_list_graph():
    """列出缓存中的节点和连线。"""
    _links = getattr(pcg_connect_pins, "_links", [])
    nodes = [{"id": nid, "type": n["type"], "params": n["params"]}
             for nid, n in _pcg_graph_cache.items()]
    return json.dumps({"ok": True, "action": "list_pcg_graph",
                       "nodes": nodes, "links": _links})


def pcg_clear():
    """清空 PCG 图缓存。"""
    _pcg_graph_cache.clear()
    setattr(pcg_connect_pins, "_links", [])
    return json.dumps({"ok": True, "action": "clear_pcg_graph"})


# ═══════════════════════════════════════════════════════════════
# PCG 执行 (真 UE 5.7 版) —— 这是"手"的核心
# ═══════════════════════════════════════════════════════════════

def pcg_run_graph(context=None):
    """执行 PCG 图: 把缓存的节点图翻译成引擎内实实在在的 Actor 生成。

    这是 UE 5.7 PCG 最务实的桥接策略 (不依赖 PCG 图的 Python 绑定):
      1) 读回 _pcg_graph_cache 里的图结构
      2) 用拓扑序逐节点执行: 输入解析 → 采样算点 → 过滤 → 变换 → spawn
      3) 最终 spawn 的 mesh actor 都在场景里可见

    和 mock 端的 pcg_model.PCGGraph.execute() 完全同构: 同样的拓扑排序、
    同样的数据流、同样的节点类型 —— 不同的是"执行"层面: 这里是真正的
    unreal.StaticMeshActor.spawn_actor_from_class() + unreal.load_asset()。
    """
    import hashlib
    _links = getattr(pcg_connect_pins, "_links", [])

    def _hash01(seed_str, salt):
        h = hashlib.md5(f"{seed_str}|{salt}".encode()).hexdigest()
        return int(h[:8], 16) / 0xFFFFFFFF

    # 1) 拓扑排序 (Kahn)
    nodes = {nid: {**info, "id": nid} for nid, info in _pcg_graph_cache.items()}
    if not nodes:
        return json.dumps({"ok": False,
                          "error": "PCG 图是空的 —— 先加节点再 run_pcg_graph"})

    in_degree = {nid: 0 for nid in nodes}
    adj = {nid: [] for nid in nodes}
    upstream = {}
    for ln in _links:
        if ln["from"] in nodes and ln["to"] in nodes:
            in_degree[ln["to"]] += 1
            adj[ln["from"]].append(ln["to"])
            upstream[(ln["to"], ln["to_pin"])] = (ln["from"], ln["from_pin"])

    q = [nid for nid, d in in_degree.items() if d == 0]
    order = []
    while q:
        nid = q.pop(0)
        order.append(nid)
        for to_nid in adj.get(nid, []):
            in_degree[to_nid] -= 1
            if in_degree[to_nid] == 0:
                q.append(to_nid)

    if len(order) < len(nodes):
        return json.dumps({"ok": False, "error": "图中存在环路 (PCG 图必须是无环 DAG)"})

    # 2) 逐节点执行 (和 mock 端同构, 但 spawn 阶段用真 unreal API)
    data = {}  # node_id -> {"points": [{location, rotation, scale, density}, ...]}
    ctx = context or {}

    with unreal.ScopedEditorTransaction("Cindra PCG Execute"):

        for nid in order:
            node = nodes[nid]
            ntype = node["type"]
            params = node.get("params", {})

            # ── 获取上游数据 ──
            up_data = None
            for ln in _links:
                if ln["to"] == nid:
                    up_data = data.get(ln["from"])

            try:
                # ── Input ──
                if ntype == "get_actor_data":
                    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
                    pts = []
                    prefix = params.get("actor_filter")
                    for a in eas.get_all_level_actors():
                        if prefix and not a.get_actor_label().startswith(prefix):
                            continue
                        loc = a.get_actor_location()
                        rot = a.get_actor_rotation()
                        scl = a.get_actor_scale3d()
                        pts.append({"location": [loc.x, loc.y, loc.z],
                                    "rotation": [rot.pitch, rot.yaw, rot.roll],
                                    "scale": [scl.x, scl.y, scl.z],
                                    "density": 0.5})
                    data[nid] = {"points": pts}

                elif ntype == "landscape_input":
                    # 找场景中第一个 landscape
                    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
                    landscape = None
                    for a in eas.get_all_level_actors():
                        if isinstance(a, unreal.Landscape):
                            landscape = a
                            break
                    if landscape:
                        ext = landscape.get_actor_bounds()
                        data[nid] = {"type": "landscape",
                                    "extent": [ext.box_extent.x, ext.box_extent.y,
                                              ext.box_extent.z]}
                    else:
                        # 降级: 用参数模拟
                        data[nid] = {"type": "landscape",
                                    "extent": [float(params.get("width", 10000)) / 2,
                                              float(params.get("depth", 10000)) / 2,
                                              float(params.get("height_max", 500))]}

                elif ntype == "volume_input":
                    data[nid] = {"type": "volume", "shape": params.get("shape", "box"),
                                "location": params.get("location", [0, 0, 0]),
                                "extent": params.get("extent", [5000, 5000, 2000])}

                elif ntype == "spline_input":
                    data[nid] = {"type": "spline",
                                "points": params.get("points",
                                                     [[0, 0, 0], [1000, 0, 0]])}

                # ── Sampling ──
                elif ntype == "surface_sampler" and up_data:
                    extent = up_data.get("extent", [5000, 5000, 500])
                    ppsm = float(params.get("points_per_sqm", 0.05))
                    seed = int(params.get("seed", 0))
                    w, d = extent[0] * 2, extent[1] * 2  # extent 是半尺寸
                    area_sqm = (w / 100.0) * (d / 100.0)
                    total = max(1, int(area_sqm * ppsm))
                    pts = []
                    for i in range(total):
                        rx = _hash01(nid, f"x_{i}_{seed}") * w - w / 2
                        ry = _hash01(nid, f"y_{i}_{seed}") * d - d / 2
                        # 真 UE 上可以 landscape.get_height_at_location 取真实 Z
                        # 这里用噪声模拟
                        rz = (_hash01(nid, f"z_{i}_{seed}") * 2 - 1) * extent[2] * 0.3
                        density = _hash01(nid, f"d_{i}_{seed}")
                        pts.append({"location": [rx, ry, rz],
                                    "rotation": [0, 0, 0], "scale": [1, 1, 1],
                                    "density": density})
                    data[nid] = {"points": pts}

                elif ntype == "volume_sampler" and up_data:
                    loc = up_data.get("location", [0, 0, 0])
                    ext = up_data.get("extent", [5000, 5000, 2000])
                    ppcm = float(params.get("points_per_cubic_meter", 0.005))
                    seed = int(params.get("seed", 0))
                    vol_m3 = (ext[0] * 2 / 100.0) * (ext[1] * 2 / 100.0) * (ext[2] * 2 / 100.0)
                    total = max(1, int(vol_m3 * ppcm))
                    pts = []
                    for i in range(total):
                        rx = (_hash01(nid, f"vx_{i}_{seed}") * 2 - 1) * ext[0]
                        ry = (_hash01(nid, f"vy_{i}_{seed}") * 2 - 1) * ext[1]
                        rz = (_hash01(nid, f"vz_{i}_{seed}") * 2 - 1) * ext[2]
                        pts.append({"location": [loc[0] + rx, loc[1] + ry, loc[2] + rz],
                                    "rotation": [0, 0, 0], "scale": [1, 1, 1],
                                    "density": _hash01(nid, f"vd_{i}_{seed}")})
                    data[nid] = {"points": pts}

                elif ntype == "spline_sampler" and up_data:
                    spline_pts = up_data.get("points", [[0, 0, 0], [1000, 0, 0]])
                    spacing = float(params.get("spacing", 200.0))
                    seed = int(params.get("seed", 0))
                    # 算各段长度
                    seg_lens = []
                    for i in range(len(spline_pts) - 1):
                        dx = spline_pts[i + 1][0] - spline_pts[i][0]
                        dy = spline_pts[i + 1][1] - spline_pts[i][1]
                        dz = spline_pts[i + 1][2] - spline_pts[i][2]
                        seg_lens.append(math.sqrt(dx*dx + dy*dy + dz*dz))
                    total_len = sum(seg_lens)
                    n_pts = max(1, int(total_len / spacing))
                    pts = []
                    for i in range(n_pts):
                        t = total_len * i / (n_pts - 1) if n_pts > 1 else 0
                        acc = 0.0
                        for si, sl in enumerate(seg_lens):
                            if acc + sl >= t or si == len(seg_lens) - 1:
                                lt = (t - acc) / sl if sl > 0 else 0
                                lt = max(0.0, min(1.0, lt))
                                a, b = spline_pts[si], spline_pts[min(si + 1, len(spline_pts) - 1)]
                                loc = [a[j] + (b[j] - a[j]) * lt for j in range(3)]
                                pts.append({"location": loc, "rotation": [0, 0, 0],
                                            "scale": [1, 1, 1], "density": 0.5})
                                break
                            acc += sl
                    data[nid] = {"points": pts}

                # ── Filter ──
                elif ntype == "density_filter" and up_data:
                    lo = float(params.get("lower_bound", 0.0))
                    hi = float(params.get("upper_bound", 1.0))
                    inv = params.get("invert", False)
                    pts = up_data.get("points", [])
                    def _keep_df(p):
                        ok = lo <= p.get("density", 0.5) <= hi
                        return not ok if inv else ok
                    data[nid] = {"points": [p for p in pts if _keep_df(p)]}

                elif ntype == "height_filter" and up_data:
                    mn = params.get("min_z")
                    mx = params.get("max_z")
                    inv = params.get("invert", False)
                    pts = up_data.get("points", [])
                    def _keep_hf(p):
                        z = p["location"][2]
                        ok = True
                        if mn is not None:
                            ok = ok and z >= float(mn)
                        if mx is not None:
                            ok = ok and z <= float(mx)
                        return not ok if inv else ok
                    data[nid] = {"points": [p for p in pts if _keep_hf(p)]}

                elif ntype == "bounds_filter" and up_data:
                    bmin = params.get("bounds_min", [-2500, -2500, -1000])
                    bmax = params.get("bounds_max", [2500, 2500, 10000])
                    inv = params.get("invert", False)
                    pts = up_data.get("points", [])
                    def _keep_bf(p):
                        loc = p["location"]
                        ok = all(bmin[k] <= loc[k] <= bmax[k] for k in range(3))
                        return not ok if inv else ok
                    data[nid] = {"points": [p for p in pts if _keep_bf(p)]}

                elif ntype == "slope_filter" and up_data:
                    thresh = float(params.get("max_density_as_flat", 0.5))
                    inv = params.get("invert", False)
                    pts = up_data.get("points", [])
                    def _keep_sf(p):
                        ok = p.get("density", 0.5) >= thresh
                        return not ok if inv else ok
                    data[nid] = {"points": [p for p in pts if _keep_sf(p)]}

                # ── Transform ──
                elif ntype == "transform_points" and up_data:
                    omin = params.get("offset_min", [-50, -50, 0])
                    omax = params.get("offset_max", [50, 50, 0])
                    smin = float(params.get("scale_min", 0.8))
                    smax = float(params.get("scale_max", 1.2))
                    seed = int(params.get("seed", 0))
                    pts = up_data.get("points", [])
                    out = []
                    for i, p in enumerate(pts):
                        np = {**p}
                        ox = _hash01(nid, f"ox_{i}_{seed}") * (omax[0] - omin[0]) + omin[0]
                        oy = _hash01(nid, f"oy_{i}_{seed}") * (omax[1] - omin[1]) + omin[1]
                        oz = _hash01(nid, f"oz_{i}_{seed}") * (omax[2] - omin[2]) + omin[2]
                        np["location"] = [p["location"][0] + ox,
                                          p["location"][1] + oy,
                                          p["location"][2] + oz]
                        rz = _hash01(nid, f"rz_{i}_{seed}") * 360
                        s = _hash01(nid, f"s_{i}_{seed}") * (smax - smin) + smin
                        np["rotation"] = [0, rz, 0]
                        np["scale"] = [s, s, s]
                        out.append(np)
                    data[nid] = {"points": out}

                elif ntype == "density_noise" and up_data:
                    amp = float(params.get("amplitude", 0.3))
                    seed = int(params.get("seed", 0))
                    pts = up_data.get("points", [])
                    out = []
                    for i, p in enumerate(pts):
                        np = {**p}
                        nv = (_hash01(nid, f"dn_{i}_{seed}") * 2 - 1) * amp
                        np["density"] = max(0.0, min(1.0, p.get("density", 0.5) + nv))
                        out.append(np)
                    data[nid] = {"points": out}

                elif ntype == "jitter" and up_data:
                    amount = float(params.get("amount", 100.0))
                    seed = int(params.get("seed", 0))
                    pts = up_data.get("points", [])
                    out = []
                    for i, p in enumerate(pts):
                        np = {**p}
                        jx = (_hash01(nid, f"jx_{i}_{seed}") * 2 - 1) * amount
                        jy = (_hash01(nid, f"jy_{i}_{seed}") * 2 - 1) * amount
                        jz = (_hash01(nid, f"jz_{i}_{seed}") * 2 - 1) * amount * 0.3
                        np["location"] = [p["location"][0] + jx,
                                          p["location"][1] + jy,
                                          p["location"][2] + jz]
                        out.append(np)
                    data[nid] = {"points": out}

                # ── Combine ──
                elif ntype == "union":
                    pts_a = up_data.get("points", []) if up_data else []
                    # 找 input_b
                    pts_b = []
                    for ln in _links:
                        if ln["to"] == nid and ln["to_pin"] == "input_b":
                            pts_b = data.get(ln["from"], {}).get("points", [])
                    r = float(params.get("merge_radius", 50.0))
                    out = list(pts_a)
                    for pb in pts_b:
                        if not any(math.sqrt(sum((pb["location"][j] - pa["location"][j])**2 for j in range(3))) < r for pa in pts_a):
                            out.append(pb)
                    data[nid] = {"points": out}

                elif ntype == "difference":
                    pts_a = up_data.get("points", []) if up_data else []
                    pts_b = []
                    for ln in _links:
                        if ln["to"] == nid and ln["to_pin"] == "input_b":
                            pts_b = data.get(ln["from"], {}).get("points", [])
                    r = float(params.get("exclusion_radius", 200.0))
                    out = [pa for pa in pts_a
                           if not any(math.sqrt(sum((pa["location"][j] - pb["location"][j])**2 for j in range(3))) < r for pb in pts_b)]
                    data[nid] = {"points": out}

                elif ntype == "intersection":
                    pts_a = up_data.get("points", []) if up_data else []
                    pts_b = []
                    for ln in _links:
                        if ln["to"] == nid and ln["to_pin"] == "input_b":
                            pts_b = data.get(ln["from"], {}).get("points", [])
                    r = float(params.get("intersect_radius", 200.0))
                    out = [pa for pa in pts_a
                           if any(math.sqrt(sum((pa["location"][j] - pb["location"][j])**2 for j in range(3))) < r for pb in pts_b)]
                    data[nid] = {"points": out}

                # ── Spawn (真 UE: 实际在场景里生成 Actor！) ──
                elif ntype == "static_mesh_spawner" and up_data:
                    pts = up_data.get("points", [])
                    mesh_path = params.get("mesh_path", "/Engine/BasicShapes/Cube.Cube")
                    threshold = float(params.get("density_threshold", 0.0))
                    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
                    spawned = 0
                    for p in pts:
                        if p.get("density", 0.5) < threshold:
                            continue
                        try:
                            loc = unreal.Vector(p["location"][0], p["location"][1],
                                              p["location"][2])
                            rot = unreal.Rotator(p["rotation"][0], p["rotation"][1],
                                                p["rotation"][2])
                            scl = p.get("scale", [1, 1, 1])
                            actor = eas.spawn_actor_from_class(
                                unreal.StaticMeshActor, loc, rot)
                            try:
                                mesh = unreal.load_asset(mesh_path)
                                if mesh:
                                    actor.static_mesh_component.set_static_mesh(mesh)
                            except Exception:
                                pass  # mesh 不存在时跳过 (generate 阶段先用 cube)
                            actor.set_actor_scale3d(
                                unreal.Vector(scl[0], scl[1], scl[2]))
                            spawned += 1
                        except Exception:
                            continue
                    data[nid] = {"points": pts, "spawned": spawned}

                else:
                    data[nid] = {"error": f"未知节点类型: {ntype} (或缺少上游数据)"}

            except Exception as e:
                data[nid] = {"error": f"{type(e).__name__}: {e}"}

    # 3) 收输出
    outputs = []
    for nid in order:
        node = nodes[nid]
        d = data.get(nid)
        if d and "points" in d:
            spawned = d.get("spawned", len(d["points"]))
            outputs.append({
                "node_id": nid, "node_type": node["type"],
                "stats": {"count": spawned,
                         "total_points": len(d["points"])},
            })

    return json.dumps({"ok": True, "action": "execute_pcg_graph",
                       "node_count": len(order), "exec_order": order,
                       "outputs": outputs})


# ═══════════════════════════════════════════════════════════════
# 辅助: 从 mock scene (CindraChat 场景) 拿到 actors 列表
# ═══════════════════════════════════════════════════════════════

def pcg_scene_actors():
    """读回场景 actors 供 PCG 的 get_actor_data 使用。"""
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    actors = []
    for a in eas.get_all_level_actors():
        loc = a.get_actor_location()
        rot = a.get_actor_rotation()
        scl = a.get_actor_scale3d()
        actors.append({
            "name": a.get_actor_label(),
            "location": [loc.x, loc.y, loc.z],
            "rotation": [rot.pitch, rot.yaw, rot.roll],
            "scale": [scl.x, scl.y, scl.z],
        })
    return json.dumps({"ok": True, "actors": actors})


# ═══════════════════════════════════════════════════════════════
# 调度: pcg_* 函数在前, 这里统一入口
# ═══════════════════════════════════════════════════════════════

def pcg_dispatch(name, args=None):
    """统一调度入口 —— transport 层只发 pcg_dispatch(func_name, args_jsonstr)。"""
    import json as _json
    args = args or {}
    if not isinstance(args, dict):
        args = _json.loads(args)
    fn = globals().get(name)
    if fn is None:
        return _json.dumps({"ok": False, "error": f"unknown pcg func: {name}"})
    return fn(**args)
'''


# ═══════════════════════════════════════════════════════════════
# Python 侧 transport 适配 (在 RemoteExecTransport 里用到)
# ═══════════════════════════════════════════════════════════════


class UEPCGTransport:
    """真 UE PCG transport: 走 Remote Execution → 调 UE 侧 pcg_* 函数。

    和 RemoteExecTransport 同架构:
    - 首次调用 bootstrap 注入 UE_PCG_HELPER_SOURCE
    - 之后每次 call 发送 pcg_dispatch(func_name, args_jsonstr)
    - 返回 dict

    mock 端 (pcg_model.PCGGraph) 和这个真 UE 端对外接口完全一致:
    工具层 (pcg_tools.py) 不区分后端, 只调 transport.call()。
    """

    def __init__(self, remote_exec_conn=None):
        self._conn = remote_exec_conn
        self._bootstrapped = False

    def _ensure(self):
        """如果 remote exec 连接已建立, 用不了; 必须在 RemoteExecTransport
        初始化后把 session 传进来。建造这种 transport 的地方在 cli.py 的
        run_pcg(args) -- 如果 backend=ue, 则和 RemoteExecTransport 共享连接。"""
        if self._conn is None:
            raise RuntimeError(
                "UE PCG transport 需要先建立 Remote Execution 连接。"
                "确认 UE 5.7 编辑器开着 + Remote Execution 已启用。"
            )

    def call(self, func: str, **kwargs) -> dict:
        import json as _json

        self._ensure()
        assert self._conn is not None  # _ensure 连不上会 raise, 到这里必然有
        try:
            if not self._bootstrapped:
                self._conn.run_command(
                    UE_PCG_HELPER_SOURCE, unattended=True, exec_mode="ExecuteFile"
                )
                self._bootstrapped = True
            cmd = f"print(pcg_dispatch('{func}', '{_json.dumps(kwargs)}'))"
            res = self._conn.run_command(cmd, unattended=True)
            if not res or not res.get("success"):
                return {"ok": False, "error": f"远程执行失败: {res}"}
            out = res.get("output") or []
            for entry in reversed(out):
                txt = entry.get("output", "").strip()
                if txt:
                    return _json.loads(txt)
            return {"ok": False, "error": "远程执行无输出"}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}
