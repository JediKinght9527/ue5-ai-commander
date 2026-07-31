"""verifier —— 验证闭环的"硬校验"层: 不信工具返回值, 只信场景前后 diff。

设计 (对应 agent loop 的 Observe→Verify 阶段):
  1. 每个改场景的工具调用前后各拍一次 cnd_snapshot (结构化快照)。
  2. diff_snapshots 算出 added/removed/changed。
  3. hard_check 按"这个工具声称干了什么"自动推导判据, 和实际 diff 对账。
     判据完全从 (tool_name, args, result) 推导 —— 不需要 LLM、不花 token、
     确定性可离线自检。抓的是"工具返回 ok 但引擎里其实没生效"这类静默失败
     (真 UE 上最常见: 视口隐藏时 spawn 崩、transaction 没真提交)。

视觉软校验不在这里: agent 本身就是 VLM, 通过 inspect_viewport 工具亲眼看
截图 (mock: ASCII 俯视图) 自行判断 —— 见 scene_tools.inspect_viewport。

自检: python3 -m cindra.verifier  (纯 mock, 无需 UE / API key)
"""
from __future__ import annotations

from typing import Any

# 位置/旋转/缩放对账的容差。UE 浮点经 JSON 往返会有尾差。
_EPS = 1e-3

# 会改场景的工具 → 需要前后快照 + 硬校验。查询类 (list/inspect) 不在内。
MUTATING_TOOLS = {"spawn_actor", "spawn_grid", "delete_actor", "move_actor",
                  "set_transform", "arrange_scene", "clear_scene", "undo"}


def take_snapshot(transport) -> dict[str, dict] | None:
    """拍一张结构化快照, 返回 name -> state。失败返回 None (校验降级跳过)。"""
    res = transport.call("cnd_snapshot")
    if not res.get("ok"):
        return None
    return {a["name"]: a for a in res.get("actors", [])}


def diff_snapshots(before: dict[str, dict], after: dict[str, dict]) -> dict:
    """算前后差异: added/removed 是名字列表, changed 是 {名字: [变了的字段]}。"""
    added = [n for n in after if n not in before]
    removed = [n for n in before if n not in after]
    changed: dict[str, list[str]] = {}
    for n in before:
        if n not in after:
            continue
        fields = [f for f in ("location", "rotation", "scale")
                  if not _vec_eq(before[n].get(f), after[n].get(f))]
        if fields:
            changed[n] = fields
    return {"added": added, "removed": removed, "changed": changed}


def _vec_eq(a, b) -> bool:
    if a is None or b is None:
        return a == b
    return len(a) == len(b) and all(abs(x - y) <= _EPS for x, y in zip(a, b))


def _vec_close(actual, want) -> bool:
    """want 可能是 int 列表 (agent 给的), actual 是 float。"""
    return _vec_eq([float(x) for x in actual], [float(x) for x in want])


def hard_check(tool: str, args: dict, result: dict, d: dict,
               after: dict[str, dict]) -> tuple[bool, str]:
    """按工具声称的效果和实际 diff 对账。返回 (是否通过, 原因)。

    原则: 宁可放过、不可误杀 —— 判据只取"该工具必然产生的最小效果",
    拿不准的 (比如 set_transform 设了和原值相同的值) 按 after 终态对账。
    """
    if not result.get("ok", True):
        return True, "工具已自报失败, 无需对账"  # 失败结果本身就会让 agent 修正

    if tool == "spawn_actor":
        name = result.get("name")
        if name not in d["added"]:
            return False, f"声称 spawn 了 {name}, 但快照里没有新增它 (实际新增: {d['added']})"
        want = args.get("location")
        if want and not _vec_close(after[name]["location"], want):
            return False, (f"{name} 生成位置不对: 要求 {want}, "
                           f"实际 {after[name]['location']}")
        return True, f"新增 {name} 已确认"

    if tool == "spawn_grid":
        want_n = int(result.get("count", args.get("count", 0)))
        if len(d["added"]) != want_n:
            return False, f"声称生成 {want_n} 个, 快照里只新增 {len(d['added'])} 个"
        return True, f"新增 {want_n} 个已确认"

    if tool == "delete_actor":
        name = args.get("name")
        if name not in d["removed"]:
            return False, f"声称删除了 {name}, 但它还在场景里"
        return True, f"删除 {name} 已确认"

    if tool in ("move_actor", "set_transform"):
        # 不要求"有变化" (设相同值是合法 no-op), 只对账终态是否符合要求。
        name = args.get("name")
        if name not in after:
            return False, f"{name} 不在快照里 (被误删或改名?)"
        for field in ("location", "rotation", "scale"):
            want = args.get(field)
            if want is not None and not _vec_close(after[name][field], want):
                return False, (f"{name}.{field} 终态不对: 要求 {want}, "
                               f"实际 {after[name][field]}")
        return True, f"{name} 终态与要求一致"

    if tool == "arrange_scene":
        claimed = int(result.get("changed", 0))
        actual = len(d["changed"]) + len(d["added"]) + len(d["removed"])
        if claimed > 0 and actual == 0:
            return False, f"声称变换了 {claimed} 个, 但快照前后毫无差异"
        return True, f"实际 {len(d['changed'])} 个被变换"

    if tool == "clear_scene":
        claimed = int(result.get("deleted", 0))
        if len(d["removed"]) != claimed:
            return False, (f"声称清掉 {claimed} 个, 实际移除 {len(d['removed'])} 个")
        return True, f"清除 {claimed} 个已确认"

    if tool == "undo":
        # undo 的正确性没有通用判据 (取决于被撤销的操作), 只确认场景确实变了。
        # 真 UE 的 Transaction.Undo 无返回值, 这一步是它唯一的成效检测。
        moved = len(d["changed"]) + len(d["added"]) + len(d["removed"])
        if moved == 0:
            return False, "undo 后场景毫无变化 —— 撤销可能没生效 (真UE已知坑: 改前没 actor.modify())"
        return True, f"undo 生效: {moved} 处回退"

    return True, "非改动类工具, 跳过对账"


def verify(tool: str, args: dict, result: dict,
           before: dict[str, dict] | None,
           after: dict[str, dict] | None) -> tuple[bool, str]:
    """一步到位: diff + hard_check。快照拍失败时降级放行 (不阻塞 agent)。"""
    if tool not in MUTATING_TOOLS:
        return True, "非改动类工具"
    if before is None or after is None:
        return True, "快照不可用, 跳过硬校验"
    return hard_check(tool, args, result, diff_snapshots(before, after), after)


# ---------------------------------------------------------------- selfcheck

def _selfcheck() -> int:
    """离线自检: 诚实操作要通过, 撒谎操作必须被抓。跑: python3 -m cindra.verifier"""
    from . import scene_tools
    from .transport import MockTransport

    t = MockTransport()

    def run(tool, args):
        before = take_snapshot(t)
        result = scene_tools.dispatch(t, tool, args)
        after = take_snapshot(t)
        ok, why = verify(tool, args, result, before, after)
        return result, ok, why, after

    # 1) 诚实 spawn → 通过
    r, ok, why, after = run("spawn_actor",
                            {"actor_type": "cube", "location": [100, 200, 0]})
    assert ok, f"诚实 spawn 被误杀: {why}"
    print(f"✅ spawn 硬校验通过: {why}")

    # 2) 撒谎的 spawn (声称 ok 但场景没变) → 必须抓出来
    snap = take_snapshot(t)
    fake = {"ok": True, "action": "spawn", "name": "ghost_1", "type": "cube"}
    ok, why = verify("spawn_actor", {"actor_type": "cube"}, fake, snap, snap)
    assert not ok, "静默失败的 spawn 没被抓住!"
    print(f"✅ 静默失败被抓: {why}")

    # 3) move 终态对账: 声称移到 A 实际在 B → 抓出来
    name = r["name"]
    real_move = {"ok": True, "action": "move", "name": name}
    before = take_snapshot(t)
    ok, why = verify("move_actor", {"name": name, "location": [999, 999, 0]},
                     real_move, before, before)  # 场景没动
    assert not ok, "move 终态不符没被抓住!"
    print(f"✅ move 终态对账生效: {why}")

    # 4) set_transform 设相同值 (合法 no-op) → 不能误杀
    cur = before[name]["location"]
    r2, ok, why, _ = run("set_transform", {"name": name, "location": cur})
    assert ok, f"no-op set_transform 被误杀: {why}"
    print(f"✅ no-op 不误杀: {why}")

    # 5) spawn_grid 数量对账
    r3, ok, why, _ = run("spawn_grid", {"actor_type": "sphere", "count": 6})
    assert ok and "6" in why, f"spawn_grid 对账失败: {why}"
    print(f"✅ spawn_grid 数量对账: {why}")

    # 6) undo 闭环: 撤销 grid 的最后一个 spawn → 场景变化被确认
    r4, ok, why, after4 = run("undo", {"steps": 1})
    assert ok, f"undo 校验失败: {why}"
    assert len(after4) == 6, f"undo 后应剩 6 个 (7-1), 实际 {len(after4)}"
    print(f"✅ undo 生效并被确认: {why} (剩 {len(after4)} 个)")

    # 7) 空 undo (历史耗尽后再撤) → 自报失败, 校验放行不误杀
    t2 = MockTransport()
    r5 = scene_tools.dispatch(t2, "undo", {"steps": 1})
    assert not r5.get("ok"), "空历史 undo 应自报失败"
    print(f"✅ 空历史 undo 自报失败: {r5.get('error')}")

    # 8) clear 对账
    r6, ok, why, after6 = run("clear_scene", {})
    assert ok and len(after6) == 0, f"clear 对账失败: {why}"
    print(f"✅ clear 对账: {why}")

    # 9) inspect_viewport (mock 视觉通道) 返回 ASCII 俯视图
    scene_tools.dispatch(t, "spawn_actor", {"actor_type": "cone"})
    view = scene_tools.dispatch(t, "inspect_viewport", {})
    assert view.get("ok") and "俯视图" in view.get("view", ""), f"viewport 失败: {view}"
    print("✅ inspect_viewport (mock=ASCII 俯视图) 可用")

    print("\n验证闭环自检 9/9 通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(_selfcheck())
