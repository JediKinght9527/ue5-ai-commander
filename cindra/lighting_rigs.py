"""lighting_rigs —— 风格化整套布光的纯数学 (arrange_scene 的灯光版)。

agent 调一次 light_rig(style), 这里读回场景包围盒, 按风格算出一整套
灯光 + 环境 (雾/后处理/太阳) 的生成参数, dispatch 逐个打到 transport。
引擎不需要"懂恐怖片" —— 纯编排 cnd_spawn_light / cnd_spawn_env 原语。

所有参数确定性: 同 (style, bounds, intensity) 永远同产物。

自检: python3 -m cindra.lighting_rigs
"""

from __future__ import annotations

import math

Vec3 = tuple[float, float, float]

STYLES = ("horror", "golden_hour", "studio", "night_neon", "overcast")
RIG_PREFIX = "CindraRig_"


def _op(func: str, **kwargs) -> dict:
    return {"func": func, "kwargs": kwargs}


def _ring(center: Vec3, radius: float, height: float, yaw_deg: float) -> Vec3:
    y = math.radians(yaw_deg)
    return (center[0] + radius * math.cos(y), center[1] + radius * math.sin(y), center[2] + height)


def build_rig(style: str, center: Vec3, radius: float, intensity: float = 0.6) -> list[dict]:
    """返回 [{func, kwargs}...] 的执行计划。radius = 场景半径 (cm)。"""
    if style not in STYLES:
        raise ValueError(f"unknown rig style: {style} (可选 {STYLES})")
    k = max(0.05, min(1.0, intensity))
    r = max(radius, 200.0)
    ops: list[dict] = []

    if style == "horror":
        # 冷月环境 + 贴地暖色残灯 + 浓雾 + 暗角: 经典恐怖走廊配方
        ops.append(
            _op(
                "cnd_spawn_env",
                kind="sun",
                params={"rotation": [-20, 140, 0], "intensity": 0.6 * k, "temperature": 9000},
            )
        )
        ops.append(
            _op(
                "cnd_spawn_env",
                kind="exp_height_fog",
                params={"density": 0.06 * k + 0.02, "height_falloff": 0.2},
            )
        )
        ops.append(
            _op(
                "cnd_spawn_env",
                kind="post_process",
                params={
                    "vignette_intensity": 0.7 * k + 0.2,
                    "auto_exposure_bias": -1.2 * k,
                    "film_grain_intensity": 0.35 * k,
                },
            )
        )
        for i, yaw in enumerate((30.0, 200.0)):
            loc = _ring(center, r * 0.55, 120.0, yaw)
            ops.append(
                _op(
                    "cnd_spawn_light",
                    light_type="spot",
                    name=f"{RIG_PREFIX}HorrorSpot_{i + 1}",
                    location=list(loc),
                    rotation=[-35.0, (yaw + 180.0) % 360.0, 0.0],
                    intensity=2500.0 * k,
                    temperature=2200.0,
                    attenuation_radius=r * 1.2,
                    cone_angle=32.0,
                )
            )
        ops.append(
            _op(
                "cnd_spawn_light",
                light_type="point",
                name=f"{RIG_PREFIX}HorrorFill",
                location=[center[0], center[1], center[2] + r * 0.8],
                intensity=400.0 * k,
                color=[0.35, 0.42, 0.65],
                attenuation_radius=r * 2.0,
            )
        )

    elif style == "golden_hour":
        # 低角度暖阳 + 天空散射 + 淡雾: 黄金时刻
        ops.append(_op("cnd_spawn_env", kind="sky_atmosphere", params={}))
        ops.append(
            _op(
                "cnd_spawn_env",
                kind="sun",
                params={"rotation": [-8, 250, 0], "intensity": 8.0 * k + 2.0, "temperature": 3200},
            )
        )
        ops.append(
            _op(
                "cnd_spawn_env",
                kind="exp_height_fog",
                params={"density": 0.015 * k, "height_falloff": 0.6},
            )
        )
        ops.append(
            _op(
                "cnd_spawn_light",
                light_type="point",
                name=f"{RIG_PREFIX}GoldBounce",
                location=[center[0], center[1], center[2] + r * 0.5],
                intensity=800.0 * k,
                temperature=4200.0,
                attenuation_radius=r * 2.2,
            )
        )

    elif style == "studio":
        # 三点布光: key / fill / rim, 中性色温, 无雾
        key_loc = _ring(center, r * 1.4, r * 0.9, 315.0)
        fill_loc = _ring(center, r * 1.6, r * 0.5, 45.0)
        rim_loc = _ring(center, r * 1.5, r * 1.1, 160.0)
        for name, loc, inten, temp, cone in (
            ("Key", key_loc, 8000.0 * k, 5600.0, 40.0),
            ("Fill", fill_loc, 3000.0 * k, 6500.0, 55.0),
            ("Rim", rim_loc, 5000.0 * k, 7000.0, 30.0),
        ):
            yaw_back = math.degrees(math.atan2(center[1] - loc[1], center[0] - loc[0]))
            pitch = -math.degrees(math.atan2(loc[2] - center[2], max(1.0, r)))
            ops.append(
                _op(
                    "cnd_spawn_light",
                    light_type="spot",
                    name=f"{RIG_PREFIX}{name}",
                    location=list(loc),
                    rotation=[pitch, yaw_back, 0.0],
                    intensity=inten,
                    temperature=temp,
                    attenuation_radius=r * 3.0,
                    cone_angle=cone,
                )
            )

    elif style == "night_neon":
        # 冷夜环境 + 霓虹色点灯环绕 + 泛光: 赛博夜巷
        ops.append(
            _op(
                "cnd_spawn_env",
                kind="sun",
                params={"rotation": [-30, 0, 0], "intensity": 0.15, "temperature": 12000},
            )
        )
        ops.append(
            _op(
                "cnd_spawn_env",
                kind="exp_height_fog",
                params={"density": 0.035 * k + 0.01, "height_falloff": 0.3},
            )
        )
        ops.append(
            _op(
                "cnd_spawn_env",
                kind="post_process",
                params={"bloom_intensity": 2.5 * k + 0.5, "auto_exposure_bias": -0.6 * k},
            )
        )
        neon = [(1.0, 0.1, 0.7), (0.1, 0.9, 1.0), (0.9, 0.3, 0.1), (0.4, 0.1, 1.0)]
        for i, rgb in enumerate(neon):
            loc = _ring(center, r * 0.8, 180.0, 90.0 * i + 20.0)
            ops.append(
                _op(
                    "cnd_spawn_light",
                    light_type="point",
                    name=f"{RIG_PREFIX}Neon_{i + 1}",
                    location=list(loc),
                    intensity=3500.0 * k,
                    color=list(rgb),
                    attenuation_radius=r * 0.9,
                )
            )

    elif style == "overcast":
        # 阴天: 高角度弱冷阳 + 天光 + 薄雾, 低反差
        ops.append(_op("cnd_spawn_env", kind="sky_atmosphere", params={}))
        ops.append(_op("cnd_spawn_env", kind="sky_light", params={}))
        ops.append(
            _op(
                "cnd_spawn_env",
                kind="sun",
                params={"rotation": [-65, 40, 0], "intensity": 2.0 * k + 0.5, "temperature": 7000},
            )
        )
        ops.append(
            _op(
                "cnd_spawn_env",
                kind="exp_height_fog",
                params={"density": 0.02 * k, "height_falloff": 0.8},
            )
        )

    return ops


def _selfcheck() -> None:
    ok = 0
    # 1. 确定性: 同输入两次产出一致
    a = build_rig("horror", (0, 0, 0), 800, 0.7)
    b = build_rig("horror", (0, 0, 0), 800, 0.7)
    assert a == b, "rig 不确定!"
    ok += 1
    print("[1/4] 确定性 ✓")

    # 2. horror 配方: 至少 1 个低色温 spot + 雾 + 后处理
    spots = [o for o in a if o["kwargs"].get("light_type") == "spot"]
    assert spots and all(o["kwargs"]["temperature"] <= 2500 for o in spots)
    kinds = {o["kwargs"].get("kind") for o in a if o["func"] == "cnd_spawn_env"}
    assert "exp_height_fog" in kinds and "post_process" in kinds
    ok += 1
    print("[2/4] horror 配方 ✓")

    # 3. golden_hour: 低角度暖色太阳
    g = build_rig("golden_hour", (0, 0, 0), 800)
    suns = [o for o in g if o["kwargs"].get("kind") == "sun"]
    assert suns and suns[0]["kwargs"]["params"]["temperature"] <= 3500
    assert suns[0]["kwargs"]["params"]["rotation"][0] > -15, "黄金时刻应低角度"
    ok += 1
    print("[3/4] golden_hour 配方 ✓")

    # 4. studio 三点 + 全风格可构建 + 未知风格报错
    s = build_rig("studio", (100, 200, 0), 500)
    names = {o["kwargs"].get("name", "") for o in s}
    assert {f"{RIG_PREFIX}Key", f"{RIG_PREFIX}Fill", f"{RIG_PREFIX}Rim"} <= names
    for style in STYLES:
        assert build_rig(style, (0, 0, 0), 400), style
    try:
        build_rig("disco", (0, 0, 0), 400)
        raise AssertionError("应报未知风格")
    except ValueError:
        pass
    ok += 1
    print("[4/4] studio 三点 + 全风格 + 报错 ✓")
    print(f"lighting_rigs 自检 {ok}/4 全部通过")


if __name__ == "__main__":
    _selfcheck()
