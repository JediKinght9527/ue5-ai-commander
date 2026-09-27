"""blueprint_model —— Mac 上的内存蓝图图模型。

复刻 mock_ue.py 的思路: 没装 UE 也能跑通"操控蓝图图"整条链路。把一张
Blueprint 事件图建模成 节点(Node) + 引脚(Pin) + 连线(Link), 实现和真 UE
侧同名同义的 bp_*() 操作, 还能渲染成文本图让你"看见"图长什么样。

UE 里这对应 UEdGraph/UK2Node/UEdGraphPin —— 真后端 (UEBlueprintTransport)
通过 C++ 插件操作那些类, 但工具接口和本文件完全一致。

引脚模型 (照搬 UE 的关键概念):
  - direction: "input" | "output"
  - kind: "exec" (白色执行流) | "data" (带类型的数据)
  - data 引脚有 type (bool/int/float/string/object/...)

连线规则 (照搬 UE 的合法性):
  - 只能 output -> input
  - exec 接 exec, data 接 data
  - data 连线两端类型需一致 (wildcard 除外)
  - 一个 input data 引脚只能有一条入线 (UE 行为); exec output 同理单出
"""
from __future__ import annotations

import json
from typing import Any

# 内置节点模板: 名字 -> 引脚定义。引脚: (name, direction, kind, type)
# 这是一个精简但有代表性的节点库, 覆盖事件/分支/打印/取设变量/比较。
_NODE_TEMPLATES: dict[str, list[tuple]] = {
    # 事件节点: 只有一个 exec 输出 (执行流起点)
    "Event_BeginPlay": [("then", "output", "exec", None)],
    "Event_Tick": [("then", "output", "exec", None),
                   ("DeltaSeconds", "output", "data", "float")],
    # 流程控制
    "Branch": [("exec", "input", "exec", None),
               ("Condition", "input", "data", "bool"),
               ("True", "output", "exec", None),
               ("False", "output", "exec", None)],
    "Sequence": [("exec", "input", "exec", None),
                 ("Then0", "output", "exec", None),
                 ("Then1", "output", "exec", None)],
    # 常用函数
    "PrintString": [("exec", "input", "exec", None),
                    ("InString", "input", "data", "string"),
                    ("then", "output", "exec", None)],
    "Delay": [("exec", "input", "exec", None),
              ("Duration", "input", "data", "float"),
              ("Completed", "output", "exec", None)],
    # 比较/运算 (纯数据节点, 无 exec)
    "Greater_FloatFloat": [("A", "input", "data", "float"),
                           ("B", "input", "data", "float"),
                           ("ReturnValue", "output", "data", "bool")],
    "Add_FloatFloat": [("A", "input", "data", "float"),
                       ("B", "input", "data", "float"),
                       ("ReturnValue", "output", "data", "float")],
}


def node_templates() -> dict[str, list[dict]]:
    """对外暴露可用节点模板 (给 agent 看有哪些节点可加)。"""
    out = {}
    for name, pins in _NODE_TEMPLATES.items():
        out[name] = [{"name": p[0], "direction": p[1], "kind": p[2],
                      "type": p[3]} for p in pins]
    return out


class BlueprintGraph:
    """一张内存事件图。"""

    def __init__(self) -> None:
        self.nodes: dict[str, dict] = {}
        self.links: list[dict] = []
        self.variables: dict[str, dict] = {}
        self._counter = 0
        self.asset_path: str | None = None
        self.parent_class: str = "Actor"

    # ---- bp_*: 和真 UE 侧 (ue 后端) 同名同义 ----

    def bp_create(self, path, parent_class="Actor") -> str:
        """mock 版建蓝图资产: 只记路径/父类 (真侧 CndBpCreate 建真资产)。"""
        if self.asset_path == path:
            return json.dumps({"ok": False, "error": f"blueprint exists: {path}"})
        self.asset_path = path
        self.parent_class = parent_class
        self.nodes, self.links, self.variables = {}, [], {}
        self._counter = 0
        return json.dumps({"ok": True, "action": "create", "path": path,
                           "parent": parent_class})

    def bp_open(self, path) -> str:
        self.asset_path = path
        return json.dumps({"ok": True, "action": "open", "path": path,
                           "nodes": len(self.nodes)})

    def bp_compile(self) -> str:
        """mock 编译: 真侧是 FKismetEditorUtilities::CompileBlueprint。
        这里做廉价等价检查: 每个带 exec 输入的节点必须从某个事件可达
        (孤儿执行节点 = 真编译的 warning/死代码)。"""
        reachable: set[str] = set()
        frontier = [nid for nid, n in self.nodes.items()
                    if n["type"].startswith("Event_")]
        reachable.update(frontier)
        while frontier:
            cur = frontier.pop()
            for ln in self.links:
                if ln["from_node"] == cur and ln["to_node"] not in reachable:
                    reachable.add(ln["to_node"])
                    frontier.append(ln["to_node"])
        orphans = []
        for nid, n in self.nodes.items():
            has_exec_in = any(p["kind"] == "exec" and p["direction"] == "input"
                              for p in n["pins"])
            if has_exec_in and nid not in reachable:
                orphans.append(nid)
        warnings = [f"节点 {nid} 不可达 (没接到任何事件流)" for nid in orphans]
        return json.dumps({"ok": True, "action": "compile", "errors": 0,
                           "warnings": len(warnings), "messages": warnings})

    def bp_add_node(self, node_type, name=None) -> str:
        if node_type not in _NODE_TEMPLATES:
            return json.dumps({"ok": False,
                               "error": f"未知节点类型: {node_type}. "
                               f"可用: {', '.join(_NODE_TEMPLATES)}"})
        self._counter += 1
        nid = name or f"{node_type}_{self._counter}"
        base, i = nid, 1
        while nid in self.nodes:
            i += 1
            nid = f"{base}_{i}"
        pins = [{"name": p[0], "direction": p[1], "kind": p[2], "type": p[3]}
                for p in _NODE_TEMPLATES[node_type]]
        self.nodes[nid] = {"id": nid, "type": node_type, "pins": pins}
        return json.dumps({"ok": True, "action": "add_node", "id": nid,
                           "type": node_type,
                           "pins": [p["name"] for p in pins]})

    def bp_add_variable(self, name, var_type="float", default=None) -> str:
        if name in self.variables:
            return json.dumps({"ok": False, "error": f"变量已存在: {name}"})
        self.variables[name] = {"name": name, "type": var_type,
                                "default": default}
        return json.dumps({"ok": True, "action": "add_variable",
                           "name": name, "type": var_type})

    def _find_pin(self, node_id, pin_name) -> tuple[dict[str, Any] | None, str | None]:
        """找引脚。返回 (引脚, None) 或 (None, 错误原因)。"""

        node = self.nodes.get(node_id)
        if not node:
            return None, f"节点不存在: {node_id}"
        for p in node["pins"]:
            if p["name"] == pin_name:
                return p, None
        names = ", ".join(p["name"] for p in node["pins"])
        return None, f"节点 {node_id} 没有引脚 {pin_name} (有: {names})"

    def bp_connect(self, from_node, from_pin, to_node, to_pin) -> str:
        src, err = self._find_pin(from_node, from_pin)
        if err or src is None:
            return json.dumps({"ok": False, "error": err or "引脚不存在"})
        dst, err = self._find_pin(to_node, to_pin)
        if err or dst is None:
            return json.dumps({"ok": False, "error": err or "引脚不存在"})
        # 方向: 必须 output -> input
        if src["direction"] != "output" or dst["direction"] != "input":
            return json.dumps({"ok": False,
                               "error": "连线必须从 output 引脚到 input 引脚"})
        # 类别: exec 接 exec, data 接 data
        if src["kind"] != dst["kind"]:
            return json.dumps({"ok": False,
                               "error": f"引脚类别不匹配: {src['kind']} -> {dst['kind']}"})
        # data 类型一致
        if src["kind"] == "data" and src["type"] != dst["type"]:
            return json.dumps({"ok": False,
                               "error": f"数据类型不匹配: {src['type']} -> {dst['type']}"})
        # 单入: 一个 input 引脚 (无论 exec/data) 只能有一条入线
        for ln in self.links:
            if ln["to_node"] == to_node and ln["to_pin"] == to_pin:
                return json.dumps({"ok": False,
                                   "error": f"{to_node}.{to_pin} 已有入线, "
                                   "一个输入引脚只能连一条"})
        # exec output 单出 (一个执行输出只能去一个地方)
        if src["kind"] == "exec":
            for ln in self.links:
                if ln["from_node"] == from_node and ln["from_pin"] == from_pin:
                    return json.dumps({"ok": False,
                                       "error": f"{from_node}.{from_pin} 执行输出已连线, "
                                       "exec 输出只能连一条"})
        self.links.append({"from_node": from_node, "from_pin": from_pin,
                           "to_node": to_node, "to_pin": to_pin})
        return json.dumps({"ok": True, "action": "connect",
                           "link": f"{from_node}.{from_pin} -> {to_node}.{to_pin}"})

    def bp_delete_node(self, node_id) -> str:
        if node_id not in self.nodes:
            return json.dumps({"ok": False, "error": f"节点不存在: {node_id}"})
        del self.nodes[node_id]
        before = len(self.links)
        self.links = [ln for ln in self.links
                      if ln["from_node"] != node_id and ln["to_node"] != node_id]
        return json.dumps({"ok": True, "action": "delete_node", "id": node_id,
                           "removed_links": before - len(self.links)})

    def bp_list(self) -> str:
        return json.dumps({"ok": True, "action": "list",
                           "nodes": [{"id": n["id"], "type": n["type"]}
                                     for n in self.nodes.values()],
                           "links": self.links,
                           "variables": list(self.variables.values())})

    def bp_clear(self) -> str:
        n = len(self.nodes)
        self.nodes, self.links, self.variables = {}, [], {}
        return json.dumps({"ok": True, "action": "clear", "deleted": n})

    # ---- 文本渲染, 让你"看见"图 ----

    def render(self) -> str:
        if not self.nodes:
            return "(空蓝图图)"
        lines = ["蓝图事件图:"]
        if self.variables:
            lines.append("  变量: " + ", ".join(
                f"{v['name']}:{v['type']}" for v in self.variables.values()))
        lines.append("  节点:")
        for n in self.nodes.values():
            lines.append(f"    [{n['id']}] ({n['type']})")
        lines.append("  连线:")
        if not self.links:
            lines.append("    (无)")
        for ln in self.links:
            arrow = "=>" if _is_exec_link(self, ln) else "->"
            lines.append(f"    {ln['from_node']}.{ln['from_pin']} "
                         f"{arrow} {ln['to_node']}.{ln['to_pin']}")
        return "\n".join(lines)


def _is_exec_link(graph: BlueprintGraph, ln: dict) -> bool:
    node = graph.nodes.get(ln["from_node"])
    if not node:
        return False
    for p in node["pins"]:
        if p["name"] == ln["from_pin"]:
            return p["kind"] == "exec"
    return False


def _selfcheck() -> int:
    """离线自检: 建一张 BeginPlay -> Branch -> PrintString 的图,
    验证连线校验规则 + mock 编译的孤儿检测。跑: python3 -m cindra.blueprint_model
    """
    g = BlueprintGraph()
    ok = 0

    # 1. 建图: BeginPlay -> Branch(True) -> PrintString, Greater 喂 Condition
    assert json.loads(g.bp_create("/Game/BP_Test", "Actor"))["ok"]
    for t in ("Event_BeginPlay", "Branch", "PrintString", "Greater_FloatFloat"):
        assert json.loads(g.bp_add_node(t))["ok"], t
    assert json.loads(g.bp_connect("Event_BeginPlay_1", "then",
                                   "Branch_2", "exec"))["ok"]
    assert json.loads(g.bp_connect("Greater_FloatFloat_4", "ReturnValue",
                                   "Branch_2", "Condition"))["ok"]
    assert json.loads(g.bp_connect("Branch_2", "True",
                                   "PrintString_3", "exec"))["ok"]
    ok += 1
    print("✅ 建图 4 节点 3 连线")

    # 2. 非法连线全部被拒: 类型不匹配 / 双入线 / exec 双出 / input->input
    g.bp_add_node("Add_FloatFloat")  # Add_FloatFloat_5
    r = json.loads(g.bp_connect("Add_FloatFloat_5", "ReturnValue",
                                "Branch_2", "Condition"))
    assert not r["ok"] and "类型" in r["error"], "float->bool 应被拒"
    r = json.loads(g.bp_connect("Event_BeginPlay_1", "then",
                                "PrintString_3", "exec"))
    assert not r["ok"], "exec 双出应被拒 (BeginPlay.then 已连)"
    r = json.loads(g.bp_connect("PrintString_3", "InString",
                                "Branch_2", "Condition"))
    assert not r["ok"], "input->input 应被拒"
    ok += 1
    print("✅ 非法连线三连拒 (类型/双出/方向)")

    # 3. mock 编译: 当前图应无孤儿
    r = json.loads(g.bp_compile())
    assert r["ok"] and r["warnings"] == 0, r
    ok += 1
    print("✅ 编译: 全部可达, 0 警告")

    # 4. 加一个不接线的 Delay -> 编译报孤儿
    g.bp_add_node("Delay")
    r = json.loads(g.bp_compile())
    assert r["warnings"] == 1 and "Delay" in r["messages"][0], r
    ok += 1
    print("✅ 编译: 孤儿 Delay 被点名")

    # 5. 删节点连带清线 + bp_list round-trip
    r = json.loads(g.bp_delete_node("Branch_2"))
    assert r["ok"] and r["removed_links"] == 3
    listed = json.loads(g.bp_list())
    assert len(listed["nodes"]) == 5 and len(listed["links"]) == 0
    ok += 1
    print("✅ 删节点连带清线 + list round-trip")

    print(f"\n蓝图模型自检 {ok}/5 通过。当前图:")
    print(g.render())
    return 0


if __name__ == "__main__":
    raise SystemExit(_selfcheck())
