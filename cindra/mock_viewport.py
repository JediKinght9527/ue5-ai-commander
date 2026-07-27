"""mock_viewport —— 把 MockScene 确定性地渲成 PNG (mock 后端的"眼睛")。

真 UE 后端的 cnd_screenshot 拍的是真视口; mock 后端拍的就是这里的输出。
不追求好看, 追求两点:
  1. 确定性 —— 同一场景渲两次字节级一致 (纯整数填充, 无抗锯齿)
  2. 姿态相关 —— 动了 actor 或动了相机, 图必须变
这样视觉闭环 (act -> screenshot -> critique -> iterate) 在 Mac 上离线可测。

自检: python3 -m cindra.mock_viewport
"""
from __future__ import annotations

import math
from typing import Any

from .camera_math import Rot3, Vec3
from .imaging import write_png

# 类型 -> RGB。asset:/light:/env: 前缀族给统一色, 一眼能分出景别层次。
_PALETTE: list[tuple[str, tuple[int, int, int]]] = [
    ("cube", (150, 150, 160)),
    ("sphere", (90, 130, 230)),
    ("cylinder", (185, 155, 110)),
    ("cone", (225, 145, 60)),
    ("plane", (75, 85, 75)),
    ("light:", (255, 220, 90)),
    ("asset:", (95, 185, 105)),
    ("env:", (150, 95, 190)),
    ("pcg:", (60, 160, 150)),
]
_DEFAULT_COLOR = (205, 85, 85)
_BG = (24, 26, 30)
_GRID = (38, 42, 48)
_BASE_UU = 100.0  # 引擎基础形状半径量级 (cube 100uu)


def _color_for(actor_type: str) -> tuple[int, int, int]:
    for prefix, rgb in _PALETTE:
        if actor_type.startswith(prefix):
            return rgb
    return _DEFAULT_COLOR


class _Canvas:
    def __init__(self, width: int, height: int) -> None:
        self.w = width
        self.h = height
        self.px = [list(_BG) for _ in range(width * height)]

    def set(self, x: int, y: int, rgb: tuple[int, int, int]) -> None:
        if 0 <= x < self.w and 0 <= y < self.h:
            self.px[y * self.w + x] = list(rgb)

    def fill_rect(self, cx: float, cy: float, hx: float, hy: float,
                  yaw_deg: float, rgb: tuple[int, int, int]) -> None:
        """旋转矩形填充: 对包围盒逐像素做逆旋转判内。纯整数扫描, 无 AA。"""
        yaw = math.radians(yaw_deg)
        c, s = math.cos(yaw), math.sin(yaw)
        r = math.sqrt(hx * hx + hy * hy)
        x0, x1 = int(cx - r) - 1, int(cx + r) + 1
        y0, y1 = int(cy - r) - 1, int(cy + r) + 1
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                dx, dy = x - cx, y - cy
                lx = dx * c + dy * s
                ly = -dx * s + dy * c
                if abs(lx) <= hx and abs(ly) <= hy:
                    self.set(x, y, rgb)

    def fill_disc(self, cx: float, cy: float, radius: float,
                  rgb: tuple[int, int, int]) -> None:
        r = int(radius) + 1
        for y in range(int(cy) - r, int(cy) + r + 1):
            for x in range(int(cx) - r, int(cx) + r + 1):
                if (x - cx) ** 2 + (y - cy) ** 2 <= radius * radius:
                    self.set(x, y, rgb)

    def rows(self) -> list[bytes]:
        out = []
        for y in range(self.h):
            row = bytearray()
            for x in range(self.w):
                row.extend(self.px[y * self.w + x])
            out.append(bytes(row))
        return out


def _sorted_actors(actors: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    # painter order: 低的先画, 名字做平局项 -> 确定性
    return sorted(actors.values(),
                  key=lambda a: (a["location"][2], a["name"]))


def render_topdown_png(actors: dict[str, dict[str, Any]], path: str,
                       width: int = 640, height: int = 640,
                       span: float = 1500.0) -> str:
    """俯视图: 世界 X 向右, Y 向下, [-span, span] 映射到整幅画。"""
    cv = _Canvas(width, height)
    # 网格线每 500uu 一条, 给 agent 尺度感
    step = 500.0
    k = -int(span // step)
    while k * step <= span:
        gx = int((k * step + span) / (2 * span) * (width - 1))
        gy = int((k * step + span) / (2 * span) * (height - 1))
        for y in range(height):
            cv.set(gx, y, _GRID)
        for x in range(width):
            cv.set(x, gy, _GRID)
        k += 1
    ppu = width / (2 * span)  # 像素/uu
    for a in _sorted_actors(actors):
        x, y = a["location"][0], a["location"][1]
        cx = (x + span) / (2 * span) * (width - 1)
        cy = (y + span) / (2 * span) * (height - 1)
        rgb = _color_for(a["type"])
        if a["type"].startswith("light:"):
            cv.fill_disc(cx, cy, 6.0, rgb)
            continue
        if a["type"].startswith("env:"):
            cv.fill_disc(cx, cy, 4.0, rgb)
            continue
        hx = max(2.0, _BASE_UU / 2 * a["scale"][0] * ppu)
        hy = max(2.0, _BASE_UU / 2 * a["scale"][1] * ppu)
        cv.fill_rect(cx, cy, hx, hy, a["rotation"][1], rgb)
    write_png(path, width, height, cv.rows())
    return path


def render_view_png(actors: dict[str, dict[str, Any]], path: str,
                    cam_loc: Vec3, cam_rot: Rot3, fov: float = 60.0,
                    width: int = 640, height: int = 360) -> str:
    """粗透视图: 投影 actor 中心, 按深度画缩放方块。糙, 但姿态相关且确定。"""
    pitch = math.radians(cam_rot[0])
    yaw = math.radians(cam_rot[1])
    cp, sp = math.cos(pitch), math.sin(pitch)
    cy_, sy_ = math.cos(yaw), math.sin(yaw)
    f = (cp * cy_, cp * sy_, sp)          # forward
    r = (-sy_, cy_, 0.0)                  # right (+yaw 从 +X 转向 +Y)
    u = (f[1] * r[2] - f[2] * r[1],       # up = f x r
         f[2] * r[0] - f[0] * r[2],
         f[0] * r[1] - f[1] * r[0])
    focal = (width / 2) / math.tan(math.radians(fov) / 2)

    cv = _Canvas(width, height)
    # 按深度从远到近排序 (painter), 名字平局
    projected = []
    for a in actors.values():
        d = tuple(a["location"][i] - cam_loc[i] for i in range(3))
        depth = d[0] * f[0] + d[1] * f[1] + d[2] * f[2]
        if depth <= 10.0:
            continue
        px = d[0] * r[0] + d[1] * r[1] + d[2] * r[2]
        py = d[0] * u[0] + d[1] * u[1] + d[2] * u[2]
        sx = width / 2 + px / depth * focal
        sy = height / 2 - py / depth * focal
        projected.append((depth, a["name"], sx, sy, a))
    projected.sort(key=lambda t: (-t[0], t[1]))
    for depth, _name, sx, sy, a in projected:
        rgb = _color_for(a["type"])
        avg_scale = (a["scale"][0] + a["scale"][1] + a["scale"][2]) / 3.0
        half = focal * (_BASE_UU / 2 * avg_scale) / depth
        half = max(1.0, min(200.0, half))
        if a["type"].startswith("light:"):
            cv.fill_disc(sx, sy, max(2.0, half / 2), rgb)
        else:
            cv.fill_rect(sx, sy, half, half, 0.0, rgb)
    write_png(path, width, height, cv.rows())
    return path


def _selfcheck() -> None:
    import tempfile
    from pathlib import Path

    from .mock_ue import MockScene

    ok = 0
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        scene = MockScene()

        # 1. 空场景也能渲出合法 PNG
        p_empty = td / "empty.png"
        render_topdown_png(scene.actors, str(p_empty))
        from .imaging import read_png_size
        assert read_png_size(p_empty) == (640, 640)
        ok += 1
        print("[1/4] 空场景合法 PNG ✓")

        # 2. 3x3 网格, 渲两次字节级一致
        for pos in [[c * 300 - 300, r * 300 - 300, 0]
                    for r in range(3) for c in range(3)]:
            scene.cnd_spawn(actor_type="cube", location=pos)
        p1, p2 = td / "g1.png", td / "g2.png"
        render_topdown_png(scene.actors, str(p1))
        render_topdown_png(scene.actors, str(p2))
        assert p1.read_bytes() == p2.read_bytes(), "渲染不确定!"
        ok += 1
        print("[2/4] 俯视图确定性 ✓")

        # 3. 动一个 actor, 图必须变
        name0 = next(iter(scene.actors))
        scene.cnd_move(name0, [900, 900, 0])
        p3 = td / "g3.png"
        render_topdown_png(scene.actors, str(p3))
        assert p3.read_bytes() != p1.read_bytes(), "动了 actor 图没变!"
        ok += 1
        print("[3/4] 场景变化反映到图 ✓")

        # 4. 透视图: 相机转 90 度, 图必须变
        from .camera_math import orbit_pose
        eye_a, rot_a = orbit_pose((0, 0, 0), 1200, 0, 25)
        eye_b, rot_b = orbit_pose((0, 0, 0), 1200, 90, 25)
        pa, pb = td / "va.png", td / "vb.png"
        render_view_png(scene.actors, str(pa), eye_a, rot_a)
        render_view_png(scene.actors, str(pb), eye_b, rot_b)
        assert pa.read_bytes() != pb.read_bytes(), "转了相机图没变!"
        # 且同参重渲一致
        pa2 = td / "va2.png"
        render_view_png(scene.actors, str(pa2), eye_a, rot_a)
        assert pa2.read_bytes() == pa.read_bytes()
        ok += 1
        print("[4/4] 透视图姿态相关 + 确定性 ✓")
    print(f"mock_viewport 自检 {ok}/4 全部通过")


if __name__ == "__main__":
    _selfcheck()
