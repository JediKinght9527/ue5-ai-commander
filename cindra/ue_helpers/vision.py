"""ue_helpers.vision —— 视口相机 + 截图原语 (agent 的"眼睛")。

真 UE 注入源。关键设计:
- 相机用 UnrealEditorSubsystem (5.x; EditorLevelLibrary 的同名接口在 5.7 已弃用)
- cnd_screenshot 发射即返回 (take_high_res_screenshot 是 latent task, 跨编辑器
  tick 才完成; 在阻塞的 remote-exec 调用里轮询 is_task_done 永远不会翻转)。
  等文件落盘由 cindra 侧 (vision 工具 dispatch) 轮询, 不在引擎侧等。
- 图片永远走磁盘, 只回传路径 —— remote-exec 输出管不了 base64 大包。
"""

SOURCE = r'''
import json
import math
import os
import time
import unreal

_SHOT_COUNTER = {"n": 0}


def _ues():
    return unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)


def _eas_v():
    return unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def _look_at_rotation(eye, target):
    dx = target[0] - eye[0]
    dy = target[1] - eye[1]
    dz = target[2] - eye[2]
    yaw = math.degrees(math.atan2(dy, dx))
    pitch = math.degrees(math.atan2(dz, math.sqrt(dx * dx + dy * dy)))
    return (pitch, yaw, 0.0)


def _orbit_pose(center, distance, yaw_deg, pitch_deg):
    yaw = math.radians(yaw_deg)
    pitch = math.radians(pitch_deg)
    x = center[0] - distance * math.cos(pitch) * math.cos(yaw)
    y = center[1] - distance * math.cos(pitch) * math.sin(yaw)
    z = center[2] + distance * math.sin(pitch)
    eye = (x, y, z)
    return eye, _look_at_rotation(eye, center)


def cnd_set_camera(location=None, rotation=None, look_at=None, orbit=None):
    """设置编辑器视口相机。orbit={"center","distance","yaw","pitch"} 或
    location+rotation, 或 location+look_at。"""
    cur_loc, cur_rot = _ues().get_level_viewport_camera_info()
    loc = [cur_loc.x, cur_loc.y, cur_loc.z]
    rot = [cur_rot.pitch, cur_rot.yaw, cur_rot.roll]
    if orbit:
        eye, r = _orbit_pose(
            orbit.get("center", (0, 0, 0)), float(orbit.get("distance", 800)),
            float(orbit.get("yaw", 0)), float(orbit.get("pitch", 20)))
        loc = list(eye)
        rot = list(r)
    else:
        if location is not None:
            loc = [float(location[0]), float(location[1]), float(location[2])]
        if look_at is not None:
            rot = list(_look_at_rotation(loc, look_at))
        elif rotation is not None:
            rot = [float(rotation[0]), float(rotation[1]), float(rotation[2])]
    _ues().set_level_viewport_camera_info(
        unreal.Vector(loc[0], loc[1], loc[2]),
        unreal.Rotator(rot[0], rot[1], rot[2]))
    return json.dumps({"ok": True, "action": "set_camera",
                       "location": loc, "rotation": rot})


def cnd_frame_actors(prefix=None, distance_factor=2.2, pitch=25.0):
    """把相机摆到能框住 (前缀匹配的) 所有 Actor 的位置。给 agent"看全景"用。"""
    actors = []
    for a in _eas_v().get_all_level_actors():
        if not isinstance(a, unreal.StaticMeshActor):
            continue
        if prefix and not a.get_actor_label().startswith(prefix):
            continue
        actors.append(a)
    if not actors:
        return json.dumps({"ok": False, "error": "no actors to frame"})
    mins = [1e18, 1e18, 1e18]
    maxs = [-1e18, -1e18, -1e18]
    for a in actors:
        origin, extent = a.get_actor_bounds(False)
        for i, (o, e) in enumerate(((origin.x, extent.x), (origin.y, extent.y),
                                    (origin.z, extent.z))):
            mins[i] = min(mins[i], o - e)
            maxs[i] = max(maxs[i], o + e)
    center = [(mins[i] + maxs[i]) / 2.0 for i in range(3)]
    radius = max(maxs[i] - mins[i] for i in range(3)) / 2.0
    radius = max(radius, 100.0)
    eye, rot = _orbit_pose(center, radius * float(distance_factor), 315.0,
                           float(pitch))
    _ues().set_level_viewport_camera_info(
        unreal.Vector(eye[0], eye[1], eye[2]),
        unreal.Rotator(rot[0], rot[1], rot[2]))
    return json.dumps({"ok": True, "action": "frame_actors",
                       "count": len(actors), "center": center,
                       "camera": list(eye)})


def cnd_screenshot(res_x=1280, res_y=720, view="camera"):
    """视口截图。发射即返回 {pending: True, path}; 文件生成由调用方轮询。
    view="topdown" 时先把相机抬到场景正上方俯拍 (与 mock 俯视图对齐)。"""
    if view == "topdown":
        try:
            actors = _eas_v().get_all_level_actors()
            xs = [a.get_actor_location().x for a in actors] or [0.0]
            ys = [a.get_actor_location().y for a in actors] or [0.0]
            cx = (min(xs) + max(xs)) / 2.0
            cy = (min(ys) + max(ys)) / 2.0
            span = max(max(xs) - min(xs), max(ys) - min(ys), 1000.0)
            _ues().set_level_viewport_camera_info(
                unreal.Vector(cx, cy, span * 1.4),
                unreal.Rotator(-90.0, 0.0, 0.0))
        except Exception:
            pass
    _SHOT_COUNTER["n"] += 1
    proj = unreal.SystemLibrary.get_project_saved_directory()
    shot_dir = os.path.join(proj, "Cindra", "shots")
    try:
        os.makedirs(shot_dir, exist_ok=True)
    except Exception:
        pass
    fname = "shot_%d_%03d.png" % (int(time.time()), _SHOT_COUNTER["n"])
    path = os.path.join(shot_dir, fname)
    try:
        unreal.AutomationLibrary.take_high_res_screenshot(
            int(res_x), int(res_y), path)
        method = "automation"
    except Exception:
        # fallback: 控制台命令 HighResShot, 文件落到 Saved/Screenshots
        unreal.SystemLibrary.execute_console_command(
            None, "HighResShot %dx%d" % (int(res_x), int(res_y)))
        path = os.path.join(proj, "Screenshots")
        method = "console"
    return json.dumps({"ok": True, "action": "screenshot", "pending": True,
                       "path": path, "method": method})
'''
