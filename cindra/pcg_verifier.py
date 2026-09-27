"""pcg_verifier —— PCG 图的验证闭环。

和 verifier.py 对应但针对 PCG 场景:
  - 图编辑验证: 每次 add/connect/delete/set_param 后读回图结构, 确认操作生效
  - 执行验证 (mock): 对比 run_pcg_graph 前后的输出节点统计, 确认执行非 no-op
  - 执行验证 (ue): 对比 run_pcg_graph 前后的场景快照 (actor count 对账),
    复用 verifier.py 的 take_snapshot 和 diff 机制

原则 (同 verifier): 宁可放过不误杀, 只抓确定的"静默失败"。
"""
from __future__ import annotations

# PCG 中会改图结构或产生场景副作用的工具
MUTATING_PCG_TOOLS = {
    "add_pcg_node", "connect_pcg_pins", "set_pcg_param",
    "delete_pcg_node", "run_pcg_graph", "clear_pcg_graph",
}


def graph_snapshot(graph) -> dict | None:
    """拍一张图结构的快照: 节点 id 集合 + 连线集合。"""
    try:
        nodes = {nid: n["type"] for nid, n in graph.nodes.items()}
        links = {(ln["from_node"], ln["from_pin"],
                  ln["to_node"], ln["to_pin"]) for ln in graph.links}
        return {"nodes": nodes, "links": links}
    except Exception:
        return None


def graph_diff(before: dict | None, after: dict | None) -> dict:
    """计算图结构的前后差异。"""
    if before is None or after is None:
        return {"nodes_added": [], "nodes_removed": [], "links_added": [], "links_removed": []}
    nodes_added = [n for n in after["nodes"] if n not in before["nodes"]]
    nodes_removed = [n for n in before["nodes"] if n not in after["nodes"]]
    links_added = [ln for ln in after["links"] if ln not in before["links"]]
    links_removed = [ln for ln in before["links"] if ln not in after["links"]]
    return {"nodes_added": nodes_added, "nodes_removed": nodes_removed,
            "links_added": links_added, "links_removed": links_removed}


def verify_graph_edit(tool: str, args: dict, result: dict,
                      before: dict | None, after: dict | None) -> tuple[bool, str]:
    """按图形编辑操作类型, 用读回的结构 diff 对账。"""
    if not result.get("ok", True):
        return True, "工具已自报失败, 无需对账"

    # 快照拿不到时降级成空 dict: graph_diff 本身能吃 None, 但下面按节点/连线
    # 对账的地方直接 after.get(...) / before["links"], 传 None 会 TypeError,
    # 报出来的错还跟"图形校验失败"毫无关系。
    before = before or {}
    after = after or {}
    graph_diff(before, after)

    if tool == "add_pcg_node":
        # 确认节点真的加进去了
        nid = result.get("id")
        if nid is None or nid not in after.get("nodes", {}):
            return False, f"声称加了节点 {nid}, 但图里没有它"
        return True, f"节点 {nid} 已确认在图里"

    if tool == "connect_pcg_pins":
        # 确认连线真的在了
        from_node = args.get("from_node")
        from_pin = args.get("from_pin")
        to_node = args.get("to_node")
        to_pin = args.get("to_pin")
        expected = (from_node, from_pin, to_node, to_pin)
        if expected not in after.get("links", set()):
            return False, f"声称连线 {from_node}.{from_pin} -> {to_node}.{to_pin}, 但图里没有"
        return True, "连线确认"

    if tool == "delete_pcg_node":
        nid = args.get("node_id")
        if nid in after.get("nodes", {}):
            return False, f"声称删了节点 {nid}, 但它还在图里"
        return True, f"节点 {nid} 已确认被删"

    if tool == "set_pcg_param":
        # set_param 本身返回了设置后的值, 很难直接验证; 对 mock 是靠谱的自己确认。
        # verifier 不做额外检查, 靠 run_pcg_graph 时的执行结果验证。
        return True, "参数变更 (执行时对账最终产出)"

    if tool == "clear_pcg_graph":
        if len(after.get("nodes", {})) > 0:
            return False, "声称清空但图里还有节点"
        return True, "图已清空确认"

    return True, "非图编辑类工具, 跳过对账"


def verify_execution(result: dict, before_graph: dict | None) -> tuple[bool, str]:
    """校验 run_pcg_graph 的产出。

    before_graph: 执行前的快照 (已不相关, 这里留下的主要是未来扩展占位)。
    核心是验证执行结果本身的一致性: node_count 对应的节点是否真的在 exec_order 里、
    每个 output 的 stats 是否合法。
    """
    if not result.get("ok", True):
        return True, "执行已自报失败"

    node_count = result.get("node_count", 0)
    exec_order = result.get("exec_order", [])
    outputs = result.get("outputs", [])

    if node_count != len(exec_order):
        return False, f"node_count={node_count} 但 exec_order 长度={len(exec_order)}"

    # 检查输出: 每个 output 必须有 node_id/node_type/stats
    for o in outputs:
        if not o.get("node_id") or not o.get("stats"):
            return False, f"输出节点 {o} 缺少 node_id 或 stats"

    # 如果有 spawn 节点 → 产出必须 > 0 (否则可能是管线调参没调好)
    # 注意: 这不是硬错误, 而是可疑信号 —— 交给 agent 自行判断
    spawn_outputs = [o for o in outputs if o.get("node_type") == "static_mesh_spawner"]
    total_spawn = sum(o["stats"].get("count", 0) for o in spawn_outputs)
    if spawn_outputs and total_spawn == 0:
        return True, f"执行完成但 spawn 产出为 0 ({len(exec_order)} 节点都跑了); agent 应调参重试"

    return True, f"执行完成: {node_count} 节点, {total_spawn} 个 spawn 点"


# ═══════════════════════════════════════════════════════════════
# 和 verifier.py 的场景快照协同 (真 UE 后端用)
# ═══════════════════════════════════════════════════════════════


def execute_scene_verify(tool: str, scene_before, scene_after,
                          exec_result: dict) -> tuple[bool, str]:
    """真 UE 后端: run_pcg_graph 执行后会 spawn Actor → 用场景快照对账。

    scene_before/after 是 verifier.take_snapshot() 的返回值 (name → actor dict)。
    根据 exec_result 里 spawn 节点的点云统计, 验证场景里 actor 数量是否增加了对应数量。

    和 verifier 的 diff_snapshots + hard_check 同原理: 不信 PCG 执行声称的 ok,
    要亲眼在场景快照里看到多了对应数量的 mesh actor。
    """
    if tool != "run_pcg_graph":
        return True, "非执行类工具"

    if not exec_result.get("ok"):
        return True, "PCG 执行已自报失败"

    if scene_before is None or scene_after is None:
        return True, "快照不可用, 跳过场景级校验 (agent 可用 inspect_viewport 替代)"

    # 从执行结果拿到预期的 spawn 点总数
    expected = 0
    spawned_node = None
    for o in exec_result.get("outputs", []):
        if o.get("node_type") == "static_mesh_spawner":
            expected += o["stats"].get("count", 0)
            spawned_node = o["node_id"]

    if expected == 0:
        # 没有 spawn 节点 → 场景不应有变化
        added = [n for n in scene_after if n not in scene_before]
        if added:
            return False, f"PCG 图没有 spawn 节点, 但场景多了 {len(added)} 个 actor: {added}"
        return True, "无 spawn 节点, 场景无变化 (符合预期)"

    # 有 spawn 节点 → 验证新增 actor 数量
    added = [n for n in scene_after if n not in scene_before]
    actual = len(added)
    if actual == 0:
        return False, (f"声称 {spawned_node} 产了 {expected} 个 spawn 点, "
                       "但场景没多出任何 actor (静默失败!)")
    if actual < expected * 0.8:
        return False, (f"{spawned_node} 声称 {expected} 个 spawn 点, "
                       f"但场景只多了 {actual} 个 actor (不足 80%)")
    return True, f"场景新增 {actual} 个 actor (预期 ≥{int(expected * 0.8)}), 执行生效"
