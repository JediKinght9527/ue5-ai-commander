"""demo —— 60 秒上手 demo: 不用 UE、不用 API key, 一键生成一张"森林"图。

做的事情:
  1. 用 PCG 管线 (landscape → sampler → filter → transform → spawner)
     在 200x200m 的地形上撒一片橡树林 (只有 mock, 全确定性)
  2. 把结果渲成两张 PNG: 俯视图 + 45° 透视图
  3. 终端打印 ASCII 俯视图

用法:
  python -m cindra.demo              # 生成 PNG 到当前目录 (demo_topdown.png / demo_view.png)
  python -m cindra.demo --dir out/   # 指定输出目录
  python -m cindra.demo --no-png     # 只打印 ASCII

自检: python3 -m cindra.demo --check
"""
from __future__ import annotations

import argparse
import os
import sys

# 让 demo 在仓库外也能跑 (pip install -e 或直接 clone 后运行)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def build_forest_scene():
    """搭一片 200x200m 的橡树林 (确定性 PCG 管线)。

    返回 (pcg_graph, mock_scene, spawn_points)。
    """
    from cindra.mock_ue import MockScene
    from cindra.pcg_model import PCGGraph

    g = PCGGraph()
    g.add_node("landscape_input", "terrain",
               {"width": 20000, "depth": 20000, "height_min": 0,
                "height_max": 400, "noise_scale": 0.3, "seed": 7})
    g.add_node("surface_sampler", "sampler",
               {"points_per_sqm": 0.02, "seed": 42})
    g.add_node("density_noise", "noise",
               {"amplitude": 0.25, "frequency": 1.5, "seed": 77})
    g.add_node("slope_filter", "flat_only",
               {"max_density_as_flat": 0.2, "invert": False})
    g.add_node("transform_points", "vary",
               {"offset_min": [-30, -30, 0], "offset_max": [30, 30, 0],
                "rotation_min": [0, 0, 0], "rotation_max": [0, 360, 0],
                "scale_min": 0.7, "scale_max": 1.4, "seed": 5})
    g.add_node("static_mesh_spawner", "trees",
               {"mesh_path": "/Game/Nature/Trees/Oak_Tree",
                "density_threshold": 0.1})
    g.connect("terrain", "landscape", "sampler", "source")
    for a, b in [("sampler", "noise"), ("noise", "flat_only"),
                 ("flat_only", "vary"), ("vary", "trees")]:
        g.connect(a, "points", b, "points")

    result = g.execute()
    assert result["ok"], f"PCG 图执行失败: {result}"

    # 把 spawn 点装进 MockScene, 便于用 mock_viewport 渲 PNG
    scene = MockScene()
    trees = g.nodes["trees"]["cache"]["points"]
    for i, p in enumerate(trees):
        scene.cnd_spawn(
            actor_type="cube", name=f"Oak_{i:03d}",
            location=p["location"],
            rotation=p["rotation"],
            scale=p["scale"],
        )

    return g, scene, trees


def render_pngs(scene, out_dir: str) -> tuple[str, str]:
    """把场景渲成俯视图 + 透视图两张 PNG, 返回路径。"""
    from cindra.mock_viewport import render_topdown_png

    os.makedirs(out_dir, exist_ok=True)
    top = os.path.join(out_dir, "demo_topdown.png")
    view = os.path.join(out_dir, "demo_view.png")

    render_topdown_png(scene.actors, top, width=800, height=800, span=12000)
    # 特写视角: 站树林边上朝里看, 树会显得大而密集
    _render_forest_closeup(scene.actors, view, width=1280, height=720)

    return top, view


def _render_forest_closeup(actors, path: str, width: int = 1280,
                           height: int = 720) -> str:
    """给 demo 用的"树林特写"渲染器。

    不是通用 mock_viewport (那个追求确定性), 这个是给 README 截图用的:
    把每个 spawn 点画成深绿树冠 + 浅绿高光 + 灰树干, 让画面一眼看出是森林。
    确定性同样保持 (同输入同输出), 但目标是"好看"。

    用简单的投影: 相机在世界 (cx, cy, cz) 看向原点, 按深度 painter 排序。
    """
    import math

    from cindra.imaging import write_png

    class _C:
        def __init__(self, w, h):
            self.w, self.h = w, h
            self.px = [[(26, 32, 38)] * w for _ in range(h)]

        def set(self, x, y, rgb):
            if 0 <= x < self.w and 0 <= y < self.h:
                self.px[y][x] = rgb

        def disc(self, cx, cy, r, rgb):
            r = int(r) + 1
            for y in range(int(cy) - r, int(cy) + r + 1):
                for x in range(int(cx) - r, int(cx) + r + 1):
                    if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                        self.set(x, y, rgb)

        def rows(self):
            out = []
            for y in range(self.h):
                row = bytearray()
                for x in range(self.w):
                    row.extend(self.px[y][x])
                out.append(bytes(row))
            return out

    # 相机: 东南方向, 俯角, 看向森林中心
    cam = (6000.0, 6000.0, 2600.0)
    center = (0.0, 0.0, 80.0)
    fwd = tuple(center[i] - cam[i] for i in range(3))
    fl = math.sqrt(sum(v * v for v in fwd))
    fwd = tuple(v / fl for v in fwd)
    right = (-fwd[1], fwd[0], 0.0)
    rl = math.sqrt(right[0] ** 2 + right[1] ** 2)
    right = tuple(v / rl for v in right)
    up = (fwd[1] * right[2] - fwd[2] * right[1],
          fwd[2] * right[0] - fwd[0] * right[2],
          fwd[0] * right[1] - fwd[1] * right[0])
    focal = (width / 2) / math.tan(math.radians(45) / 2)

    cv = _C(width, height)

    # 地面: 大片暗绿渐变 (简单均匀色)
    # 原来这里还有个"画地面网格"的三层循环, 循环体只有 pass —— 注释说
    # "投影一个地面点"但什么也没投影, 是没写完的残留, 直接删掉。
    for y in range(height):
        shade = 30 + int(18 * y / height)
        row_rgb = (shade, 40 + int(10 * y / height), shade - 8)
        cv.px[y] = [row_rgb] * width

    # painter: 从远到近
    proj = []
    for a in actors.values():
        loc = a["location"]
        d = tuple(loc[i] - cam[i] for i in range(3))
        depth = d[0] * fwd[0] + d[1] * fwd[1] + d[2] * fwd[2]
        if depth <= 50.0:
            continue
        px = d[0] * right[0] + d[1] * right[1] + d[2] * right[2]
        py = d[0] * up[0] + d[1] * up[1] + d[2] * up[2]
        sx = width / 2 + px / depth * focal
        sy = height / 2 - py / depth * focal
        s = a["scale"][0] * a["scale"][1]
        proj.append((depth, a["name"], sx, sy, s))
    proj.sort(key=lambda t: (-t[0], t[1]))

    for depth, _name, sx, sy, s in proj:
        # 树的大小随深度衰减
        base = focal * 260.0 * s / depth   # 树冠半径 (px)
        if base < 2.0:
            continue
        # 树干
        trunk = max(2.0, base * 0.28)
        for dy in range(int(base * 1.1)):
            cv.disc(sx, sy + dy, trunk * (1 - dy / (base * 1.4)), (90, 62, 42))
        # 树冠: 深绿 + 高光
        cv.disc(sx, sy - base * 0.9, base, (38, 92, 58))
        cv.disc(sx - base * 0.35, sy - base * 1.15, base * 0.6, (30, 76, 50))
        cv.disc(sx + base * 0.3, sy - base * 0.95, base * 0.55, (46, 104, 64))

    write_png(path, width, height, cv.rows())
    return path


def main() -> int:
    p = argparse.ArgumentParser(description="Cindra 一键 demo (无 UE, 无 key)")
    p.add_argument("--dir", default=".", help="PNG 输出目录")
    p.add_argument("--no-png", action="store_true", help="只打印 ASCII, 不生成 PNG")
    p.add_argument("--check", action="store_true", help="自检模式")
    args, _ = p.parse_known_args()

    if args.check:
        return _check()

    g, scene, trees = build_forest_scene()

    print("=== Cindra demo: 一片橡树林 (纯 mock, 无 UE, 无 API key) ===")
    print()
    print("PCG 管线: landscape_input → surface_sampler → density_noise")
    print("          → slope_filter(只留平坦) → transform_points → static_mesh_spawner")
    print()
    print(f"spawn 点: {len(trees)} 棵橡树 (200x200m, 只长在平坦区域)")
    print()

    # ASCII 俯视图
    print(g.render())
    print()
    print(g.render_stats())

    if not args.no_png:
        top, view = render_pngs(scene, args.dir)
        print()
        print(f"俯视图 PNG: {top}")
        print(f"透视图 PNG: {view}")

    return 0


def _check() -> int:
    """确定性 + 可重复性自检。"""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        # 同一份种子建两次 → 树的位置一致
        g1, s1, trees1 = build_forest_scene()
        g2, s2, trees2 = build_forest_scene()
        assert len(trees1) == len(trees2) == len(trees1), "两次建树数量不一致"
        assert all(a["location"] == b["location"]
                   for a, b in zip(trees1, trees2, strict=True)), "两次树的位置不一致"
        print(f"[1/3] 确定性: 两次运行产出 {len(trees1)} 棵树, 位置完全一致 ✓")

        # PNG 两次渲染字节级一致
        from cindra.mock_viewport import render_topdown_png
        top1 = os.path.join(td, "a.png")
        top2 = os.path.join(td, "b.png")
        render_topdown_png(s1.actors, top1, span=12000)
        render_topdown_png(s2.actors, top2, span=12000)
        with open(top1, "rb") as f1, open(top2, "rb") as f2:
            assert f1.read() == f2.read(), "PNG 渲染不确定"
        print("[2/3] PNG 渲染确定性 ✓")

        # PNG 是合法文件且非空
        from cindra.imaging import read_png_size
        w, h = read_png_size(top1)
        assert w > 0 and h > 0
        print(f"[3/3] 合法 PNG ({w}x{h}) ✓")

    print("\ndemo 自检 3/3 通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
