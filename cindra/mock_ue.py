"""mock_ue —— Mac 上的内存场景, 实现和 ue_helper 同名的 cnd_*() 函数。

没装 UE 也能跑通整条链路: agent -> 工具 -> 这里。状态存在一个进程内的
字典里, 还能渲染成 ASCII 俯视图, 让你"看见"场景变化。

接真 UE 时把 transport 切到 RemoteExecTransport 即可, 这个文件不再参与。
"""
from __future__ import annotations

import json
from typing import Any


class MockScene:
    """一个极简的内存场景。"""

    def __init__(self) -> None:
        self.actors: dict[str, dict[str, Any]] = {}
        self._counters: dict[str, int] = {}

    # ---- cnd_*: 和 ue_helper.UE_HELPER_SOURCE 里同名同义 ----

    def cnd_spawn(self, actor_type="cube", name=None, location=(0, 0, 0),
                    rotation=(0, 0, 0), scale=(1, 1, 1)) -> str:
        actor_type = (actor_type or "cube").lower()
        if not name:
            self._counters[actor_type] = self._counters.get(actor_type, 0) + 1
            name = f"{actor_type}_{self._counters[actor_type]}"
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

    def cnd_list(self) -> str:
        out = [{"name": a["name"], "class": a["type"],
                "location": a["location"]} for a in self.actors.values()]
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
