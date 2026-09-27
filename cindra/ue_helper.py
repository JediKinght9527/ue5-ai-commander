"""ue_helper —— 兼容薄层。

v2 起注入源按命名空间拆到 cindra/ue_helpers/ (scene/vision/assets/...),
transport 按需懒注入。这里保留 UE_HELPER_SOURCE 指向 scene 模块,
让 check_ue.py 等旧引用不破。新代码请用 cindra.ue_helpers。
"""

from .ue_helpers import FUNC_TO_MODULE, HELPER_MODULES, module_for  # noqa: F401

# 这段源码会被原样发到 UE 的 Python 解释器里执行。引擎侧 import unreal。
UE_HELPER_SOURCE = r'''
import json
import unreal

# 基础形状 -> 引擎资产路径。够覆盖 "生成 10 个 cube" 这类需求。
_SHAPE_MESHES = {
    "cube":     "/Engine/BasicShapes/Cube.Cube",
    "sphere":   "/Engine/BasicShapes/Sphere.Sphere",
    "cylinder": "/Engine/BasicShapes/Cylinder.Cylinder",
    "cone":     "/Engine/BasicShapes/Cone.Cone",
    "plane":    "/Engine/BasicShapes/Plane.Plane",
}


def _eas():
    return unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def _find_by_label(name):
    for a in _eas().get_all_level_actors():
        if a.get_actor_label() == name:
            return a
    return None


def cnd_spawn(actor_type="cube", name=None, location=(0, 0, 0),
                rotation=(0, 0, 0), scale=(1, 1, 1)):
    """在场景里生成一个基础形状 Actor。返回它的信息。"""
    actor_type = (actor_type or "cube").lower()
    mesh_path = _SHAPE_MESHES.get(actor_type, _SHAPE_MESHES["cube"])
    loc = unreal.Vector(float(location[0]), float(location[1]), float(location[2]))
    rot = unreal.Rotator(float(rotation[0]), float(rotation[1]), float(rotation[2]))

    with unreal.ScopedEditorTransaction("Cindra Spawn"):
        actor = _eas().spawn_actor_from_class(
            unreal.StaticMeshActor, loc, rot)
        mesh = unreal.load_asset(mesh_path)
        actor.static_mesh_component.set_static_mesh(mesh)
        actor.set_actor_scale3d(
            unreal.Vector(float(scale[0]), float(scale[1]), float(scale[2])))
        if name:
            actor.set_actor_label(name)
    return json.dumps({
        "ok": True, "action": "spawn", "name": actor.get_actor_label(),
        "type": actor_type,
        "location": [loc.x, loc.y, loc.z],
    })


def cnd_delete(name):
    """按名字删除一个 Actor。"""
    actor = _find_by_label(name)
    if not actor:
        return json.dumps({"ok": False, "error": "not found: %s" % name})
    with unreal.ScopedEditorTransaction("Cindra Delete"):
        _eas().destroy_actor(actor)
    return json.dumps({"ok": True, "action": "delete", "name": name})


def cnd_move(name, location):
    """把一个 Actor 移到新坐标。"""
    actor = _find_by_label(name)
    if not actor:
        return json.dumps({"ok": False, "error": "not found: %s" % name})
    loc = unreal.Vector(float(location[0]), float(location[1]), float(location[2]))
    with unreal.ScopedEditorTransaction("Cindra Move"):
        actor.set_actor_location(loc, False, True)
    return json.dumps({"ok": True, "action": "move", "name": name,
                       "location": [loc.x, loc.y, loc.z]})


def cnd_set_transform(name, location=None, rotation=None, scale=None):
    """一次性改位置/旋转/缩放 (任一可省)。语义化批量编辑 (地震/倒塌) 必须能改
    旋转和缩放, cnd_move 只能改位置。和 mock_ue 同名同义。"""
    actor = _find_by_label(name)
    if not actor:
        return json.dumps({"ok": False, "error": "not found: %s" % name})
    with unreal.ScopedEditorTransaction("Cindra SetTransform"):
        if location is not None:
            actor.set_actor_location(
                unreal.Vector(float(location[0]), float(location[1]),
                              float(location[2])), False, True)
        if rotation is not None:
            actor.set_actor_rotation(
                unreal.Rotator(float(rotation[0]), float(rotation[1]),
                               float(rotation[2])), True)
        if scale is not None:
            actor.set_actor_scale3d(
                unreal.Vector(float(scale[0]), float(scale[1]), float(scale[2])))
    loc = actor.get_actor_location()
    rot = actor.get_actor_rotation()
    scl = actor.get_actor_scale3d()
    return json.dumps({"ok": True, "action": "set_transform", "name": name,
                       "location": [loc.x, loc.y, loc.z],
                       "rotation": [rot.pitch, rot.yaw, rot.roll],
                       "scale": [scl.x, scl.y, scl.z]})


def cnd_list():
    """列出场景里所有 Actor 的名字 + 坐标 —— 给 agent 读回状态自检。"""
    out = []
    for a in _eas().get_all_level_actors():
        loc = a.get_actor_location()
        out.append({"name": a.get_actor_label(),
                    "class": a.get_class().get_name(),
                    "location": [loc.x, loc.y, loc.z]})
    return json.dumps({"ok": True, "action": "list", "actors": out})


def cnd_snapshot():
    """全量场景快照 (含旋转/缩放) —— 验证闭环的结构化"眼睛"。
    和 cnd_list 的区别: list 是给 agent 的简表, snapshot 是给 verifier 做
    操作前后 diff 的全表。和 mock_ue 同名同义。"""
    out = []
    for a in _eas().get_all_level_actors():
        loc = a.get_actor_location()
        rot = a.get_actor_rotation()
        scl = a.get_actor_scale3d()
        out.append({"name": a.get_actor_label(),
                    "class": a.get_class().get_name(),
                    "location": [loc.x, loc.y, loc.z],
                    "rotation": [rot.pitch, rot.yaw, rot.roll],
                    "scale": [scl.x, scl.y, scl.z]})
    return json.dumps({"ok": True, "action": "snapshot", "actors": out})


def cnd_undo(steps=1):
    """撤销最近 steps 个编辑器 transaction。所有 cnd_* 改动都包了
    ScopedEditorTransaction, 所以这就是 AI 操作的回滚安全网。
    注意: 控制台命令拿不到成功与否的返回值, 调用方应随后 cnd_snapshot 验证。"""
    steps = max(1, int(steps))
    for _ in range(steps):
        unreal.SystemLibrary.execute_console_command(None, "Transaction.Undo")
    return json.dumps({"ok": True, "action": "undo", "undone": steps,
                       "note": "console 命令无返回值, 请 snapshot 验证结果"})


def cnd_screenshot(path, width=1280, height=720):
    """请求一张视口高分辨率截图 —— 视觉闭环的"眼睛"。
    这是异步的: 引擎在随后数帧末尾才把 PNG 写盘, 本函数只发起请求并立即返回。
    Mac/CLI 侧 (transport.viewport) 负责轮询文件出现 + 大小稳定。
    已知坑 (同 spawn): 视口被藏起来时截图不会出图 —— 保证视口可见。"""
    ok = unreal.AutomationLibrary.take_high_res_screenshot(
        int(width), int(height), path)
    return json.dumps({"ok": bool(ok), "action": "screenshot", "path": path,
                       "note": "async: 文件在随后数帧内写盘, 需轮询等待"})


def cnd_clear(prefix=None):
    """清场。可选只删名字以 prefix 开头的 (避免误删关卡基础物)。"""
    n = 0
    with unreal.ScopedEditorTransaction("Cindra Clear"):
        for a in list(_eas().get_all_level_actors()):
            if not isinstance(a, unreal.StaticMeshActor):
                continue
            if prefix and not a.get_actor_label().startswith(prefix):
                continue
            _eas().destroy_actor(a)
            n += 1
    return json.dumps({"ok": True, "action": "clear", "deleted": n})
'''
