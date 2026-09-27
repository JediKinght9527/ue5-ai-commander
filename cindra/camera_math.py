"""camera_math —— 相机与运镜关键帧的纯数学。

Pillar 1 (视觉闭环) 和 Pillar 3 (运镜) 共用: mock 视口、真 UE 视口相机、
Sequencer 关键帧全都消费这里的输出 —— 数学只写一份, 双后端才对得上。

坐标/旋转约定与 UE 一致: 位置 (x, y, z) 厘米, 旋转 (pitch, yaw, roll) 度;
yaw=0 朝 +X, 逆时针为正; pitch 正抬头。

自检: python3 -m cindra.camera_math
"""
from __future__ import annotations

import math

Vec3 = tuple[float, float, float]


def as_vec3(v) -> Vec3:
    """把任意 3 元序列收敛成 Vec3。

    直接写 tuple(v) 推出来是 tuple[float, ...], 传给标着 Vec3 的参数会报错;
    这里显式拆三项, 顺带对长度不对的输入给出明确错误而不是静默截断。
    """
    x, y, z = v
    return (float(x), float(y), float(z))
Rot3 = tuple[float, float, float]  # (pitch, yaw, roll)


def look_at_rotation(eye: Vec3, target: Vec3) -> Rot3:
    """从 eye 看向 target 的旋转 (roll 恒 0)。与 ue_helpers/vision.py 同式。"""
    dx = target[0] - eye[0]
    dy = target[1] - eye[1]
    dz = target[2] - eye[2]
    yaw = math.degrees(math.atan2(dy, dx))
    pitch = math.degrees(math.atan2(dz, math.sqrt(dx * dx + dy * dy)))
    return (pitch, yaw, 0.0)


def orbit_pose(center: Vec3, distance: float, yaw_deg: float,
               pitch_deg: float) -> tuple[Vec3, Rot3]:
    """环绕位: 相机在 center 周围 distance 处, 按 yaw/pitch 角摆位并看向中心。"""
    yaw = math.radians(yaw_deg)
    pitch = math.radians(pitch_deg)
    x = center[0] - distance * math.cos(pitch) * math.cos(yaw)
    y = center[1] - distance * math.cos(pitch) * math.sin(yaw)
    z = center[2] + distance * math.sin(pitch)
    eye = (x, y, z)
    return eye, look_at_rotation(eye, center)


def _ease_in_out(t: float) -> float:
    """smoothstep; 让运镜起止柔和。"""
    return t * t * (3.0 - 2.0 * t)


def _frames(n_keys: int, fps: int, seconds: float) -> list[int]:
    total = max(1, int(round(fps * seconds)))
    if n_keys <= 1:
        return [0]
    return [round(i * total / (n_keys - 1)) for i in range(n_keys)]


def orbit_keys(center: Vec3, distance: float = 800.0, pitch: float = 20.0,
               start_yaw: float = 0.0, revolutions: float = 1.0,
               n_keys: int = 24, fps: int = 24,
               seconds: float = 8.0, ease: bool = True) -> list[dict]:
    """环绕运镜关键帧。返回 [{frame, location, rotation}]。"""
    keys = []
    for i, frame in enumerate(_frames(n_keys, fps, seconds)):
        t = i / (n_keys - 1) if n_keys > 1 else 0.0
        tt = _ease_in_out(t) if ease else t
        yaw = start_yaw + 360.0 * revolutions * tt
        eye, rot = orbit_pose(center, distance, yaw, pitch)
        keys.append({"frame": frame, "location": list(eye),
                     "rotation": list(rot)})
    return keys


def dolly_keys(start: Vec3, end: Vec3, look_at: Vec3 | None = None,
               n_keys: int = 12, fps: int = 24, seconds: float = 6.0,
               ease: bool = True) -> list[dict]:
    """推拉运镜: start -> end 直线, 可选恒看向 look_at。"""
    keys = []
    for i, frame in enumerate(_frames(n_keys, fps, seconds)):
        t = i / (n_keys - 1) if n_keys > 1 else 0.0
        tt = _ease_in_out(t) if ease else t
        # 显式写三项而不是推导式: 推导式推成 tuple[float, ...], 传给 Vec3 会报
        loc: Vec3 = (
            start[0] + (end[0] - start[0]) * tt,
            start[1] + (end[1] - start[1]) * tt,
            start[2] + (end[2] - start[2]) * tt,
        )
        rot = (look_at_rotation(loc, look_at) if look_at
               else look_at_rotation(start, end))
        keys.append({"frame": frame, "location": list(loc),
                     "rotation": list(rot)})
    return keys


def crane_keys(center: Vec3, distance: float = 600.0,
               start_height: float = 100.0, end_height: float = 900.0,
               yaw: float = 315.0, n_keys: int = 12, fps: int = 24,
               seconds: float = 6.0, ease: bool = True) -> list[dict]:
    """升降运镜: 固定方位角, 相机从低到高扫过, 恒看中心。"""
    yaw_r = math.radians(yaw)
    keys = []
    for i, frame in enumerate(_frames(n_keys, fps, seconds)):
        t = i / (n_keys - 1) if n_keys > 1 else 0.0
        tt = _ease_in_out(t) if ease else t
        h = start_height + (end_height - start_height) * tt
        loc = (center[0] - distance * math.cos(yaw_r),
               center[1] - distance * math.sin(yaw_r),
               center[2] + h)
        keys.append({"frame": frame, "location": list(loc),
                     "rotation": list(look_at_rotation(loc, center))})
    return keys


def flyover_keys(start: Vec3, end: Vec3, height: float = 500.0,
                 n_keys: int = 16, fps: int = 24, seconds: float = 8.0,
                 ease: bool = True) -> list[dict]:
    """飞掠: 在 height 高度从 start 上空飞到 end 上空, 镜头前下方看。"""
    keys = []
    for i, frame in enumerate(_frames(n_keys, fps, seconds)):
        t = i / (n_keys - 1) if n_keys > 1 else 0.0
        tt = _ease_in_out(t) if ease else t
        loc = (start[0] + (end[0] - start[0]) * tt,
               start[1] + (end[1] - start[1]) * tt,
               height)
        ahead = (loc[0] + (end[0] - start[0]) * 0.25,
                 loc[1] + (end[1] - start[1]) * 0.25, 0.0)
        keys.append({"frame": frame, "location": list(loc),
                     "rotation": list(look_at_rotation(loc, ahead))})
    return keys


PRESETS = {
    "orbit": orbit_keys,
    "dolly": dolly_keys,
    "crane": crane_keys,
    "flyover": flyover_keys,
}


def _selfcheck() -> None:
    ok = 0
    # 1. look_at 指向正确: 从 (0,0,0) 看 (100,0,0) 应 yaw=0 pitch=0
    r = look_at_rotation((0, 0, 0), (100, 0, 0))
    assert abs(r[0]) < 1e-9 and abs(r[1]) < 1e-9, r
    r = look_at_rotation((0, 0, 0), (0, 100, 0))
    assert abs(r[1] - 90.0) < 1e-9, r
    ok += 1
    print("[1/4] look_at_rotation ✓")

    # 2. orbit_pose 距离守恒 + 朝向中心
    eye, rot = orbit_pose((0, 0, 0), 500, 123, 30)
    d = math.sqrt(sum(v * v for v in eye))
    assert abs(d - 500) < 1e-6, d
    r2 = look_at_rotation(eye, (0, 0, 0))
    assert all(abs(a - b) < 1e-9 for a, b in zip(rot, r2, strict=True))
    ok += 1
    print("[2/4] orbit_pose ✓")

    # 3. orbit_keys 确定性 + 首末帧正确
    k1 = orbit_keys((0, 0, 0), 800, n_keys=24, fps=24, seconds=8)
    k2 = orbit_keys((0, 0, 0), 800, n_keys=24, fps=24, seconds=8)
    assert k1 == k2, "关键帧不确定!"
    assert k1[0]["frame"] == 0 and k1[-1]["frame"] == 192
    # 转满一圈: 首末位置几乎重合
    assert all(abs(a - b) < 1e-6
               for a, b in zip(k1[0]["location"], k1[-1]["location"], strict=True))
    ok += 1
    print("[3/4] orbit_keys 确定性 + 闭环 ✓")

    # 4. dolly/crane/flyover 形状合理
    dk = dolly_keys((0, 0, 100), (500, 0, 100), n_keys=5)
    assert dk[0]["location"][0] == 0 and dk[-1]["location"][0] == 500
    ck = crane_keys((0, 0, 0), start_height=100, end_height=900, n_keys=5)
    assert ck[-1]["location"][2] > ck[0]["location"][2]
    fk = flyover_keys((0, 0, 0), (1000, 0, 0), height=500, n_keys=5)
    assert all(k["location"][2] == 500 for k in fk)
    assert all(k["rotation"][0] < 0 for k in fk), "飞掠应俯视"
    ok += 1
    print("[4/4] dolly/crane/flyover ✓")
    print(f"camera_math 自检 {ok}/4 全部通过")


if __name__ == "__main__":
    _selfcheck()
