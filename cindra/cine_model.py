"""cine_model —— mock Sequencer (运镜模式的内存后端)。

与真 UE 侧 ue_helpers/cine.py 同名同义的 cnd_seq_*(): 建序列 / 加相机 /
写关键帧 / 相机切换 / 渲染。渲染产"故事板": 均匀采样 N 帧, 按插值出的
相机位用 mock_viewport 渲 PNG —— mock 上也能"看片", 视觉闭环全链路离线可测。

自检: python3 -m cindra.cine_model
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_RENDER_DIR = Path.home() / ".cindra" / "renders"


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _sample_pose(keys: list[dict], frame: float) -> tuple[list, list]:
    """在关键帧序列上采样某帧的 (location, rotation)。线性插值, 够故事板用。"""
    if not keys:
        return [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]
    ks = sorted(keys, key=lambda k: k["frame"])
    if frame <= ks[0]["frame"]:
        return list(ks[0]["location"]), list(ks[0]["rotation"])
    if frame >= ks[-1]["frame"]:
        return list(ks[-1]["location"]), list(ks[-1]["rotation"])
    for lo, hi in zip(ks, ks[1:]):
        if lo["frame"] <= frame <= hi["frame"]:
            span = hi["frame"] - lo["frame"] or 1
            t = (frame - lo["frame"]) / span
            loc = [_lerp(lo["location"][i], hi["location"][i], t)
                   for i in range(3)]
            rot = [_lerp(lo["rotation"][i], hi["rotation"][i], t)
                   for i in range(3)]
            return loc, rot
    return list(ks[-1]["location"]), list(ks[-1]["rotation"])


class CineModel:
    """内存序列集合。scene_actors: 渲染故事板时读的场景 (callable -> actors)。"""

    def __init__(self, scene_actors=None, render_dir: str | None = None) -> None:
        self.sequences: dict[str, dict[str, Any]] = {}
        self._scene_actors = scene_actors or (lambda: {})
        self.render_dir = Path(render_dir) if render_dir else DEFAULT_RENDER_DIR

    # ---- cnd_seq_*: 与 ue_helpers/cine.py 同名同义 ----

    def cnd_seq_create(self, name, fps=24, seconds=8.0) -> str:
        if name in self.sequences:
            return json.dumps({"ok": False,
                               "error": f"sequence exists: {name}"})
        total = int(round(fps * seconds))
        self.sequences[name] = {
            "name": name, "fps": int(fps), "end_frame": total,
            "cameras": {}, "cuts": [], "rendered": [],
        }
        return json.dumps({"ok": True, "action": "seq_create", "name": name,
                           "fps": int(fps), "end_frame": total})

    def _seq(self, name):
        return self.sequences.get(name)

    def cnd_seq_add_camera(self, sequence, camera_name=None) -> str:
        seq = self._seq(sequence)
        if seq is None:
            return json.dumps({"ok": False,
                               "error": f"no sequence: {sequence}"})
        cam = camera_name or f"CineCam_{len(seq['cameras']) + 1}"
        if cam in seq["cameras"]:
            return json.dumps({"ok": False, "error": f"camera exists: {cam}"})
        seq["cameras"][cam] = {"keys": [], "fov": 60.0}
        return json.dumps({"ok": True, "action": "seq_add_camera",
                           "sequence": sequence, "camera": cam})

    def cnd_seq_add_keys(self, sequence, camera, keys) -> str:
        seq = self._seq(sequence)
        if seq is None:
            return json.dumps({"ok": False,
                               "error": f"no sequence: {sequence}"})
        cam = seq["cameras"].get(camera)
        if cam is None:
            return json.dumps({"ok": False, "error": f"no camera: {camera}"})
        for k in keys:
            if not ("frame" in k and "location" in k and "rotation" in k):
                return json.dumps({"ok": False,
                                   "error": "key 需含 frame/location/rotation"})
        cam["keys"].extend(json.loads(json.dumps(keys)))
        cam["keys"].sort(key=lambda k: k["frame"])
        return json.dumps({"ok": True, "action": "seq_add_keys",
                           "sequence": sequence, "camera": camera,
                           "total_keys": len(cam["keys"])})

    def cnd_seq_add_cut(self, sequence, camera, start_frame=None,
                        end_frame=None) -> str:
        seq = self._seq(sequence)
        if seq is None:
            return json.dumps({"ok": False,
                               "error": f"no sequence: {sequence}"})
        if camera not in seq["cameras"]:
            return json.dumps({"ok": False, "error": f"no camera: {camera}"})
        cut = {"camera": camera,
               "start": int(start_frame or 0),
               "end": int(end_frame if end_frame is not None
                          else seq["end_frame"])}
        seq["cuts"].append(cut)
        return json.dumps({"ok": True, "action": "seq_add_cut",
                           "sequence": sequence, **cut})

    def cnd_seq_list(self, sequence=None) -> str:
        if sequence is None:
            return json.dumps({"ok": True, "action": "seq_list",
                               "sequences": sorted(self.sequences)})
        seq = self._seq(sequence)
        if seq is None:
            return json.dumps({"ok": False,
                               "error": f"no sequence: {sequence}"})
        return json.dumps({"ok": True, "action": "seq_list",
                           "name": sequence, "fps": seq["fps"],
                           "end_frame": seq["end_frame"],
                           "cameras": {c: {"keys": len(v["keys"])}
                                       for c, v in seq["cameras"].items()},
                           "cuts": seq["cuts"]})

    def _active_camera(self, seq, frame):
        """按 cuts 决定该帧用哪台相机; 没 cuts 则用第一台。"""
        for cut in seq["cuts"]:
            if cut["start"] <= frame <= cut["end"]:
                return cut["camera"]
        cams = sorted(seq["cameras"])
        return cams[0] if cams else None

    def cnd_seq_render(self, sequence, out_dir=None, samples=8,
                       res=(640, 360)) -> str:
        """故事板渲染: 均匀采样 samples 帧, 逐帧按插值相机位渲 PNG。
        同步完成 (mock), 返回全部帧路径 + 首/中/末 3 帧作为 images。"""
        from .mock_viewport import render_view_png

        seq = self._seq(sequence)
        if seq is None:
            return json.dumps({"ok": False,
                               "error": f"no sequence: {sequence}"})
        if not seq["cameras"]:
            return json.dumps({"ok": False, "error": "sequence 还没有相机"})
        out = Path(out_dir) if out_dir else (self.render_dir / sequence)
        out.mkdir(parents=True, exist_ok=True)
        actors = self._scene_actors()
        total = seq["end_frame"]
        n = max(2, int(samples))
        frames = []
        for i in range(n):
            frame = round(i * total / (n - 1))
            cam_name = self._active_camera(seq, frame)
            cam = seq["cameras"][cam_name]
            loc, rot = _sample_pose(cam["keys"], frame)
            path = str(out / f"frame_{frame:04d}.png")
            render_view_png(actors, path, tuple(loc), tuple(rot),
                            fov=cam.get("fov", 60.0),
                            width=int(res[0]), height=int(res[1]))
            frames.append(path)
        seq["rendered"] = frames
        picks = [frames[0], frames[len(frames) // 2], frames[-1]]
        return json.dumps({"ok": True, "action": "seq_render",
                           "sequence": sequence, "frames": frames,
                           "out_dir": str(out), "images": picks})


def _selfcheck() -> None:
    import tempfile

    from .camera_math import orbit_keys
    from .mock_ue import MockScene

    ok = 0
    with tempfile.TemporaryDirectory() as td:
        scene = MockScene()
        for pos in [[c * 300 - 300, r * 300 - 300, 0]
                    for r in range(3) for c in range(3)]:
            scene.cnd_spawn(actor_type="cube", location=pos)
        model = CineModel(scene_actors=lambda: scene.actors, render_dir=td)

        # 1. 建序列 + 相机 + 关键帧
        assert json.loads(model.cnd_seq_create("demo", fps=24, seconds=8))["ok"]
        assert json.loads(model.cnd_seq_add_camera("demo", "CamA"))["ok"]
        keys = orbit_keys((0, 0, 0), 1500, n_keys=12, fps=24, seconds=8)
        r = json.loads(model.cnd_seq_add_keys("demo", "CamA", keys))
        assert r["ok"] and r["total_keys"] == 12
        ok += 1
        print("[1/4] create/add_camera/add_keys ✓")

        # 2. 渲染: 8 帧全部落盘
        rr = json.loads(model.cnd_seq_render("demo", samples=8))
        assert rr["ok"] and len(rr["frames"]) == 8
        assert all(Path(f).is_file() for f in rr["frames"])
        assert len(rr["images"]) == 3
        ok += 1
        print("[2/4] 故事板 8 帧落盘 + 3 采样图 ✓")

        # 3. 首帧 != 中帧 (相机在动), 重渲字节一致 (确定性)
        b0 = Path(rr["frames"][0]).read_bytes()
        b4 = Path(rr["frames"][4]).read_bytes()
        assert b0 != b4, "环绕运镜首/中帧不该一样"
        rr2 = json.loads(model.cnd_seq_render("demo", samples=8))
        assert Path(rr2["frames"][0]).read_bytes() == b0
        ok += 1
        print("[3/4] 姿态相关 + 确定性 ✓")

        # 4. cuts: 双相机切换 + 错误路径
        model.cnd_seq_add_camera("demo", "CamB")
        model.cnd_seq_add_keys("demo", "CamB",
                               [{"frame": 0, "location": [0, 0, 3000],
                                 "rotation": [-89, 0, 0]}])
        model.cnd_seq_add_cut("demo", "CamA", 0, 96)
        model.cnd_seq_add_cut("demo", "CamB", 97, 192)
        seq = model.sequences["demo"]
        assert model._active_camera(seq, 50) == "CamA"
        assert model._active_camera(seq, 150) == "CamB"
        assert not json.loads(model.cnd_seq_render("nope"))["ok"]
        assert not json.loads(model.cnd_seq_add_keys("demo", "CamX", []))["ok"]
        ok += 1
        print("[4/4] 相机切换 + 错误路径 ✓")
    print(f"cine_model 自检 {ok}/4 全部通过")


if __name__ == "__main__":
    _selfcheck()
