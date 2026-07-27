"""ue_helpers.assets —— 真资产/灯光/环境/PCG 原语。

真 UE 注入源。硬规则: 大数据 (资产 manifest) 写盘回传路径, 不走 remote-exec 输出。
"""

SOURCE = r'''
import json
import os
import unreal

_LIGHT_CLASSES = {
    "point":       "PointLight",
    "spot":        "SpotLight",
    "rect":        "RectLight",
    "directional": "DirectionalLight",
}

_ENV_CLASSES = {
    "sky_atmosphere":  "SkyAtmosphere",
    "exp_height_fog":  "ExponentialHeightFog",
    "post_process":    "PostProcessVolume",
    "sky_light":       "SkyLight",
    "sun":             "DirectionalLight",
}


def _eas_a():
    return unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def _labels():
    return {a.get_actor_label() for a in _eas_a().get_all_level_actors()}


def _uniq(base):
    labels = _labels()
    if base not in labels:
        return base
    i = 2
    while ("%s_%03d" % (base, i)) in labels:
        i += 1
    return "%s_%03d" % (base, i)


def _find(name):
    for a in _eas_a().get_all_level_actors():
        if a.get_actor_label() == name:
            return a
    return None


def cnd_list_assets(roots=None, classes=None, manifest_path=None):
    """枚举资产写 manifest JSON 到盘上, 只回传 {count, path}。"""
    roots = roots or ["/Game", "/Engine/BasicShapes"]
    reg = unreal.AssetRegistryHelpers.get_asset_registry()
    wanted = set(classes or [])
    entries = []
    for root in roots:
        for ad in reg.get_assets_by_path(unreal.Name(root), recursive=True):
            cls = str(ad.asset_class_path.asset_name)
            if wanted and cls not in wanted:
                continue
            path = str(ad.package_name)
            entries.append({
                "path": "%s.%s" % (path, str(ad.asset_name)),
                "name": str(ad.asset_name),
                "class": cls,
                "tags": [],
            })
    if manifest_path is None:
        proj = unreal.SystemLibrary.get_project_saved_directory()
        manifest_path = os.path.join(proj, "Cindra", "asset_manifest.json")
    os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump({"assets": entries}, f, ensure_ascii=False)
    return json.dumps({"ok": True, "action": "list_assets",
                       "count": len(entries), "path": manifest_path})


def cnd_spawn_asset(asset_path, name=None, location=(0, 0, 0),
                    rotation=(0, 0, 0), scale=(1, 1, 1), folder=None):
    """按资产路径生成 Actor: StaticMesh -> StaticMeshActor, Blueprint 等
    可放置资产 -> spawn_actor_from_object。返回真实包围盒尺寸。"""
    asset = unreal.load_asset(asset_path)
    if asset is None:
        return json.dumps({"ok": False,
                           "error": "asset not found: %s" % asset_path})
    loc = unreal.Vector(float(location[0]), float(location[1]),
                        float(location[2]))
    rot = unreal.Rotator(float(rotation[0]), float(rotation[1]),
                         float(rotation[2]))
    base = name or ("Cindra_%s" % asset.get_name())
    label = _uniq(base)
    with unreal.ScopedEditorTransaction("Cindra SpawnAsset"):
        if isinstance(asset, unreal.StaticMesh):
            actor = _eas_a().spawn_actor_from_class(
                unreal.StaticMeshActor, loc, rot)
            actor.static_mesh_component.set_static_mesh(asset)
        else:
            actor = _eas_a().spawn_actor_from_object(asset, loc, rot)
            if actor is None:
                return json.dumps({"ok": False,
                                   "error": "not placeable: %s" % asset_path})
        actor.set_actor_scale3d(
            unreal.Vector(float(scale[0]), float(scale[1]), float(scale[2])))
        actor.set_actor_label(label)
        if folder:
            try:
                actor.set_folder_path(folder)
            except Exception:
                pass
    origin, extent = actor.get_actor_bounds(False)
    return json.dumps({"ok": True, "action": "spawn_asset", "name": label,
                       "asset": asset_path,
                       "location": [loc.x, loc.y, loc.z],
                       "bounds_extent": [extent.x, extent.y, extent.z]})


def cnd_set_material(name, material_path, slot=0):
    """给 Actor 的 StaticMeshComponent 换材质。"""
    actor = _find(name)
    if not actor:
        return json.dumps({"ok": False, "error": "not found: %s" % name})
    mat = unreal.load_asset(material_path)
    if mat is None:
        return json.dumps({"ok": False,
                           "error": "material not found: %s" % material_path})
    comp = getattr(actor, "static_mesh_component", None)
    if comp is None:
        return json.dumps({"ok": False,
                           "error": "no static mesh component: %s" % name})
    with unreal.ScopedEditorTransaction("Cindra SetMaterial"):
        comp.set_material(int(slot), mat)
    return json.dumps({"ok": True, "action": "set_material", "name": name,
                       "material": material_path, "slot": int(slot)})


def cnd_spawn_light(light_type="point", name=None, location=(0, 0, 300),
                    rotation=(0, 0, 0), intensity=5000.0, color=None,
                    temperature=None, attenuation_radius=1000.0,
                    cone_angle=44.0):
    """生成灯光 Actor。color=[r,g,b] 0-1; temperature 开尔文色温。"""
    cls_name = _LIGHT_CLASSES.get((light_type or "point").lower())
    if cls_name is None:
        return json.dumps({"ok": False,
                           "error": "unknown light type: %s" % light_type})
    cls = getattr(unreal, cls_name)
    loc = unreal.Vector(float(location[0]), float(location[1]),
                        float(location[2]))
    rot = unreal.Rotator(float(rotation[0]), float(rotation[1]),
                         float(rotation[2]))
    label = _uniq(name or ("Cindra_%s" % cls_name))
    with unreal.ScopedEditorTransaction("Cindra SpawnLight"):
        actor = _eas_a().spawn_actor_from_class(cls, loc, rot)
        actor.set_actor_label(label)
        comp = actor.light_component
        comp.set_intensity(float(intensity))
        if color is not None:
            comp.set_light_color(unreal.LinearColor(
                float(color[0]), float(color[1]), float(color[2]), 1.0))
        if temperature is not None:
            comp.set_editor_property("use_temperature", True)
            comp.set_editor_property("temperature", float(temperature))
        if cls_name in ("PointLight", "SpotLight"):
            try:
                comp.set_attenuation_radius(float(attenuation_radius))
            except Exception:
                pass
        if cls_name == "SpotLight":
            try:
                comp.set_outer_cone_angle(float(cone_angle))
            except Exception:
                pass
    return json.dumps({"ok": True, "action": "spawn_light", "name": label,
                       "type": light_type,
                       "location": [loc.x, loc.y, loc.z],
                       "intensity": float(intensity)})


def cnd_spawn_env(kind, params=None):
    """环境单例: sky_atmosphere / exp_height_fog / post_process / sky_light / sun。
    已存在同类 Cindra 环境 Actor 则先删再建 (params 全量生效)。"""
    params = params or {}
    cls_name = _ENV_CLASSES.get(kind)
    if cls_name is None:
        return json.dumps({"ok": False, "error": "unknown env kind: %s" % kind})
    cls = getattr(unreal, cls_name)
    label = "Cindra_Env_%s" % kind
    with unreal.ScopedEditorTransaction("Cindra SpawnEnv"):
        old = _find(label)
        if old:
            _eas_a().destroy_actor(old)
        loc = unreal.Vector(*[float(v) for v in params.get(
            "location", (0, 0, 0))])
        rot_v = params.get("rotation", (0, 0, 0))
        if kind == "sun":
            rot_v = params.get("rotation", (-35, 30, 0))
        rot = unreal.Rotator(*[float(v) for v in rot_v])
        actor = _eas_a().spawn_actor_from_class(cls, loc, rot)
        actor.set_actor_label(label)
        if kind == "exp_height_fog":
            comp = actor.component
            if "density" in params:
                comp.set_editor_property("fog_density",
                                         float(params["density"]))
            if "height_falloff" in params:
                comp.set_editor_property("fog_height_falloff",
                                         float(params["height_falloff"]))
        elif kind == "post_process":
            actor.set_editor_property("unbound", True)
            settings = actor.settings
            for key in ("bloom_intensity", "auto_exposure_bias",
                        "vignette_intensity", "film_grain_intensity"):
                if key in params:
                    settings.set_editor_property(
                        "override_" + key, True)
                    settings.set_editor_property(key, float(params[key]))
        elif kind == "sun":
            comp = actor.light_component
            if "intensity" in params:
                comp.set_intensity(float(params["intensity"]))
            if "temperature" in params:
                comp.set_editor_property("use_temperature", True)
                comp.set_editor_property("temperature",
                                         float(params["temperature"]))
    return json.dumps({"ok": True, "action": "spawn_env", "kind": kind,
                       "name": label})


def cnd_pcg_spawn_volume(graph_path, name=None, origin=(0, 0, 0),
                         size=(2000, 2000, 500)):
    """生成 PCGVolume 并挂上已有 PCG Graph 资产。"""
    graph = unreal.load_asset(graph_path)
    if graph is None:
        return json.dumps({"ok": False,
                           "error": "pcg graph not found: %s" % graph_path})
    loc = unreal.Vector(float(origin[0]), float(origin[1]), float(origin[2]))
    label = _uniq(name or "Cindra_PCGVolume")
    with unreal.ScopedEditorTransaction("Cindra PCGVolume"):
        actor = _eas_a().spawn_actor_from_class(
            unreal.PCGVolume, loc, unreal.Rotator(0, 0, 0))
        actor.set_actor_label(label)
        actor.set_actor_scale3d(unreal.Vector(
            float(size[0]) / 200.0, float(size[1]) / 200.0,
            float(size[2]) / 200.0))
        comp = actor.get_component_by_class(unreal.PCGComponent)
        # 5.7 setter 名有漂移风险: 优先 graph_instance, 回退 set_graph/graph
        try:
            comp.set_editor_property("graph_instance", graph)
        except Exception:
            try:
                comp.set_graph(graph)
            except Exception:
                comp.set_editor_property("graph", graph)
    return json.dumps({"ok": True, "action": "pcg_spawn_volume",
                       "name": label, "graph": graph_path})


def cnd_pcg_generate(name):
    """触发 PCG 生成 (异步, pending 协议; agent 之后用 cnd_list/截图验证)。"""
    actor = _find(name)
    if not actor:
        return json.dumps({"ok": False, "error": "not found: %s" % name})
    comp = actor.get_component_by_class(unreal.PCGComponent)
    if comp is None:
        return json.dumps({"ok": False, "error": "no PCGComponent: %s" % name})
    comp.generate(True)
    return json.dumps({"ok": True, "action": "pcg_generate", "name": name,
                       "pending": True})


def cnd_env_info():
    """环境诊断: UE 版本 / MegaLights / PCG 插件。"""
    ver = unreal.SystemLibrary.get_engine_version()
    megalights = None
    try:
        cvar = unreal.SystemLibrary.execute_console_command
        megalights = "unknown (check r.MegaLights)"
    except Exception:
        pass
    has_pcg = hasattr(unreal, "PCGVolume")
    return json.dumps({"ok": True, "action": "env_info",
                       "engine_version": str(ver),
                       "pcg_available": bool(has_pcg),
                       "megalights": megalights})
'''
