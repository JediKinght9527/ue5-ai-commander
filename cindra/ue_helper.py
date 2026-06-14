"""ue_helper —— 在 UE5 编辑器里执行的 cnd_*() 助手函数。

这是"手"。真 UE 里通过 Python Remote Execution 运行这段代码,用真正的 `unreal`
API 在场景里 spawn / 删除 / 移动 Actor。Mac mock 实现同名函数 (见 mock_ue.py),
所以 agent 生成的调用两边通用。

所有引擎改动都包在 transaction 里 (撤销友好),并调度到 Game Thread —— 这是
MCP_BRIDGE.md 里点明的两个硬卡点。

返回值统一是 JSON 字符串,方便远程执行把结果回传给 agent 形成验证闭环。
"""

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


def _unique_label(base):
    labels = set()
    for a in _eas().get_all_level_actors():
        labels.add(a.get_actor_label())
    if base not in labels:
        return base
    i = 2
    while True:
        candidate = "%s_%03d" % (base, i)
        if candidate not in labels:
            return candidate
        i += 1


def _select_actor(actor):
    try:
        _eas().set_selected_level_actors([actor])
    except Exception:
        pass


def cnd_spawn(actor_type="cube", name=None, location=(0, 0, 0),
                rotation=(0, 0, 0), scale=(1, 1, 1), folder=None,
                tags=None):
    """在场景里生成一个基础形状 Actor。返回它的信息。"""
    actor_type = (actor_type or "cube").lower()
    label = _unique_label(name or ("Cindra_%s" % actor_type.capitalize()))
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
        actor.set_actor_label(label)
        if folder:
            try:
                actor.set_folder_path(folder)
            except Exception:
                pass
        if tags:
            actor.tags = [unreal.Name(str(tag)) for tag in tags]
        _select_actor(actor)
    return json.dumps({
        "ok": True, "action": "spawn", "name": actor.get_actor_label(),
        "type": actor_type,
        "location": [loc.x, loc.y, loc.z],
        "folder": str(folder or ""),
        "tags": [str(tag) for tag in (tags or [])],
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
        try:
            folder = str(a.get_folder_path())
        except Exception:
            folder = ""
        out.append({"name": a.get_actor_label(),
                    "class": a.get_class().get_name(),
                    "location": [loc.x, loc.y, loc.z],
                    "folder": folder,
                    "tags": [str(tag) for tag in getattr(a, "tags", [])]})
    return json.dumps({"ok": True, "action": "list", "actors": out})


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
