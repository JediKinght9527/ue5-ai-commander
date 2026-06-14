"""mock_ue —— Mac 上的内存场景, 实现和 ue_helper 同名的 cnd_*() 函数。

没装 UE 也能跑通整条链路: agent -> 工具 -> 这里。状态存在一个进程内的
字典里, 还能渲染成 ASCII 俯视图, 让你"看见"场景变化。

接真 UE 时把 transport 切到 RemoteExecTransport 即可, 这个文件不再参与。
"""
from __future__ import annotations

import json
import sys
from typing import Any

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


class MockScene:
    """一个极简的内存场景。"""

    def __init__(self) -> None:
        self.actors: dict[str, dict[str, Any]] = {}
        self._counters: dict[str, int] = {}

    # ---- cnd_*: 和 ue_helper.UE_HELPER_SOURCE 里同名同义 ----

    def cnd_spawn(self, actor_type="cube", name=None, location=(0, 0, 0),
                    rotation=(0, 0, 0), scale=(1, 1, 1), folder=None,
                    tags=None) -> str:
        actor_type = (actor_type or "cube").lower()
        if not name:
            self._counters[actor_type] = self._counters.get(actor_type, 0) + 1
            name = f"Cindra_{actor_type.capitalize()}_{self._counters[actor_type]:03d}"
        # 名字冲突就加后缀, 模拟 UE 的唯一 label 行为
        base, i = name, 1
        while name in self.actors:
            i += 1
            name = f"{base}_{i}"
        self.actors[name] = {
            "name": name, "type": actor_type,
            "location": [float(x) for x in location],
            "rotation": [float(x) for x in rotation],
            "scale": [float(x) for x in scale],
            "folder": folder or "",
            "tags": [str(x) for x in (tags or [])],
        }
        return json.dumps({"ok": True, "action": "spawn", "name": name,
                           "type": actor_type,
                           "location": self.actors[name]["location"]})

    def cnd_delete(self, name) -> str:
        if name not in self.actors:
            return json.dumps({"ok": False, "error": f"not found: {name}"})
        del self.actors[name]
        return json.dumps({"ok": True, "action": "delete", "name": name})

    def cnd_move(self, name, location) -> str:
        if name not in self.actors:
            return json.dumps({"ok": False, "error": f"not found: {name}"})
        self.actors[name]["location"] = [float(x) for x in location]
        return json.dumps({"ok": True, "action": "move", "name": name,
                           "location": self.actors[name]["location"]})

    def cnd_set_transform(self, name, location=None, rotation=None,
                          scale=None) -> str:
        """一次性改位置/旋转/缩放 (任一可省)。补 cnd_move 只能改位置的不足 ——
        语义化批量编辑 (倒塌/地震) 必须能让物体旋转、缩放。和真 UE 侧同名同义。"""
        a = self.actors.get(name)
        if a is None:
            return json.dumps({"ok": False, "error": f"not found: {name}"})
        if location is not None:
            a["location"] = [float(x) for x in location]
        if rotation is not None:
            a["rotation"] = [float(x) for x in rotation]
        if scale is not None:
            a["scale"] = [float(x) for x in scale]
        return json.dumps({"ok": True, "action": "set_transform", "name": name,
                           "location": a["location"], "rotation": a["rotation"],
                           "scale": a["scale"]})

    def cnd_list(self) -> str:
        out = [{"name": a["name"], "class": a["type"],
                "location": a["location"],
                "folder": a.get("folder", ""),
                "tags": a.get("tags", [])} for a in self.actors.values()]
        return json.dumps({"ok": True, "action": "list", "actors": out})

    def cnd_clear(self, prefix=None) -> str:
        before = len(self.actors)
        if prefix:
            self.actors = {k: v for k, v in self.actors.items()
                           if not k.startswith(prefix)}
        else:
            self.actors = {}
        return json.dumps({"ok": True, "action": "clear",
                           "deleted": before - len(self.actors)})

    # ---- 把场景画成 ASCII 俯视图 (X 向右, Y 向下), 让你能"看见" ----

    def render_topdown(self, width=48, height=18, span=1000.0) -> str:
        if not self.actors:
            return "(空场景)"
        grid = [[" "] * width for _ in range(height)]
        for a in self.actors.values():
            x, y = a["location"][0], a["location"][1]
            gx = int((x + span) / (2 * span) * (width - 1))
            gy = int((y + span) / (2 * span) * (height - 1))
            gx = max(0, min(width - 1, gx))
            gy = max(0, min(height - 1, gy))
            grid[gy][gx] = a["type"][0].upper()
        border = "+" + "-" * width + "+"
        rows = "\n".join("|" + "".join(r) + "|" for r in grid)
        legend = ", ".join(sorted({a["type"] for a in self.actors.values()}))
        return f"{border}\n{rows}\n{border}\n俯视图 ({len(self.actors)} 个: {legend})"


def _selfcheck() -> int:
    """端到端自检: 建网格 → 语义批量变换 → 验证每个都被改了 transform。
    复刻 docs/project 的可复跑自检, 补上 CindraChat 一直缺的回归测试。
    跑: python3 -m cindra.mock_ue
    """
    import json as _json
    from . import scene_tools

    scene = MockScene()

    # 1) 建 3x3 网格
    for pos in [[c * 200, r * 200, 0] for r in range(3) for c in range(3)]:
        scene.cnd_spawn(actor_type="cube", location=pos)
    n = len(scene.actors)
    assert n == 9, f"应有 9 个 cube, 实际 {n}"
    print(f"✅ 建 3x3 网格: {n} 个 cube")

    # 2) 直接验证新原语 cnd_set_transform 能改旋转/缩放 (cnd_move 做不到)
    name0 = next(iter(scene.actors))
    scene.cnd_set_transform(name0, rotation=[0, 0, 45], scale=[1, 1, 2])
    a0 = scene.actors[name0]
    assert a0["rotation"] == [0, 0, 45] and a0["scale"] == [1, 1, 2], "set_transform 没生效"
    print(f"✅ cnd_set_transform 改旋转+缩放: {name0} rot={a0['rotation']} scale={a0['scale']}")

    # 3) 经 scene_tools 走 arrange_scene 语义批量编辑 (earthquake)
    class _T:  # 极简 transport, 直接打到这个 scene
        def call(self, func, **kw):
            return _json.loads(getattr(scene, func)(**kw))

    before = {k: list(v["location"]) for k, v in scene.actors.items()}
    res = scene_tools.dispatch(_T(), "arrange_scene",
                               {"style": "earthquake", "intensity": 1.0})
    assert res.get("ok"), f"arrange_scene 失败: {res}"
    moved = sum(1 for k, v in scene.actors.items()
                if v["location"] != before[k])
    tilted = sum(1 for v in scene.actors.values()
                 if v["rotation"] != [0, 0, 0])
    assert moved == 9, f"earthquake 应移动全部 9 个, 实际 {moved}"
    assert tilted >= 1, "earthquake 应让物体倾斜"
    print(f"✅ arrange_scene(earthquake): {res['changed']}/{n} 个被变换, "
          f"{moved} 位移, {tilted} 倾斜")

    # 4) 确定性: 同输入同结果 (基于名字做种子)
    scene2 = MockScene()
    for pos in [[c * 200, r * 200, 0] for r in range(3) for c in range(3)]:
        scene2.cnd_spawn(actor_type="cube", location=pos)

    class _T2:
        def call(self, func, **kw):
            return _json.loads(getattr(scene2, func)(**kw))
    scene_tools.dispatch(_T2(), "arrange_scene",
                         {"style": "earthquake", "intensity": 1.0})
    same = all(scene.actors[k]["location"] == scene2.actors[k]["location"]
               for k in scene.actors)
    assert same, "arrange_scene 不确定 —— 同输入产出不一致"
    print("✅ 确定性: 同输入两次产出一致")

    print("\n场景自检 4/4 通过。地震后俯视图:")
    print(scene.render_topdown())
    return 0


if __name__ == "__main__":
    raise SystemExit(_selfcheck())
