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
        # 撤销栈: 每次改动前压入整个场景的深拷贝, 对应真 UE 的 transaction 撤销。
        # 上限 100 条防止长会话吃内存。
        self._history: list[dict[str, dict[str, Any]]] = []
        # 模拟相机状态 (session 持久化 + cnd_set_camera/cnd_screenshot 使用)
        self.camera: dict[str, Any] = {
            "location": [500.0, 500.0, 500.0],
            "rotation": [0.0, 0.0, 0.0],
            "fov": 90.0,
        }

    def _save(self) -> None:
        """改动前存档 (相当于开一个 transaction)。"""
        self._history.append(json.loads(json.dumps(self.actors)))
        if len(self._history) > 100:
            self._history.pop(0)

    # ---- cnd_*: 和 ue_helper.UE_HELPER_SOURCE 里同名同义 ----

    def cnd_spawn(self, actor_type="cube", name=None, location=(0, 0, 0),
                    rotation=(0, 0, 0), scale=(1, 1, 1), folder=None,
                    tags=None) -> str:
        self._save()
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
        self._save()
        del self.actors[name]
        return json.dumps({"ok": True, "action": "delete", "name": name})

    def cnd_move(self, name, location) -> str:
        if name not in self.actors:
            return json.dumps({"ok": False, "error": f"not found: {name}"})
        self._save()
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
        self._save()
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

    def cnd_snapshot(self) -> str:
        """全量场景快照 (含旋转/缩放) —— 验证闭环的结构化"眼睛"。
        cnd_list 是给 agent 看的简表, 这个是给 verifier 做前后 diff 的全表。"""
        out = [{"name": a["name"], "class": a["type"],
                "location": a["location"], "rotation": a["rotation"],
                "scale": a["scale"]} for a in self.actors.values()]
        return json.dumps({"ok": True, "action": "snapshot", "actors": out})

    def cnd_undo(self, steps=1) -> str:
        """回滚最近 steps 次改动 (对应真 UE 的 Transaction.Undo)。"""
        steps = max(1, int(steps))
        done = 0
        for _ in range(steps):
            if not self._history:
                break
            self.actors = self._history.pop()
            done += 1
        if done == 0:
            return json.dumps({"ok": False, "error": "没有可撤销的改动"})
        return json.dumps({"ok": True, "action": "undo", "undone": done,
                           "actors_now": len(self.actors)})

    def cnd_clear(self, prefix=None) -> str:
        self._save()
        before = len(self.actors)
        if prefix:
            self.actors = {k: v for k, v in self.actors.items()
                           if not k.startswith(prefix)}
        else:
            self.actors = {}
        return json.dumps({"ok": True, "action": "clear",
                           "deleted": before - len(self.actors)})

    # ---- 真资产/灯光/环境/PCG (与 ue_helpers/assets.py 同名同义) ----

    def _manifest(self):
        if not hasattr(self, "_asset_manifest"):
            import os
            path = os.path.join(os.path.dirname(__file__), "mock_assets",
                                "manifest.json")
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            self._asset_manifest = {a["path"]: a for a in data["assets"]}
            self._asset_manifest_path = path
        return self._asset_manifest

    def _uniq(self, base: str) -> str:
        name, i = base, 1
        while name in self.actors:
            i += 1
            name = f"{base}_{i}"
        return name

    def cnd_list_assets(self, roots=None, classes=None,
                        manifest_path=None) -> str:
        m = self._manifest()
        return json.dumps({"ok": True, "action": "list_assets",
                           "count": len(m),
                           "path": self._asset_manifest_path})

    def cnd_spawn_asset(self, asset_path, name=None, location=(0, 0, 0),
                        rotation=(0, 0, 0), scale=(1, 1, 1),
                        folder=None) -> str:
        entry = self._manifest().get(asset_path)
        if entry is None:
            # 镜像真侧 load_asset 失败 —— agent 必须先 search_assets 拿真路径
            return json.dumps({"ok": False,
                               "error": f"asset not found: {asset_path}"})
        base = name or f"Cindra_{entry['name']}"
        label = self._uniq(base)
        self.actors[label] = {
            "name": label, "type": f"asset:{entry['name']}",
            "asset": asset_path,
            "location": [float(x) for x in location],
            "rotation": [float(x) for x in rotation],
            "scale": [float(x) for x in scale],
            "folder": folder or "", "tags": list(entry.get("tags", [])),
        }
        return json.dumps({"ok": True, "action": "spawn_asset",
                           "name": label, "asset": asset_path,
                           "location": self.actors[label]["location"],
                           "bounds_extent": [50.0 * float(scale[0]),
                                             50.0 * float(scale[1]),
                                             50.0 * float(scale[2])]})

    def cnd_set_material(self, name, material_path, slot=0) -> str:
        a = self.actors.get(name)
        if a is None:
            return json.dumps({"ok": False, "error": f"not found: {name}"})
        if material_path not in self._manifest():
            return json.dumps({"ok": False,
                               "error": f"material not found: {material_path}"})
        a.setdefault("materials", {})[str(int(slot))] = material_path
        return json.dumps({"ok": True, "action": "set_material", "name": name,
                           "material": material_path, "slot": int(slot)})

    def cnd_spawn_light(self, light_type="point", name=None,
                        location=(0, 0, 300), rotation=(0, 0, 0),
                        intensity=5000.0, color=None, temperature=None,
                        attenuation_radius=1000.0, cone_angle=44.0) -> str:
        lt = (light_type or "point").lower()
        if lt not in ("point", "spot", "rect", "directional"):
            return json.dumps({"ok": False,
                               "error": f"unknown light type: {light_type}"})
        label = self._uniq(name or f"Cindra_{lt.capitalize()}Light")
        self.actors[label] = {
            "name": label, "type": f"light:{lt}",
            "location": [float(x) for x in location],
            "rotation": [float(x) for x in rotation],
            "scale": [1.0, 1.0, 1.0],
            "intensity": float(intensity),
            "color": [float(c) for c in color] if color else None,
            "temperature": float(temperature) if temperature else None,
            "folder": "", "tags": [],
        }
        return json.dumps({"ok": True, "action": "spawn_light", "name": label,
                           "type": lt,
                           "location": self.actors[label]["location"],
                           "intensity": float(intensity)})

    def cnd_spawn_env(self, kind, params=None) -> str:
        kinds = ("sky_atmosphere", "exp_height_fog", "post_process",
                 "sky_light", "sun")
        if kind not in kinds:
            return json.dumps({"ok": False,
                               "error": f"unknown env kind: {kind}"})
        label = f"Cindra_Env_{kind}"
        self.actors.pop(label, None)  # 单例: 重建全量生效
        self.actors[label] = {
            "name": label, "type": f"env:{kind}",
            "location": [0.0, 0.0, 0.0], "rotation": [0.0, 0.0, 0.0],
            "scale": [1.0, 1.0, 1.0],
            "params": dict(params or {}), "folder": "", "tags": [],
        }
        return json.dumps({"ok": True, "action": "spawn_env", "kind": kind,
                           "name": label})

    def cnd_pcg_spawn_volume(self, graph_path, name=None, origin=(0, 0, 0),
                             size=(2000, 2000, 500)) -> str:
        entry = self._manifest().get(graph_path)
        if entry is None or entry.get("class") != "PCGGraph":
            return json.dumps({"ok": False,
                               "error": f"pcg graph not found: {graph_path}"})
        label = self._uniq(name or "Cindra_PCGVolume")
        self.actors[label] = {
            "name": label, "type": "pcg:volume", "graph": graph_path,
            "location": [float(x) for x in origin],
            "rotation": [0.0, 0.0, 0.0],
            "scale": [float(size[0]) / 100.0, float(size[1]) / 100.0,
                      float(size[2]) / 100.0],
            "size": [float(x) for x in size], "folder": "", "tags": [],
        }
        return json.dumps({"ok": True, "action": "pcg_spawn_volume",
                           "name": label, "graph": graph_path})

    def cnd_pcg_generate(self, name) -> str:
        vol = self.actors.get(name)
        if vol is None or vol["type"] != "pcg:volume":
            return json.dumps({"ok": False,
                               "error": f"no PCG volume: {name}"})
        import hashlib

        def r01(salt):
            h = hashlib.md5(f"{name}|{salt}".encode()).hexdigest()
            return int(h[:8], 16) / 0xFFFFFFFF

        size = vol["size"]
        n = min(40, max(4, int(size[0] * size[1] / (500.0 * 500.0))))
        ox, oy, oz = vol["location"]
        for i in range(n):
            label = f"{name}_gen_{i:03d}"
            self.actors[label] = {
                "name": label, "type": "pcg:gen",
                "location": [ox + (r01(f"x{i}") - 0.5) * size[0],
                             oy + (r01(f"y{i}") - 0.5) * size[1], oz],
                "rotation": [0.0, r01(f"yaw{i}") * 360.0, 0.0],
                "scale": [0.8 + r01(f"s{i}") * 0.6] * 3,
                "folder": "", "tags": [],
            }
        return json.dumps({"ok": True, "action": "pcg_generate", "name": name,
                           "generated": n})

    def cnd_env_info(self) -> str:
        return json.dumps({"ok": True, "action": "env_info",
                           "engine_version": "mock",
                           "pcg_available": True, "megalights": "mock"})

    # ---- 视觉闭环: 相机 + 截图 (与 ue_helpers/vision.py 同名同义) ----

    def cnd_set_camera(self, location=None, rotation=None, look_at=None,
                       orbit=None, fov=None) -> str:
        from .camera_math import look_at_rotation, orbit_pose

        cam = self.camera
        if orbit:
            eye, rot = orbit_pose(
                tuple(orbit.get("center", (0, 0, 0))),
                float(orbit.get("distance", 800)),
                float(orbit.get("yaw", 0)), float(orbit.get("pitch", 20)))
            cam["location"] = list(eye)
            cam["rotation"] = list(rot)
        else:
            if location is not None:
                cam["location"] = [float(x) for x in location]
            if look_at is not None:
                cam["rotation"] = list(look_at_rotation(
                    tuple(cam["location"]), tuple(look_at)))
            elif rotation is not None:
                cam["rotation"] = [float(x) for x in rotation]
        if fov is not None:
            cam["fov"] = float(fov)
        return json.dumps({"ok": True, "action": "set_camera",
                           "location": cam["location"],
                           "rotation": cam["rotation"]})

    def cnd_frame_actors(self, prefix=None, distance_factor=2.2,
                         pitch=25.0) -> str:
        from .camera_math import orbit_pose

        matched = [a for a in self.actors.values()
                   if not prefix or a["name"].startswith(prefix)]
        if not matched:
            return json.dumps({"ok": False, "error": "no actors to frame"})
        mins = [min(a["location"][i] - 50 * a["scale"][i] for a in matched)
                for i in range(3)]
        maxs = [max(a["location"][i] + 50 * a["scale"][i] for a in matched)
                for i in range(3)]
        center = tuple((mins[i] + maxs[i]) / 2.0 for i in range(3))
        radius = max(max(maxs[i] - mins[i] for i in range(3)) / 2.0, 100.0)
        eye, rot = orbit_pose(center, radius * float(distance_factor),
                              315.0, float(pitch))
        self.camera["location"] = list(eye)
        self.camera["rotation"] = list(rot)
        return json.dumps({"ok": True, "action": "frame_actors",
                           "count": len(matched), "center": list(center),
                           "camera": list(eye)})

    def cnd_screenshot(self, path=None, view="camera",
                       res_x=640, res_y=360) -> str:
        """mock 截图: 用 mock_viewport 渲 PNG。同步完成, 无 pending。"""
        from pathlib import Path

        from .mock_viewport import render_topdown_png, render_view_png

        if path is None:
            self._shot_counter += 1
            path = str(Path.home() / ".cindra" / "shots"
                       / f"mock_{self._shot_counter:03d}.png")
        if view == "topdown":
            render_topdown_png(self.actors, path,
                               width=int(res_x), height=int(res_x))
        else:
            render_view_png(self.actors, path,
                            tuple(self.camera["location"]),
                            tuple(self.camera["rotation"]),
                            fov=self.camera["fov"],
                            width=int(res_x), height=int(res_y))
        return json.dumps({"ok": True, "action": "screenshot",
                           "path": path, "view": view, "images": [path]})

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

    # 5) 视觉闭环: 截图确定性 + 相机姿态相关
    import tempfile
    from pathlib import Path as _P
    with tempfile.TemporaryDirectory() as _td:
        p1, p2, p3 = (_P(_td) / f"s{i}.png" for i in range(3))
        scene.cnd_set_camera(orbit={"center": [200, 200, 0],
                                    "distance": 1500, "yaw": 45, "pitch": 30})
        r = _json.loads(scene.cnd_screenshot(path=str(p1)))
        assert r["ok"] and r["images"] == [str(p1)] and p1.is_file()
        scene.cnd_screenshot(path=str(p2))
        assert p1.read_bytes() == p2.read_bytes(), "同姿态截图不一致"
        scene.cnd_set_camera(orbit={"center": [200, 200, 0],
                                    "distance": 1500, "yaw": 225, "pitch": 30})
        scene.cnd_screenshot(path=str(p3))
        assert p3.read_bytes() != p1.read_bytes(), "转了相机截图没变"
    print("✅ 视觉闭环: 截图确定性 + 姿态相关")

    # 6) 真资产 + 灯组: spawn_asset 校验路径 / light_rig 端到端
    bad = _json.loads(scene.cnd_spawn_asset("/Game/Nope.Nope"))
    assert not bad["ok"], "假路径应报错"
    good = _json.loads(scene.cnd_spawn_asset(
        "/Game/Props/SM_Crate_A.SM_Crate_A", location=[500, 500, 0]))
    assert good["ok"] and good["name"].startswith("Cindra_SM_Crate_A")
    res = scene_tools.dispatch(_T(), "light_rig", {"style": "horror"})
    assert res.get("ok"), f"light_rig 失败: {res}"
    lights = [a for a in scene.actors.values()
              if a["type"].startswith("light:")]
    envs = [a for a in scene.actors.values() if a["type"].startswith("env:")]
    assert lights and envs, "horror rig 应产出灯和环境"
    print(f"✅ 真资产 + light_rig(horror): {len(lights)} 灯, {len(envs)} 环境")

    print("\n场景自检 6/6 通过。地震后俯视图:")
    print(scene.render_topdown())
    return 0


if __name__ == "__main__":
    raise SystemExit(_selfcheck())
