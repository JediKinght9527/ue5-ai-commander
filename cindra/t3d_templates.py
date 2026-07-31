"""t3d_templates —— 蓝图 T3D 子图的 mock 实现。

Autonomix 的核心创新: 不逐节点 add_node->connect->connect, 而是把常见节点组合
用结构化意图描述一次性注入, 生成节点 + 自动连线。这比逐节点 API 快得多,
agent 只需描述"我要什么逻辑", 工具负责算节点和连线。

真 UE 端会注入真正的 T3D 文本 (UE 原生蓝图复制粘贴格式),
本文件是 mock 端 —— 把意图描述翻译成 blueprint_model.BlueprintGraph 的
节点/连线。对外工具接口完全一致 (inject_blueprint_t3d),
agent 不关心底层是 mock 翻译还是 T3D 注入。

自检: python3 -m cindra.t3d_templates
"""
from __future__ import annotations

import json
from typing import Any


# ═══════════════════════════════════════════════════════════════
# 模板库: 常见蓝图逻辑组合
# ═══════════════════════════════════════════════════════════════

# 每个模板: { nodes: [(type, id), ...], links: [(from_id, from_pin, to_id, to_pin), ...],
#              params: {param_name: {type, desc, default}} }
# agent 调用: inject_blueprint_t3d(template="event_print", params={in_string: "hello"})

TEMPLATES: dict[str, dict] = {
    # ── 事件 → 打印 ──
    "event_print": {
        "description": "事件触发时打印一段文字 (BeginPlay 时在屏幕/日志打印)。最常用的 hello world。",
        "nodes": [
            ("Event_BeginPlay", "event"),
            ("PrintString", "print"),
        ],
        "links": [
            ("event", "then", "print", "exec"),
        ],
        "params": {
            "in_string": {"type": "string", "desc": "要打印的文字", "default": "Hello from Cindra"},
        },
        "param_bindings": {
            "in_string": [("print", "InString")],
        },
    },
    "event_print_tick": {
        "description": "每帧打印一段文字 (Tick 驱动, 注意频率很高)。",
        "nodes": [
            ("Event_Tick", "tick"),
            ("PrintString", "print"),
        ],
        "links": [
            ("tick", "then", "print", "exec"),
        ],
        "params": {
            "in_string": {"type": "string", "desc": "要打印的文字", "default": "Tick"},
        },
        "param_bindings": {
            "in_string": [("print", "InString")],
        },
    },

    # ── 事件 → 延迟 → 打印 ──
    "delayed_print": {
        "description": "BeginPlay N 秒后在屏幕上打印文字。",
        "nodes": [
            ("Event_BeginPlay", "event"),
            ("Delay", "delay"),
            ("PrintString", "print"),
        ],
        "links": [
            ("event", "then", "delay", "exec"),
            ("delay", "Completed", "print", "exec"),
        ],
        "params": {
            "duration": {"type": "float", "desc": "延迟秒数", "default": 2.0},
            "in_string": {"type": "string", "desc": "要打印的文字", "default": "Delayed"},
        },
        "param_bindings": {
            "duration": [("delay", "Duration")],
            "in_string": [("print", "InString")],
        },
    },

    # ── 分支打印 ──
    "branch_print": {
        "description": "事件触发时根据条件分支打印不同文字 (True→文字A, False→文字B)。",
        "nodes": [
            ("Event_BeginPlay", "event"),
            ("Branch", "branch"),
            ("PrintString", "print_true"),
            ("PrintString", "print_false"),
        ],
        "links": [
            ("event", "then", "branch", "exec"),
            ("branch", "True", "print_true", "exec"),
            ("branch", "False", "print_false", "exec"),
        ],
        "params": {
            "condition": {"type": "bool", "desc": "分支条件", "default": True},
            "true_text": {"type": "string", "desc": "True 时打印的文字", "default": "YES"},
            "false_text": {"type": "string", "desc": "False 时打印的文字", "default": "NO"},
        },
        "param_bindings": {
            "condition": [("branch", "Condition")],
            "true_text": [("print_true", "InString")],
            "false_text": [("print_false", "InString")],
        },
    },

    # ── 比较 → 分支 ──
    "compare_branch_print": {
        "description": "两个浮点数比较大小，结果决定打印哪句话。A > B 打印前者文字，否则打印后者。",
        "nodes": [
            ("Event_BeginPlay", "event"),
            ("Greater_FloatFloat", "greater"),
            ("Branch", "branch"),
            ("PrintString", "print_true"),
            ("PrintString", "print_false"),
        ],
        "links": [
            ("event", "then", "branch", "exec"),
            ("greater", "ReturnValue", "branch", "Condition"),
            ("branch", "True", "print_true", "exec"),
            ("branch", "False", "print_false", "exec"),
        ],
        "params": {
            "value_a": {"type": "float", "desc": "比较值 A", "default": 100.0},
            "value_b": {"type": "float", "desc": "比较值 B", "default": 50.0},
            "true_text": {"type": "string", "desc": "A > B 时打印的文字", "default": "A is greater"},
            "false_text": {"type": "string", "desc": "A <= B 时打印的文字", "default": "A is not greater"},
        },
        "param_bindings": {
            "value_a": [("greater", "A")],
            "value_b": [("greater", "B")],
            "true_text": [("print_true", "InString")],
            "false_text": [("print_false", "InString")],
        },
    },

    # ── Sequence 并行 ──
    "sequence_dual": {
        "description": "事件触发时同时做两件事 (Then0 和 Then1 各连一个 PrintString)。",
        "nodes": [
            ("Event_BeginPlay", "event"),
            ("Sequence", "seq"),
            ("PrintString", "print_a"),
            ("PrintString", "print_b"),
        ],
        "links": [
            ("event", "then", "seq", "exec"),
            ("seq", "Then0", "print_a", "exec"),
            ("seq", "Then1", "print_b", "exec"),
        ],
        "params": {
            "text_a": {"type": "string", "desc": "第一条文字", "default": "First"},
            "text_b": {"type": "string", "desc": "第二条文字", "default": "Second"},
        },
        "param_bindings": {
            "text_a": [("print_a", "InString")],
            "text_b": [("print_b", "InString")],
        },
    },

    # ── Tick 驱动 + 加法 ──
    "tick_counter": {
        "description": "每帧 Tick 时把两个浮点数加起来打印 (展示数据流: Tick→Add→PrintString)。",
        "nodes": [
            ("Event_Tick", "tick"),
            ("Add_FloatFloat", "add"),
            ("PrintString", "print"),
        ],
        "links": [
            ("tick", "then", "print", "exec"),
        ],
        "params": {
            "value_a": {"type": "float", "desc": "加数 A", "default": 1.0},
            "value_b": {"type": "float", "desc": "加数 B", "default": 2.0},
        },
        "param_bindings": {
            "value_a": [("add", "A")],
            "value_b": [("add", "B")],
        },
    },
}


# ═══════════════════════════════════════════════════════════════
# 注入引擎: 模板 → BlueprintGraph
# ═══════════════════════════════════════════════════════════════


def inject(graph, template_name: str, params: dict[str, Any] | None = None,
           placeholder_guids: dict[str, Any] | None = None) -> dict:
    """把一个模板注入到 BlueprintGraph 里。

    参数:
      graph:          BlueprintGraph 实例
      template_name:  模板名 (event_print / branch_print / ...)
      params:         参数覆盖值 {param_name: value}
      placeholder_guids: 可选, GUID 占位→真实值映射 (mock 端忽略, 真 UE 端使用)

    返回: {ok, action, template, nodes_added, links_created}
    """
    tmpl = TEMPLATES.get(template_name)
    if tmpl is None:
        return {"ok": False, "error":
                f"未知模板: {template_name}. 可用: {list(TEMPLATES)}"}
    params = params or {}

    # 1) 合并参数: 取用户传入的, 缺失用默认值
    merged = {}
    for pname, pinfo in tmpl.get("params", {}).items():
        merged[pname] = params.get(pname, pinfo["default"])

    # 2) 加节点 (模板里每个逻辑 id 加一次)
    id_map = {}  # template_id → real_graph_id
    for node_type, tpl_id in tmpl["nodes"]:
        r_json = graph.bp_add_node(node_type)
        r = json.loads(r_json) if isinstance(r_json, str) else r_json
        if r.get("ok"):
            id_map[tpl_id] = r["id"]

    # 3) 连线
    links_ok = 0
    for from_tid, from_pin, to_tid, to_pin in tmpl["links"]:
        from_id = id_map.get(from_tid)
        to_id = id_map.get(to_tid)
        if from_id and to_id:
            r_json = graph.bp_connect(from_id, from_pin, to_id, to_pin)
            r = json.loads(r_json) if isinstance(r_json, str) else r_json
            if r.get("ok"):
                links_ok += 1

    # 4) 绑定参数: 把 param value 设到对应节点的 pin 上
    # data 引脚的值在 mock 端存为 graph 里节点的 "default" 字段
    bindings = tmpl.get("param_bindings", {})
    for pname, pinfo in tmpl.get("params", {}).items():
        pin_bindings = bindings.get(pname, [])
        for target_tid, target_pin in pin_bindings:
            node_id = id_map.get(target_tid)
            if node_id and node_id in graph.nodes:
                graph.nodes[node_id].setdefault("defaults", {})[target_pin] = merged[pname]

    return {"ok": True, "action": "inject_t3d",
            "template": template_name,
            "nodes_added": len(id_map),
            "links_created": links_ok,
            "params_used": merged}


# ═══════════════════════════════════════════════════════════════
# 模板列表工具
# ═══════════════════════════════════════════════════════════════


def list_templates() -> dict:
    """返回所有可用模板的名称和描述 (给 agent 调用 list_blueprint_templates)。"""
    out = {}
    for name, tmpl in TEMPLATES.items():
        out[name] = {
            "description": tmpl["description"],
            "params": {pn: {"type": pi["type"], "desc": pi["desc"], "default": pi["default"]}
                       for pn, pi in tmpl.get("params", {}).items()},
            "node_count": len(tmpl["nodes"]),
            "link_count": len(tmpl["links"]),
        }
    return out


# ═══════════════════════════════════════════════════════════════
# 自检
# ═══════════════════════════════════════════════════════════════


def _selfcheck() -> int:
    from .blueprint_model import BlueprintGraph

    # 1) event_print 注入
    g = BlueprintGraph()
    r = inject(g, "event_print", {"in_string": "自检"})
    assert r["ok"] and r["nodes_added"] == 2 and r["links_created"] == 1, f"event_print: {r}"
    listed = json.loads(g.bp_list())
    assert len(listed["nodes"]) == 2 and len(listed["links"]) == 1
    print("✅ event_print: BeginPlay → PrintString('自检')")

    # 2) branch_print 注入 + 参数
    g2 = BlueprintGraph()
    r = inject(g2, "branch_print",
               {"condition": True, "true_text": "正面", "false_text": "负面"})
    assert r["ok"] and r["nodes_added"] == 4 and r["links_created"] == 3, f"branch_print: {r}"
    listed2 = json.loads(g2.bp_list())
    assert len(listed2["nodes"]) == 4 and len(listed2["links"]) == 3
    # 验证参数绑定到节点默认值
    print_node = g2.nodes.get(listed2["nodes"][2]["id"])
    assert print_node and print_node.get("defaults", {}).get(
        "InString") == "正面", f"参数未绑定: {print_node}"
    print("✅ branch_print: 4 节点 3 连线, 参数绑定正确")

    # 3) compare_branch_print
    g3 = BlueprintGraph()
    r = inject(g3, "compare_branch_print",
               {"value_a": 10.0, "value_b": 5.0,
                "true_text": "YES", "false_text": "NO"})
    n_added = sum(1 for _ in g3.nodes)
    n_linked = len(g3.links)
    assert r["ok"] and n_added == 5 and n_linked >= 4, f"compare: {r} ({n_added} nodes, {n_linked} links)"
    print("✅ compare_branch_print: Greater → Branch → PrintString 双路")

    # 4) sequence_dual
    g4 = BlueprintGraph()
    r = inject(g4, "sequence_dual", {"text_a": "A", "text_b": "B"})
    assert r["ok"] and r["nodes_added"] == 4
    print("✅ sequence_dual: Then0/Then1 并行打印")

    # 5) 未知模板拒绝
    r = inject(g, "nonexistent", {})
    assert not r["ok"]
    print("✅ 未知模板拒绝")

    # 6) list_templates
    tlist = list_templates()
    assert len(tlist) >= 5
    print(f"✅ list_templates: {len(tlist)} 个模板")

    print(f"\nT3D 模板自检 6/6 通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(_selfcheck())
