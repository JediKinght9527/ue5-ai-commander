"""pcg_model —— Mac 上的内存 PCG (Procedural Content Generation) 图模型。

UE 5.7 的 PCG 框架正式 production-ready。本文件复刻其核心概念:
  - 节点 + 类型化引脚 (点云/地表/体积/样条)
  - 拓扑排序执行 (DAG + Kahn)
  - 确定性的点云生成 (基于节点 id + 种子 → hash → 伪随机)
  - 属性系统 (位置/旋转/缩放/密度/种子/包围盒)
  - ASCII 可视化 (俯视图 + 统计摘要)

和 mock_ue/blueprint_model 一样, 这是 Mac 离线验证的替身。
真 UE 接法见 ue_pcg_helper.py (走 PCGPythonInterop + Remote Execution)。

自检: python3 -m cindra.pcg_model
"""

from __future__ import annotations

import hashlib
import math

# ═══════════════════════════════════════════════════════════════
# 数据类型
# ═══════════════════════════════════════════════════════════════


class PointCloud:
    """点云: PCG 的核心数据类型。每个点是一个属性字典。"""

    def __init__(self, points: list[dict] | None = None) -> None:
        self.points: list[dict] = points or []

    def __len__(self) -> int:
        return len(self.points)

    def __repr__(self) -> str:
        return f"PointCloud({len(self.points)} points)"

    def to_dict(self) -> dict:
        return {"type": "point_cloud", "count": len(self.points), "points": self.points}

    def stats(self) -> dict:
        """统计摘要: 用于 inspect 和校验。"""
        if not self.points:
            return {"count": 0}
        xs = [p["location"][0] for p in self.points]
        ys = [p["location"][1] for p in self.points]
        zs = [p["location"][2] for p in self.points]
        ds = [p.get("density", 0.5) for p in self.points]
        return {
            "count": len(self.points),
            "x_range": [min(xs), max(xs)],
            "y_range": [min(ys), max(ys)],
            "z_range": [min(zs), max(zs)],
            "density": {"min": min(ds), "max": max(ds), "mean": sum(ds) / len(ds)},
            "center": [sum(xs) / len(xs), sum(ys) / len(ys), sum(zs) / len(zs)],
        }


# ═══════════════════════════════════════════════════════════════
# 确定性随机 (复刻 mock_ue 的 _rand01 策略)
# ═══════════════════════════════════════════════════════════════


def _hash_float(seed_str: str, salt: str) -> float:
    """基于 (seed_str, salt) 的稳定伪随机 [0, 1)。md5 不受 PYTHONHASHSEED 影响。"""
    h = hashlib.md5(f"{seed_str}|{salt}".encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def _hash_int(seed_str: str, salt: str, lo: int, hi: int) -> int:
    return int(_hash_float(seed_str, salt) * (hi - lo + 1)) + lo


# ═══════════════════════════════════════════════════════════════
# 节点模板库
# ═══════════════════════════════════════════════════════════════

# 每个模板: { description, inputs: [(pin, type_label), ...],
#              outputs: [(pin, type_label), ...],
#              params: { name: {type, default, desc} } }
# type_label ∈ {point_cloud, landscape, volume, spline, any}

NODE_TEMPLATES: dict[str, dict] = {
    # ── Input ──
    "get_actor_data": {
        "description": "从场景里拿 Actor 的位置当 PCG 输入点。桥接 CindraChat 场景 ↔ PCG。",
        "inputs": [],
        "outputs": [("points", "point_cloud")],
        "params": {
            "actor_filter": {"type": "string", "default": None, "desc": "按名字前缀过滤"},
            "include_scale": {"type": "bool", "default": True},
        },
        "cls": "input",
    },
    "landscape_input": {
        "description": "生成模拟地表 (高度场)。mock 用确定性噪声模拟真实地形起伏。",
        "inputs": [],
        "outputs": [("landscape", "landscape")],
        "params": {
            "width": {"type": "float", "default": 10000.0},
            "depth": {"type": "float", "default": 10000.0},
            "height_min": {"type": "float", "default": 0.0},
            "height_max": {"type": "float", "default": 500.0},
            "noise_scale": {"type": "float", "default": 1.0, "desc": "起伏幅度 0=smooth"},
            # 0 = 跟随 execute(global_seed=...)。其余 input 节点也都是 0,
            # 这里原本是 42, 导致 global_seed 对地形完全无效。
            "seed": {"type": "int", "default": 0},
        },
        "cls": "input",
    },
    "volume_input": {
        "description": "生成 3D 区域 (盒/球/柱)。",
        "inputs": [],
        "outputs": [("volume", "volume")],
        "params": {
            "shape": {"type": "string", "default": "box", "desc": "box|sphere|cylinder"},
            "location": {"type": "vector", "default": [0, 0, 0]},
            "extent": {"type": "vector", "default": [5000, 5000, 2000], "desc": "半尺寸"},
            "seed": {"type": "int", "default": 0},
        },
        "cls": "input",
    },
    "spline_input": {
        "description": "生成样条曲线 (折线)。",
        "inputs": [],
        "outputs": [("spline", "spline")],
        "params": {
            "points": {
                "type": "vector_array",
                "default": [[0, 0, 0], [1000, 500, 0], [2000, 0, 0]],
            },
            "closed": {"type": "bool", "default": False},
        },
        "cls": "input",
    },
    # ── Sampling ──
    "surface_sampler": {
        "description": "地表撒点 (均匀随机)。入口挂 landscape_input 的 landscape 引脚。",
        "inputs": [("source", "landscape")],
        "outputs": [("points", "point_cloud")],
        "params": {
            "points_per_sqm": {"type": "float", "default": 0.05, "desc": "每平方米点数"},
            "seed": {"type": "int", "default": 0},
        },
        "cls": "sampling",
    },
    "volume_sampler": {
        "description": "3D 区域内随机撒点。",
        "inputs": [("source", "volume")],
        "outputs": [("points", "point_cloud")],
        "params": {
            "points_per_cubic_meter": {"type": "float", "default": 0.005},
            "seed": {"type": "int", "default": 0},
        },
        "cls": "sampling",
    },
    "spline_sampler": {
        "description": "沿样条等间距布点。",
        "inputs": [("source", "spline")],
        "outputs": [("points", "point_cloud")],
        "params": {
            "spacing": {"type": "float", "default": 200.0},
            "seed": {"type": "int", "default": 0},
        },
        "cls": "sampling",
    },
    # ── Filter ──
    "density_filter": {
        "description": "按密度值过滤点云 (密度 ∈ [lower, upper] 才保留)。",
        "inputs": [("points", "point_cloud")],
        "outputs": [("points", "point_cloud")],
        "params": {
            "lower_bound": {"type": "float", "default": 0.0},
            "upper_bound": {"type": "float", "default": 1.0},
            "invert": {"type": "bool", "default": False},
        },
        "cls": "filter",
    },
    "height_filter": {
        "description": "按 Z 坐标范围过滤。",
        "inputs": [("points", "point_cloud")],
        "outputs": [("points", "point_cloud")],
        "params": {
            "min_z": {"type": "float", "default": None, "desc": "None=不限"},
            "max_z": {"type": "float", "default": None},
            "invert": {"type": "bool", "default": False},
        },
        "cls": "filter",
    },
    "bounds_filter": {
        "description": "按包围盒过滤 (点必须在 box 内才保留)。",
        "inputs": [("points", "point_cloud")],
        "outputs": [("points", "point_cloud")],
        "params": {
            "bounds_min": {"type": "vector", "default": [-2500, -2500, -1000]},
            "bounds_max": {"type": "vector", "default": [2500, 2500, 10000]},
            "invert": {"type": "bool", "default": False},
        },
        "cls": "filter",
    },
    "slope_filter": {
        "description": "按坡度过滤 (以密度值模拟坡度, 密度越低越'陡')。和 surface_sampler 串联用 —— 采样默认密度=0.5, 经 density_noise 扰动后模拟真实坡度分布。",
        "inputs": [("points", "point_cloud")],
        "outputs": [("points", "point_cloud")],
        "params": {
            "max_density_as_flat": {
                "type": "float",
                "default": 0.5,
                "desc": "密度≥此值视为'平坦'区域, 低于此值视为'陡坡'",
            },
            "invert": {"type": "bool", "default": False, "desc": "True=只保留陡坡"},
        },
        "cls": "filter",
    },
    # ── Transform ──
    "transform_points": {
        "description": "给每个点加随机偏移/旋转/缩放 —— 模拟自然随机性打破网格感。",
        "inputs": [("points", "point_cloud")],
        "outputs": [("points", "point_cloud")],
        "params": {
            "offset_min": {"type": "vector", "default": [-50, -50, 0]},
            "offset_max": {"type": "vector", "default": [50, 50, 0]},
            "rotation_min": {"type": "vector", "default": [0, 0, 0], "desc": "deg"},
            "rotation_max": {"type": "vector", "default": [0, 360, 0]},
            "scale_min": {"type": "float", "default": 0.8},
            "scale_max": {"type": "float", "default": 1.2},
            "absolute": {"type": "bool", "default": False, "desc": "True=设绝对值, False=叠加"},
            "seed": {"type": "int", "default": 0},
        },
        "cls": "transform",
    },
    "density_noise": {
        "description": "对点密度加确定性噪声 (模拟真实地形坡度/植被密度变化)。通常接在 surface_sampler 之后、spawner 之前。",
        "inputs": [("points", "point_cloud")],
        "outputs": [("points", "point_cloud")],
        "params": {
            "amplitude": {"type": "float", "default": 0.3},
            "frequency": {"type": "float", "default": 1.0},
            "seed": {"type": "int", "default": 0},
        },
        "cls": "transform",
    },
    "bounds_modifier": {
        "description": "设置/修改点的包围盒 (影响后续 spawner 的实例体积)。",
        "inputs": [("points", "point_cloud")],
        "outputs": [("points", "point_cloud")],
        "params": {
            "bounds_min": {"type": "vector", "default": [-50, -50, 0]},
            "bounds_max": {"type": "vector", "default": [50, 50, 200]},
        },
        "cls": "transform",
    },
    "jitter": {
        "description": "给点位置加小幅度随机抖动, 打破完美网格感。比 transform_points 更轻量 (只改位置)。",
        "inputs": [("points", "point_cloud")],
        "outputs": [("points", "point_cloud")],
        "params": {
            "amount": {"type": "float", "default": 100.0, "desc": "最大偏移量 cm"},
            "seed": {"type": "int", "default": 0},
        },
        "cls": "transform",
    },
    # ── Spawn (终端节点: 标记在哪些位置 spawn 什么 mesh) ──
    "static_mesh_spawner": {
        "description": "在每个点的位置上 spawn StaticMesh —— PCG 图的终端。mock 里标 mesh 信息到点上供 inspect 查看; 真 UE 端实际生成 Actor。",
        "inputs": [("points", "point_cloud")],
        "outputs": [("points", "point_cloud")],
        "params": {
            "mesh_path": {"type": "string", "default": "/Engine/BasicShapes/Cube.Cube"},
            "mesh_selection": {"type": "string", "default": "all_same", "desc": "all_same|random"},
            "scale_multiplier": {"type": "float", "default": 1.0},
            "density_threshold": {"type": "float", "default": 0.0, "desc": "密度低于此值的点跳过"},
        },
        "cls": "spawn",
    },
    # ── Combine ──
    "union": {
        "description": "合并两个点云 (去重: 太近的点合并为一个)。保留 A 的点 + B 中不在 A 附近的点。",
        "inputs": [("input_a", "point_cloud"), ("input_b", "point_cloud")],
        "outputs": [("points", "point_cloud")],
        "params": {
            "merge_radius": {"type": "float", "default": 50.0},
        },
        "cls": "combine",
    },
    "difference": {
        "description": "A - B: 从 A 中移除靠近 B 的点的。用于'这片区域不长树'。",
        "inputs": [("input_a", "point_cloud"), ("input_b", "point_cloud")],
        "outputs": [("points", "point_cloud")],
        "params": {
            "exclusion_radius": {"type": "float", "default": 200.0, "desc": "B 的排斥半径"},
        },
        "cls": "combine",
    },
    "intersection": {
        "description": "A ∩ B: 只保留 A 中靠近 B 的点。用于'只在特定区域里'。",
        "inputs": [("input_a", "point_cloud"), ("input_b", "point_cloud")],
        "outputs": [("points", "point_cloud")],
        "params": {
            "intersect_radius": {"type": "float", "default": 200.0},
        },
        "cls": "combine",
    },
}

# 所有点云节点的输出引脚都叫 "points" (同 UE PCG 的 Out 约定)


def _make_point(
    location, density=0.5, seed=0, rotation=None, scale=None, bounds_min=None, bounds_max=None
):
    return {
        "location": [float(x) for x in location],
        "rotation": [float(x) for x in (rotation or [0, 0, 0])],
        "scale": [float(x) for x in (scale or [1, 1, 1])],
        "density": float(density),
        "seed": int(seed),
        "bounds_min": [float(x) for x in (bounds_min or [-50, -50, 0])],
        "bounds_max": [float(x) for x in (bounds_max or [50, 50, 200])],
    }


def _dist3(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b, strict=True)))


# ═══════════════════════════════════════════════════════════════
# PCG 图
# ═══════════════════════════════════════════════════════════════


class PCGGraph:
    """一张 PCG 图: 节点 + 连线 + 执行引擎。"""

    def __init__(self) -> None:
        self.nodes: dict[str, dict] = {}  # node_id → {id, type, params, pins, cache}
        self.links: list[dict] = []  # [{from_node, from_pin, to_node, to_pin}]
        self._counter: int = 0
        self._dirty: bool = True  # 图结构变了 → 下次执行重新算

    # ── 图编辑 ──

    def add_node(self, node_type: str, name: str | None = None, params: dict | None = None) -> dict:
        """加一个节点。返回 {ok, id, type, pins} 或 {ok:False, error}。"""
        tmpl = NODE_TEMPLATES.get(node_type)
        if tmpl is None:
            return {
                "ok": False,
                "error": f"未知节点类型: {node_type}. 可用: {list(NODE_TEMPLATES)}",
            }
        self._counter += 1
        nid = name or f"{node_type}_{self._counter}"
        base, i = nid, 1
        while nid in self.nodes:
            i += 1
            nid = f"{base}_{i}"
        # 实例化参数 (模板默认值 + 覆盖)
        final_params = {}
        for pname, pinfo in tmpl["params"].items():
            final_params[pname] = (
                params.get(pname, pinfo["default"]) if params else pinfo["default"]
            )
        # 构建引脚
        inst_inputs = []
        inst_outputs = []
        for pname, plabel in tmpl["inputs"]:
            inst_inputs.append({"name": pname, "direction": "input", "type_label": plabel})
        for pname, plabel in tmpl["outputs"]:
            inst_outputs.append({"name": pname, "direction": "output", "type_label": plabel})
        self.nodes[nid] = {
            "id": nid,
            "type": node_type,
            "cls": tmpl.get("cls", ""),
            "params": final_params,
            "pins": inst_inputs + inst_outputs,
            "cache": None,  # 执行后缓存
        }
        self._dirty = True
        return {
            "ok": True,
            "action": "add_pcg_node",
            "id": nid,
            "type": node_type,
            "pins": [
                f"{p['name']}({p['direction']}:{p['type_label']})" for p in self.nodes[nid]["pins"]
            ],
        }

    def connect(self, from_node: str, from_pin: str, to_node: str, to_pin: str) -> dict:
        """连两个引脚。"""
        # 验证节点存在
        src = self.nodes.get(from_node)
        if src is None:
            return {"ok": False, "error": f"节点不存在: {from_node}"}
        dst = self.nodes.get(to_node)
        if dst is None:
            return {"ok": False, "error": f"节点不存在: {to_node}"}
        # 验证引脚 (方向感知: from_pin 必须是 output, to_pin 必须是 input。
        # 同一名字的引脚 input/output 都有,所以必须按方向过滤)
        src_pin = _find_pin_dir(src, from_pin, "output")
        if src_pin is None:
            outs = [p["name"] for p in src["pins"] if p["direction"] == "output"]
            return {"ok": False, "error": f"{from_node} 没有输出引脚 '{from_pin}'. 输出有: {outs}"}
        dst_pin = _find_pin_dir(dst, to_pin, "input")
        if dst_pin is None:
            ins = [p["name"] for p in dst["pins"] if p["direction"] == "input"]
            return {"ok": False, "error": f"{to_node} 没有输入引脚 '{to_pin}'. 输入有: {ins}"}
        # 类型兼容
        if src_pin["type_label"] != dst_pin["type_label"]:
            return {
                "ok": False,
                "error": f"类型不匹配: {src_pin['type_label']} → {dst_pin['type_label']}",
            }
        # 输入引脚单入
        for ln in self.links:
            if ln["to_node"] == to_node and ln["to_pin"] == to_pin:
                return {"ok": False, "error": f"{to_node}.{to_pin} 已有连线"}
        self.links.append(
            {"from_node": from_node, "from_pin": from_pin, "to_node": to_node, "to_pin": to_pin}
        )
        self._dirty = True
        return {
            "ok": True,
            "action": "connect",
            "link": f"{from_node}.{from_pin} -> {to_node}.{to_pin}",
        }

    def set_param(self, node_id: str, param: str, value) -> dict:
        """修改节点参数。"""
        node = self.nodes.get(node_id)
        if node is None:
            return {"ok": False, "error": f"节点不存在: {node_id}"}
        tmpl = NODE_TEMPLATES.get(node["type"], {})
        pinfo = tmpl.get("params", {}).get(param)
        if pinfo is None:
            return {"ok": False, "error": f"节点 {node['type']} 无参数 '{param}'"}
        node["params"][param] = value
        node["cache"] = None  # 参数变了, 清缓存
        self._dirty = True
        return {"ok": True, "action": "set_param", "node": node_id, "param": param, "value": value}

    def delete_node(self, node_id: str) -> dict:
        if node_id not in self.nodes:
            return {"ok": False, "error": f"节点不存在: {node_id}"}
        del self.nodes[node_id]
        before = len(self.links)
        self.links = [
            ln for ln in self.links if ln["from_node"] != node_id and ln["to_node"] != node_id
        ]
        self._dirty = True
        return {
            "ok": True,
            "action": "delete_pcg_node",
            "id": node_id,
            "removed_links": before - len(self.links),
        }

    def clear(self) -> dict:
        n = len(self.nodes)
        self.nodes.clear()
        self.links.clear()
        self._counter = 0
        self._dirty = True
        return {"ok": True, "action": "clear_pcg_graph", "deleted": n}

    def list_graph(self) -> dict:
        """列出整张图的节点、连线。"""
        nodes_out = []
        for n in self.nodes.values():
            pins_in = [p for p in n["pins"] if p["direction"] == "input"]
            pins_out = [p for p in n["pins"] if p["direction"] == "output"]
            nodes_out.append(
                {
                    "id": n["id"],
                    "type": n["type"],
                    "cls": n.get("cls", ""),
                    "params": n["params"],
                    "inputs": [f"{p['name']}({p['type_label']})" for p in pins_in],
                    "outputs": [f"{p['name']}({p['type_label']})" for p in pins_out],
                }
            )
        return {"ok": True, "action": "list_pcg_graph", "nodes": nodes_out, "links": self.links}

    # ── 执行引擎 ──

    def execute(self, context: dict | None = None) -> dict:
        """执行 PCG 图。

        context 可选: {"scene_actors": [{name, location, rotation, scale}, ...],
                       "global_seed": 42}
        这是 mock 端 — 真 UE 端由 ue_pcg_helper 在引擎里执行真正的 PCG 图。
        """
        ctx = context or {}
        scene_actors = ctx.get("scene_actors", [])
        global_seed = ctx.get("global_seed", 42)

        # 1) 拓扑排序 (Kahn)
        order = _topological_order(self.nodes, self.links)
        if order is None:
            return {"ok": False, "error": "图中存在环路 (PCG 图必须是无环的 DAG)"}

        # 2) 建上游查询表
        upstream = _build_upstream(self.links)

        # 3) 逐节点执行
        for nid in order:
            node = self.nodes[nid]
            tmpl = NODE_TEMPLATES.get(node["type"])
            if tmpl is None:
                continue
            params = node["params"]
            cls = tmpl.get("cls", "")

            try:
                if cls == "input":
                    node["cache"] = _exec_input(node, params, scene_actors, global_seed)
                elif cls == "sampling":
                    src_data = _get_upstream_data(nid, node, upstream, self.nodes)
                    node["cache"] = _exec_sampling(node, params, src_data, global_seed)
                elif cls == "filter":
                    src_data = _get_upstream_data(nid, node, upstream, self.nodes)
                    node["cache"] = _exec_filter(node, params, src_data)
                elif cls == "transform":
                    src_data = _get_upstream_data(nid, node, upstream, self.nodes)
                    node["cache"] = _exec_transform(node, params, src_data)
                elif cls == "spawn":
                    src_data = _get_upstream_data(nid, node, upstream, self.nodes)
                    node["cache"] = _exec_spawn(node, params, src_data)
                elif cls == "combine":
                    # combine 有两个输入 → 从 upstream 找 input_a 和 input_b
                    data_a = _get_named_input(nid, "input_a", upstream, self.nodes)
                    data_b = _get_named_input(nid, "input_b", upstream, self.nodes)
                    node["cache"] = _exec_combine(node, params, data_a, data_b)
                else:
                    node["cache"] = {"type": "error", "error": f"未知节点类别: {cls}"}
            except Exception as e:  # noqa: BLE001
                node["cache"] = {"type": "error", "error": f"{type(e).__name__}: {e}"}

        self._dirty = False

        # 4) 收集输出: 所有 spawn 节点的点云 + 其他无下游的终端节点
        outputs = _collect_outputs(self.nodes, self.links)
        return {
            "ok": True,
            "action": "execute_pcg_graph",
            "node_count": len(order),
            "exec_order": order,
            "outputs": outputs,
        }

    # ── 可视化 ──

    def render(self, width: int = 60, height: int = 20, span: float = 5000.0) -> str:
        """ASCII 俯视图: 把所有 spawn 节点的点云画成俯视图。"""
        # 收集所有 spawn 节点的点
        all_points = []
        for node in self.nodes.values():
            if node.get("cls") != "spawn":
                continue
            cache = node.get("cache")
            if cache and cache.get("type") == "point_cloud":
                for p in cache.get("points", []):
                    all_points.append(p)
        if not all_points:
            return "(PCG 图无 spawn 输出: 加 static_mesh_spawner 节点并执行 run_pcg_graph)"
        grid = [[" "] * width for _ in range(height)]
        for p in all_points:
            x, y = p["location"][0], p["location"][1]
            gx = int((x + span) / (2 * span) * (width - 1))
            gy = int((y + span) / (2 * span) * (height - 1))
            gx = max(0, min(width - 1, gx))
            gy = max(0, min(height - 1, gy))
            grid[gy][gx] = "*"
        border = "+" + "-" * width + "+"
        rows = "\n".join("|" + "".join(r) + "|" for r in grid)
        return f"{border}\n{rows}\n{border}\nPCG 俯视图 ({len(all_points)} 个 spawn 点)"

    def render_stats(self) -> str:
        """每个输出节点的统计摘要。"""
        lines = ["PCG 图输出统计:"]
        for node in self.nodes.values():
            cache = node.get("cache")
            if cache and cache.get("type") == "point_cloud":
                pts = cache.get("points", [])
                stats = PointCloud(pts).stats()
                lines.append(
                    f"  [{node['id']}] ({node['type']}): "
                    f"{stats['count']} 点, "
                    f"密度 {stats.get('density', {}).get('mean', 0):.2f}"
                )
        return "\n".join(lines) if len(lines) > 1 else "(无输出)"


# ═══════════════════════════════════════════════════════════════
# 图算法辅助
# ═══════════════════════════════════════════════════════════════


def _find_pin_dir(node, pin_name, direction):
    """按名字+方向找引脚 (同一名字可能有 input 和 output 两个版本)。"""
    for p in node["pins"]:
        if p["name"] == pin_name and p["direction"] == direction:
            return p
    return None


def _find_pin(node, pin_name):
    """任意方向找引脚 (向后兼容, _find_pin_dir 优先)。"""
    for p in node["pins"]:
        if p["name"] == pin_name:
            return p
    return None


def _topological_order(nodes: dict, links: list) -> list | None:
    """Kahn 算法: 返回拓扑序列表, 有环则 None。"""
    in_degree = dict.fromkeys(nodes, 0)
    adj = {nid: [] for nid in nodes}
    for ln in links:
        if ln["from_node"] in nodes and ln["to_node"] in nodes:
            in_degree[ln["to_node"]] += 1
            adj[ln["from_node"]].append(ln["to_node"])
    q = [nid for nid, d in in_degree.items() if d == 0]
    order = []
    while q:
        nid = q.pop(0)
        order.append(nid)
        for to_nid in adj.get(nid, []):
            in_degree[to_nid] -= 1
            if in_degree[to_nid] == 0:
                q.append(to_nid)
    return order if len(order) == len(nodes) else None


def _build_upstream(links: list) -> dict:
    """{(to_node, to_pin): (from_node, from_pin)}。一个输入引脚最多一条入线。"""
    up = {}
    for ln in links:
        up[(ln["to_node"], ln["to_pin"])] = (ln["from_node"], ln["from_pin"])
    return up


def _get_upstream_data(node_id, node, upstream, nodes) -> dict | None:
    """获取当前节点的上游数据 (默认取第一个 input 引脚连的数据)。"""
    for pin in node["pins"]:
        if pin["direction"] == "input":
            key = (node_id, pin["name"])
            src = upstream.get(key)
            if src:
                src_node = nodes.get(src[0])
                if src_node and src_node.get("cache"):
                    return src_node["cache"]
    return None


def _get_named_input(node_id, pin_name, upstream, nodes) -> dict | None:
    """获取指定名字的输入引脚的上游数据。"""
    src = upstream.get((node_id, pin_name))
    if src:
        src_node = nodes.get(src[0])
        if src_node and src_node.get("cache"):
            return src_node["cache"]
    return None


def _collect_outputs(nodes: dict, links: list) -> list[dict]:
    """收集输出: spawn 节点 + 不被任何下游消费的点云输出节点。"""
    consumed = set()
    for ln in links:
        consumed.add((ln["from_node"], ln["from_pin"]))
    outputs = []
    for nid, node in nodes.items():
        cache = node.get("cache")
        if cache is None or cache.get("type") != "point_cloud":
            continue
        # 所有输出引脚
        for pin in node["pins"]:
            if (
                pin["direction"] == "output"
                and pin["type_label"] == "point_cloud"
                and ((nid, pin["name"]) not in consumed or node.get("cls") == "spawn")
            ):
                pc = (
                    cache
                    if isinstance(cache, PointCloud)
                    else PointCloud(cache.get("points", []))
                )
                outputs.append(
                    {
                        "node_id": nid,
                        "node_type": node["type"],
                        "pin": pin["name"],
                        "stats": pc.stats(),
                        "mesh_path": node["params"].get("mesh_path")
                        if node.get("cls") == "spawn"
                        else None,
                    }
                )
    return outputs


# ═══════════════════════════════════════════════════════════════
# 节点执行函数 (mock 后端)
# ═══════════════════════════════════════════════════════════════


def _exec_input(
    node: dict, params: dict, scene_actors: list, global_seed: int = 42
) -> dict:
    """执行输入节点: get_actor_data / landscape_input / volume_input / spline_input。"""
    ntype = node["type"]

    if ntype == "get_actor_data":
        pts = []
        filt = params.get("actor_filter")
        inc_scale = params.get("include_scale", True)
        for i, a in enumerate(scene_actors):
            if filt and not a.get("name", "").startswith(filt):
                continue
            loc = a.get("location", [0, 0, 0])
            rot = a.get("rotation", [0, 0, 0])
            scl = a.get("scale", [1, 1, 1]) if inc_scale else [1, 1, 1]
            pts.append(_make_point(loc, density=0.5, seed=i, rotation=rot, scale=scl))
        return {"type": "point_cloud", "points": pts}

    if ntype == "landscape_input":
        w = float(params["width"])
        d = float(params["depth"])
        hmin = float(params["height_min"])
        hmax = float(params["height_max"])
        noise = float(params["noise_scale"])
        # seed=0 表示跟随全局种子; 显式给值则以该值为准。
        seed = int(params["seed"]) or global_seed
        # mock 地表: 规则网格的高度场
        res = 50  # 内部分辨率
        heights = []
        for i in range(res):
            row = []
            for j in range(res):
                fx = i / (res - 1) * 2 - 1
                fy = j / (res - 1) * 2 - 1
                h = (
                    hmin
                    + (hmax - hmin)
                    * (
                        0.5
                        + 0.3 * math.sin(fx * 3 + seed * 0.1) * math.cos(fy * 2 + seed * 0.07)
                        + 0.15 * math.sin(fx * 7) * math.sin(fy * 5)
                        + 0.05 * math.cos(fx * 13 + fy * 11)
                    )
                    * noise
                )
                row.append(h)
            heights.append(row)
        return {
            "type": "landscape",
            "width": w,
            "depth": d,
            "height_min": hmin,
            "height_max": hmax,
            "heights": heights,
            "resolution": res,
        }

    if ntype == "volume_input":
        return {
            "type": "volume",
            "shape": params["shape"],
            "location": params["location"],
            "extent": params["extent"],
        }

    if ntype == "spline_input":
        return {"type": "spline", "points": params["points"], "closed": params.get("closed", False)}

    return {"type": "error", "error": f"未知输入节点: {ntype}"}


def _exec_sampling(
    node: dict, params: dict, src_data: dict | None, global_seed: int = 42
) -> dict:
    """执行采样节点。"""
    if src_data is None:
        return {"type": "error", "error": "缺少上游输入数据"}
    ntype = node["type"]
    nid = node["id"]
    # 节点没显式给 seed 时, 用 (global_seed, 节点名) 派生一个稳定值。
    # 拼进 global_seed 是必须的: 否则 global_seed 读了不用, 换它整个图纹丝不动。
    seed = int(params.get("seed", 0)) or _hash_int(f"{global_seed}|{nid}", "seed", 0, 1_000_000)
    # 所有随机源都经由 nid_s, 这样 global_seed / 节点 seed 才真的影响采样结果
    nid_s = f"{seed}|{nid}"

    if ntype == "surface_sampler" and src_data.get("type") == "landscape":
        # 在地表随机撒点
        w = float(src_data["width"])
        d = float(src_data["depth"])
        hmin = src_data["height_min"]
        hmax = src_data["height_max"]
        heights = src_data["heights"]
        res = src_data["resolution"]
        ppsm = float(params.get("points_per_sqm", 0.05))
        # 总点数 = 面积(m²) * 密度
        area_sqm = (w / 100.0) * (d / 100.0)  # cm² → m²
        total = max(1, int(area_sqm * ppsm))
        pts = []
        for i in range(total):
            # 随机位置
            # 随机源必须带 seed: 原来只哈希节点 id, 于是 global_seed 改了
            # 地形却改不动采样点, "全局种子"名存实亡。
            rx = _hash_float(f"{seed}|{nid}", f"x_{i}") * w - w / 2
            ry = _hash_float(f"{seed}|{nid}", f"y_{i}") * d - d / 2
            # 从 height 场插值 (简单双线性)
            fx = (rx + w / 2) / w * (res - 1)
            fy = (ry + d / 2) / d * (res - 1)
            ix, iy = int(fx), int(fy)
            ix = max(0, min(res - 2, ix))
            iy = max(0, min(res - 2, iy))
            tx, ty = fx - ix, fy - iy
            h00 = heights[iy][ix]
            h10 = heights[iy][ix + 1]
            h01 = heights[iy + 1][ix]
            h11 = heights[iy + 1][ix + 1]
            rz = (h00 * (1 - tx) + h10 * tx) * (1 - ty) + (h01 * (1 - tx) + h11 * tx) * ty
            # 坡度代理: 用局部高度梯度作为 density 种子
            grad_x = abs(h10 - h00) + abs(h11 - h01)
            grad_y = abs(h01 - h00) + abs(h11 - h10)
            slope = (grad_x + grad_y) / 2.0 / (hmax - hmin + 1) * 200  # 归一化
            density = max(0.0, min(1.0, 1.0 - slope * 0.8))
            pts.append(_make_point([rx, ry, rz], density=density, seed=i))
        return {"type": "point_cloud", "points": pts}

    if ntype == "volume_sampler" and src_data.get("type") == "volume":
        loc = src_data["location"]
        ext = src_data["extent"]
        shape = src_data["shape"]
        ppcm = float(params.get("points_per_cubic_meter", 0.005))
        vol_m3 = (ext[0] * 2 / 100.0) * (ext[1] * 2 / 100.0) * (ext[2] * 2 / 100.0)
        total = max(1, int(vol_m3 * ppcm))
        pts = []
        for i in range(total):
            if shape == "sphere":
                # 球内随机 (拒绝采样)
                while True:
                    rx = (_hash_float(nid_s, f"sx_{i}") * 2 - 1) * ext[0]
                    ry = (_hash_float(nid_s, f"sy_{i}") * 2 - 1) * ext[1]
                    rz = (_hash_float(nid_s, f"sz_{i}") * 2 - 1) * ext[2]
                    if (rx / ext[0]) ** 2 + (ry / ext[1]) ** 2 + (rz / ext[2]) ** 2 <= 1.0:
                        break
            elif shape == "cylinder":
                while True:
                    rx = (_hash_float(nid_s, f"cx_{i}") * 2 - 1) * ext[0]
                    ry = (_hash_float(nid_s, f"cy_{i}") * 2 - 1) * ext[1]
                    rz = (_hash_float(nid_s, f"cz_{i}") * 2 - 1) * ext[2]
                    if (rx / ext[0]) ** 2 + (ry / ext[1]) ** 2 <= 1.0:
                        break
            else:  # box
                rx = (_hash_float(nid_s, f"bx_{i}") * 2 - 1) * ext[0]
                ry = (_hash_float(nid_s, f"by_{i}") * 2 - 1) * ext[1]
                rz = (_hash_float(nid_s, f"bz_{i}") * 2 - 1) * ext[2]
            pts.append(
                _make_point(
                    [loc[0] + rx, loc[1] + ry, loc[2] + rz],
                    density=_hash_float(nid_s, f"d_{i}"),
                    seed=i,
                )
            )
        return {"type": "point_cloud", "points": pts}

    if ntype == "spline_sampler" and src_data.get("type") == "spline":
        spline_pts = src_data["points"]
        spacing = float(params.get("spacing", 200.0))
        closed = src_data.get("closed", False)
        # 算各段长度
        seg_lens = []
        n_seg = len(spline_pts) - 1
        total_len = 0.0
        for i in range(n_seg):
            dl = _dist3(spline_pts[i], spline_pts[i + 1])
            seg_lens.append(dl)
            total_len += dl
        if closed and len(spline_pts) > 2:
            dl = _dist3(spline_pts[-1], spline_pts[0])
            seg_lens.append(dl)
            total_len += dl
            n_seg += 1
        if total_len < spacing:
            # 至少返回控制点本身
            return {
                "type": "point_cloud",
                "points": [_make_point(p, density=0.5, seed=i) for i, p in enumerate(spline_pts)],
            }
        n_pts = max(1, int(total_len / spacing))
        pts = []
        for i in range(n_pts):
            t = total_len * i / (n_pts - 1) if n_pts > 1 else 0
            # 沿样条插值
            acc = 0.0
            for si in range(n_seg):
                sl = seg_lens[si]
                if acc + sl >= t or si == n_seg - 1:
                    local_t = (t - acc) / sl if sl > 0 else 0
                    local_t = max(0.0, min(1.0, local_t))
                    a = spline_pts[si]
                    b = spline_pts[(si + 1) % len(spline_pts)]
                    loc = [a[j] + (b[j] - a[j]) * local_t for j in range(3)]
                    pts.append(_make_point(loc, density=0.5, seed=i))
                    break
                acc += sl
        return {"type": "point_cloud", "points": pts}

    return {"type": "error", "error": f"采样节点 {ntype} 不支持输入类型 {src_data.get('type')}"}


def _exec_filter(node: dict, params: dict, src_data: dict | None) -> dict:
    """执行过滤节点。"""
    if src_data is None or src_data.get("type") != "point_cloud":
        return {"type": "error", "error": "过滤节点需要 point_cloud 输入"}
    pts = src_data.get("points", [])
    ntype = node["type"]
    invert = params.get("invert", False)

    if ntype == "density_filter":
        lo = float(params.get("lower_bound", 0.0))
        hi = float(params.get("upper_bound", 1.0))

        def pred(p):  # type: ignore[misc]  # 四个 filter 分支互斥, 各自闭包只在本格生效
            ok = lo <= p.get("density", 0.5) <= hi
            return ok if not invert else not ok
    elif ntype == "height_filter":
        min_z = params.get("min_z")
        max_z = params.get("max_z")

        def pred(p):
            z = p["location"][2]
            ok = True
            if min_z is not None:
                ok = ok and z >= float(min_z)
            if max_z is not None:
                ok = ok and z <= float(max_z)
            return ok if not invert else not ok

    elif ntype == "bounds_filter":
        bmin = params["bounds_min"]
        bmax = params["bounds_max"]

        def pred(p):  # type: ignore[misc]  # 同上, 互斥分支
            loc = p["location"]
            ok = all(bmin[k] <= loc[k] <= bmax[k] for k in range(3))
            return ok if not invert else not ok

    elif ntype == "slope_filter":
        threshold = float(params.get("max_density_as_flat", 0.5))

        def pred(p):
            ok = p.get("density", 0.5) >= threshold
            return ok if not invert else not ok

    else:
        return {"type": "error", "error": f"未知过滤节点: {ntype}"}

    kept = [p for p in pts if pred(p)]
    return {"type": "point_cloud", "points": kept}


def _exec_transform(node: dict, params: dict, src_data: dict | None) -> dict:
    """执行变换节点。"""
    if src_data is None or src_data.get("type") != "point_cloud":
        return {"type": "error", "error": "变换节点需要 point_cloud 输入"}
    pts = src_data.get("points", [])
    ntype = node["type"]
    nid = node["id"]
    out = []

    if ntype == "transform_points":
        omin = params.get("offset_min", [0, 0, 0])
        omax = params.get("offset_max", [0, 0, 0])
        rmin = params.get("rotation_min", [0, 0, 0])
        rmax = params.get("rotation_max", [0, 0, 0])
        smin = float(params.get("scale_min", 1.0))
        smax = float(params.get("scale_max", 1.0))
        absolute = params.get("absolute", False)
        for i, p in enumerate(pts):
            np = {**p}
            ox = _hash_float(nid, f"ox_{i}") * (omax[0] - omin[0]) + omin[0]
            oy = _hash_float(nid, f"oy_{i}") * (omax[1] - omin[1]) + omin[1]
            oz = _hash_float(nid, f"oz_{i}") * (omax[2] - omin[2]) + omin[2]
            if absolute:
                np["location"] = [float(x) for x in omin]
                np["rotation"] = [float(x) for x in rmin]
                np["scale"] = [smin, smin, smin]
            else:
                np["location"] = [p["location"][j] + [ox, oy, oz][j] for j in range(3)]
                rx = _hash_float(nid, f"rx_{i}") * (rmax[0] - rmin[0]) + rmin[0]
                ry = _hash_float(nid, f"ry_{i}") * (rmax[1] - rmin[1]) + rmin[1]
                rz = _hash_float(nid, f"rz_{i}") * (rmax[2] - rmin[2]) + rmin[2]
                s = _hash_float(nid, f"s_{i}") * (smax - smin) + smin
                np["rotation"] = [p["rotation"][j] + [rx, ry, rz][j] for j in range(3)]
                np["scale"] = [x * s for x in p["scale"]]
            out.append(np)

    elif ntype == "density_noise":
        amp = float(params.get("amplitude", 0.3))
        freq = float(params.get("frequency", 1.0))
        # 噪声按空间位置生成, 这样 frequency 才有的可调: 之前是纯哈希,
        # frequency 读了不用, 参数是摆设 —— 而"模拟地形坡度/植被密度"
        # 本来就该是空间上成片的, 不是每个点独立的椒盐噪声。
        for i, p in enumerate(pts):
            np = {**p}
            loc = p.get("location") or [0.0, 0.0, 0.0]
            cell = (int(loc[0] // 1000.0), int(loc[1] // 1000.0))  # 1m 网格
            base = _hash_float(nid, f"dn_{cell[0]}_{cell[1]}")
            jitter = _hash_float(nid, f"dnj_{i}") * 2 - 1
            wave = math.sin(base * math.tau + freq * (cell[0] + cell[1]))
            noise_val = (wave * 0.75 + jitter * 0.25) * amp
            np["density"] = max(0.0, min(1.0, p.get("density", 0.5) + noise_val))
            out.append(np)

    elif ntype == "bounds_modifier":
        bmin = params["bounds_min"]
        bmax = params["bounds_max"]
        for p in pts:
            np = {
                **p,
                "bounds_min": [float(x) for x in bmin],
                "bounds_max": [float(x) for x in bmax],
            }
            out.append(np)

    elif ntype == "jitter":
        amount = float(params.get("amount", 100.0))
        for i, p in enumerate(pts):
            np = {**p}
            jx = (_hash_float(nid, f"jx_{i}") * 2 - 1) * amount
            jy = (_hash_float(nid, f"jy_{i}") * 2 - 1) * amount
            jz = (_hash_float(nid, f"jz_{i}") * 2 - 1) * amount * 0.3
            np["location"] = [p["location"][0] + jx, p["location"][1] + jy, p["location"][2] + jz]
            out.append(np)
    else:
        return {"type": "error", "error": f"未知变换节点: {ntype}"}

    return {"type": "point_cloud", "points": out}


def _exec_spawn(node: dict, params: dict, src_data: dict | None) -> dict:
    """执行 spawn 节点: 标记 mesh 信息。真 UE 端会真正生成 Actor。"""
    if src_data is None or src_data.get("type") != "point_cloud":
        return {"type": "error", "error": "spawn 节点需要 point_cloud 输入"}
    pts = src_data.get("points", [])
    mesh = params.get("mesh_path", "/Engine/BasicShapes/Cube.Cube")
    threshold = float(params.get("density_threshold", 0.0))
    mult = float(params.get("scale_multiplier", 1.0))
    out = []
    for p in pts:
        if p.get("density", 0.5) < threshold:
            continue
        np = {**p, "_mesh": mesh}
        if mult != 1.0:
            np["scale"] = [x * mult for x in np["scale"]]
        out.append(np)
    return {"type": "point_cloud", "points": out}


def _exec_combine(node: dict, params: dict, data_a: dict | None, data_b: dict | None) -> dict:
    """执行合并节点。"""
    ntype = node["type"]
    pts_a = data_a.get("points", []) if data_a and data_a.get("type") == "point_cloud" else []
    pts_b = data_b.get("points", []) if data_b and data_b.get("type") == "point_cloud" else []

    if ntype == "union":
        r = float(params.get("merge_radius", 50.0))
        # A 全部保留, B 中离 A 任一点 > r 的也加进来
        out = list(pts_a)
        for pb in pts_b:
            too_close = any(_dist3(pb["location"], pa["location"]) < r for pa in pts_a)
            if not too_close:
                out.append(pb)
        return {"type": "point_cloud", "points": out}

    if ntype == "difference":
        r = float(params.get("exclusion_radius", 200.0))
        out = [
            pa
            for pa in pts_a
            if not any(_dist3(pa["location"], pb["location"]) < r for pb in pts_b)
        ]
        return {"type": "point_cloud", "points": out}

    if ntype == "intersection":
        r = float(params.get("intersect_radius", 200.0))
        out = [
            pa for pa in pts_a if any(_dist3(pa["location"], pb["location"]) < r for pb in pts_b)
        ]
        return {"type": "point_cloud", "points": out}

    return {"type": "error", "error": f"未知合并节点: {ntype}"}


# ═══════════════════════════════════════════════════════════════
# 场景桥接: 从 MockScene 的 actors 列表构建 PCG 输入
# ═══════════════════════════════════════════════════════════════


def scene_actors_from_mock(scene) -> list[dict]:
    """从 mock_ue.MockScene 提取 actors 列表, 供 PCG 的 get_actor_data 使用。"""
    actors = []
    for a in scene.actors.values():
        actors.append(
            {
                "name": a["name"],
                "location": a.get("location", [0, 0, 0]),
                "rotation": a.get("rotation", [0, 0, 0]),
                "scale": a.get("scale", [1, 1, 1]),
            }
        )
    return actors


# ═══════════════════════════════════════════════════════════════
# 自检
# ═══════════════════════════════════════════════════════════════


def _selfcheck() -> int:
    """离线自检: 跑一张完整的 PCG 图 → 验证执行结果。"""
    g = PCGGraph()

    # 1) 建图: landscape → surface_sampler → density_noise → slope_filter → transform → spawn
    r = g.add_node(
        "landscape_input",
        "terrain",
        {"width": 10000, "depth": 10000, "height_min": 0, "height_max": 500, "noise_scale": 1.0},
    )
    assert r["ok"], f"加 terrain 失败: {r}"
    print(f"✅ 加 landscape_input: {r['id']}")

    r = g.add_node("surface_sampler", "sampler", {"points_per_sqm": 0.04, "seed": 42})
    assert r["ok"]
    print(f"✅ 加 surface_sampler: {r['id']}")

    r = g.add_node("density_noise", "noise", {"amplitude": 0.4, "frequency": 1.5, "seed": 77})
    assert r["ok"]
    print(f"✅ 加 density_noise: {r['id']}")

    r = g.add_node("slope_filter", "flat_only", {"max_density_as_flat": 0.35, "invert": False})
    assert r["ok"]
    print(f"✅ 加 slope_filter: {r['id']}")

    r = g.add_node(
        "transform_points",
        "vary",
        {
            "offset_min": [-30, -30, 0],
            "offset_max": [30, 30, 0],
            "rotation_min": [0, 0, 0],
            "rotation_max": [0, 360, 0],
        },
    )
    assert r["ok"]
    print(f"✅ 加 transform_points: {r['id']}")

    r = g.add_node(
        "static_mesh_spawner",
        "trees",
        {"mesh_path": "/Game/Forest/Oak.Oak", "density_threshold": 0.2},
    )
    assert r["ok"]
    print(f"✅ 加 static_mesh_spawner: {r['id']}")

    # 2) 连线
    r = g.connect("terrain", "landscape", "sampler", "source")
    assert r["ok"], f"连线失败: {r}"
    print(f"✅ 连线: {r['link']}")

    for src, dst in [
        ("sampler", "noise"),
        ("noise", "flat_only"),
        ("flat_only", "vary"),
        ("vary", "trees"),
    ]:
        r = g.connect(src, "points", dst, "points")
        assert r["ok"], f"连线 {src}→{dst} 失败: {r}"
        print(f"✅ 连线: {r['link']}")

    # 3) 执行
    result = g.execute()
    assert result["ok"], f"执行失败: {result}"
    assert result["node_count"] == 6
    print(f"✅ 执行: 6 节点按序 {result['exec_order']}")
    outputs = result["outputs"]
    assert len(outputs) >= 1, "应有至少 1 个输出"
    tree_out = outputs[-1]  # spawner 的输出
    assert tree_out["node_type"] == "static_mesh_spawner"
    n_pts = tree_out["stats"]["count"]
    assert 10 <= n_pts <= 200, f"预期 10~200 棵树, 实际 {n_pts}"
    print(f"✅ 产出: {n_pts} 个 spawn 点 (过滤+噪声后)")

    # 4) 验证确定性: 同一张图再执行一次, 产出相同
    g2 = PCGGraph()
    # 重新建等价的图 (参数必须和 g 完全一致)
    for nt, nm, ps in [
        (
            "landscape_input",
            "terrain",
            {"width": 10000, "depth": 10000, "height_min": 0, "height_max": 500},
        ),
        ("surface_sampler", "sampler", {"points_per_sqm": 0.04, "seed": 42}),
        ("density_noise", "noise", {"amplitude": 0.4, "frequency": 1.5, "seed": 77}),
        ("slope_filter", "flat_only", {"max_density_as_flat": 0.35}),
        (
            "transform_points",
            "vary",
            {
                "offset_min": [-30, -30, 0],
                "offset_max": [30, 30, 0],
                "rotation_min": [0, 0, 0],
                "rotation_max": [0, 360, 0],
            },
        ),
        (
            "static_mesh_spawner",
            "trees",
            {"mesh_path": "/Game/Forest/Oak.Oak", "density_threshold": 0.2},
        ),
    ]:
        g2.add_node(nt, nm, ps)
    for a, b in [
        ("terrain", "sampler"),
        ("sampler", "noise"),
        ("noise", "flat_only"),
        ("flat_only", "vary"),
        ("vary", "trees"),
    ]:
        g2.connect(
            a,
            "landscape" if a == "terrain" else "points",
            b,
            "source" if b == "sampler" else "points",
        )
    r2 = g2.execute()
    o2 = r2["outputs"]
    assert len(o2) == len(outputs), "两次执行输出数不一致"
    assert o2[-1]["stats"]["count"] == n_pts, f"确定性失败: {n_pts} vs {o2[-1]['stats']['count']}"
    print(f"✅ 确定性: 两次执行产出 {n_pts} 点完全一致")

    # 5) 验证 combine 节点
    g3 = PCGGraph()
    g3.add_node("get_actor_data", "actors")
    g3.add_node("volume_input", "vol", {"location": [0, 0, 0], "extent": [3000, 3000, 1000]})
    g3.add_node("volume_sampler", "vol_pts", {"points_per_cubic_meter": 0.01, "seed": 1})
    g3.add_node("difference", "diff", {"exclusion_radius": 500})
    g3.add_node("static_mesh_spawner", "spawn")
    # get_actor_data 不需要输入, volume_sampler 需要 volume_input
    g3.connect("vol", "volume", "vol_pts", "source")
    # difference 的两个输入
    g3.connect("vol_pts", "points", "diff", "input_a")
    # actors 没有 actor 数据 → 给个 scene
    ctx = {
        "scene_actors": [
            {"name": "cube_1", "location": [100, 100, 0]},
            {"name": "cube_2", "location": [500, 500, 0]},
            {"name": "sphere_1", "location": [-200, -200, 0]},
        ]
    }
    # 先跑 actors 节点
    actors_node = g3.nodes["actors"]
    actors_node["cache"] = _exec_input(actors_node, actors_node["params"], ctx["scene_actors"])
    # 连线 actors → diff input_b
    g3.connect("actors", "points", "diff", "input_b")
    r3 = g3.execute(ctx)
    assert r3["ok"], f"combine 图执行失败: {r3}"
    print(
        f"✅ combine (difference): {r3['outputs'][-1]['stats']['count']} 点 "
        f"(排除靠近 actors 的区域)"
    )

    # 6) spline 沿路布点
    g4 = PCGGraph()
    g4.add_node(
        "spline_input",
        "path",
        {"points": [[0, 0, 0], [1000, 500, 0], [2000, -300, 0], [3000, 0, 0]]},
    )
    g4.add_node("spline_sampler", "posts", {"spacing": 300})
    g4.add_node("static_mesh_spawner", "lights", {"mesh_path": "/Game/City/Lamp.Lamp"})
    g4.connect("path", "spline", "posts", "source")
    g4.connect("posts", "points", "lights", "points")
    r4 = g4.execute()
    assert r4["ok"], f"spline 图执行失败: {r4}"
    n_lights = r4["outputs"][-1]["stats"]["count"]
    assert 5 <= n_lights <= 20, f"预期 5~20 盏灯, 实际 {n_lights}"
    print(f"✅ spline 沿路布点: {n_lights} 盏路灯")

    # 7) 类型不匹配拒绝
    r = g4.connect("path", "spline", "lights", "points")
    assert not r["ok"], "类型不匹配应该被拒!"
    print(f"✅ 类型不匹配拒绝: {r['error']}")

    # 8) 引脚不存在拒绝
    r = g4.connect("posts", "nope", "lights", "points")
    assert not r["ok"]
    print(f"✅ 引脚不存在拒绝: {r['error']}")

    # 9) 环路检测
    g5 = PCGGraph()
    g5.add_node("density_noise", "a")
    g5.add_node("density_noise", "b")
    g5.connect("a", "points", "b", "points")
    g5.connect("b", "points", "a", "points")
    r5 = g5.execute()
    assert not r5["ok"] and "环" in r5.get("error", "")
    print(f"✅ 环路检测: {r5['error']}")

    # 10) ASCII 俯视图
    viz = g.render()
    assert "PCG 俯视图" in viz
    print(f"✅ ASCII 俯视图: {len(g.nodes[g.nodes['trees']['id']]['cache']['points'])} 个点")

    # 11) global_seed 必须真的生效。
    #     之前 ctx["global_seed"] 读进来就没人用, 而且 landscape_input 的默认
    #     seed 写死 42, 导致换 global_seed 整个图纹丝不动 —— 一个"看起来有、
    #     实际是死的"参数。
    def _seeded(seed: int) -> list:
        gg = PCGGraph()
        gg.add_node("landscape_input", "t", {"width": 5000, "depth": 5000})
        gg.add_node("surface_sampler", "s", {"points_per_sqm": 0.01})
        gg.connect("t", "landscape", "s", "source")
        r = gg.execute({"global_seed": seed})
        assert r["ok"] and r["outputs"], r
        # 比原始采样点而不是 stats 汇总: stats 里的 count/x_range 可能恰好相同,
        # 掩盖"点其实没动"的情况（第一版修复就栽在这）。
        return [(round(p["location"][0], 6), round(p["location"][1], 6))
                for p in gg.nodes["s"]["cache"]["points"]]

    p1, p2, p1_again = _seeded(1), _seeded(2), _seeded(1)
    assert p1 == p1_again, "同一种子必须可复现"
    assert p1 != p2, "换 global_seed 必须改变采样点, 否则该参数是死的"
    print("✅ global_seed 生效: 同种子可复现, 换种子结果变化")

    # 12) density_noise 的 frequency 必须真的影响结果。
    #     之前是纯哈希噪声, frequency 读了不用 —— 参数摆设。
    def _noised(freq: float) -> list:
        gg = PCGGraph()
        gg.add_node("landscape_input", "t", {"width": 6000, "depth": 6000})
        gg.add_node("surface_sampler", "s", {"points_per_sqm": 0.02})
        gg.add_node("density_noise", "n", {"amplitude": 0.4, "frequency": freq})
        gg.connect("t", "landscape", "s", "source")
        gg.connect("s", "points", "n", "points")
        r = gg.execute({"global_seed": 7})
        assert r["ok"], r
        return [round(p["density"], 6) for p in gg.nodes["n"]["cache"]["points"]]

    d_low, d_high, d_same = _noised(0.2), _noised(4.0), _noised(0.2)
    assert d_low == d_same, "同 frequency 必须可复现"
    assert d_low != d_high, "换 frequency 必须改变密度分布, 否则该参数是摆设"
    print("✅ density_noise.frequency 生效: 同值可复现, 换值结果变化")

    print("\nPCG 模型自检 12/12 通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(_selfcheck())
