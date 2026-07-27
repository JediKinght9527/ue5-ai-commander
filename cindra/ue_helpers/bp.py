"""ue_helpers.bp —— 蓝图真后端的 Python 胶水 (注入源)。

真正的图操作在 C++ (CindraBlueprintBridge 插件的 UCindraBlueprintLib);
UFUNCTION 经反射自动暴露成 unreal.CindraBlueprintLib.cnd_bp_*()。
这里只做三件事: 维护"当前蓝图"路径、按 mock 规则生成节点 id、把返回
JSON 原样传回 —— 形状与 blueprint_model 的 mock bp_*() 完全一致。
"""

SOURCE = r'''
import json
import unreal

_BP_STATE = {"path": None, "counter": 0}


def _bp_lib():
    lib = getattr(unreal, "CindraBlueprintLib", None)
    if lib is None:
        raise RuntimeError(
            "CindraBlueprintLib 不存在 —— CindraEditorPanel 插件的 "
            "CindraBlueprintBridge 模块没编译/没启用。见 WINDOWS_SETUP_5.7.md")
    return lib


def bp_probe():
    """探针: 插件在不在。UEBlueprintTransport 首调用它换来诚实报错。"""
    try:
        _bp_lib()
        return json.dumps({"ok": True, "action": "probe"})
    except RuntimeError as e:
        return json.dumps({"ok": False, "error": str(e)})


def bp_create(path, parent_class="Actor"):
    res = _bp_lib().cnd_bp_create(path, parent_class)
    out = json.loads(res)
    if out.get("ok"):
        _BP_STATE["path"] = path
        _BP_STATE["counter"] = 0
    return res


def bp_open(path):
    res = _bp_lib().cnd_bp_open(path)
    if json.loads(res).get("ok"):
        _BP_STATE["path"] = path
    return res


def _need_bp():
    if not _BP_STATE["path"]:
        return json.dumps({"ok": False,
                           "error": "先 create_blueprint 或 open_blueprint"})
    return None


def bp_add_node(node_type, name=None):
    err = _need_bp()
    if err:
        return err
    _BP_STATE["counter"] += 1
    nid = name or ("%s_%d" % (node_type, _BP_STATE["counter"]))
    return _bp_lib().cnd_bp_add_node(_BP_STATE["path"], node_type, nid)


def bp_add_variable(name, var_type="float", default=None):
    err = _need_bp()
    if err:
        return err
    return _bp_lib().cnd_bp_add_variable(
        _BP_STATE["path"], name, var_type,
        "" if default is None else str(default))


def bp_connect(from_node, from_pin, to_node, to_pin):
    err = _need_bp()
    if err:
        return err
    return _bp_lib().cnd_bp_connect(_BP_STATE["path"], from_node, from_pin,
                                    to_node, to_pin)


def bp_delete_node(node_id):
    err = _need_bp()
    if err:
        return err
    return _bp_lib().cnd_bp_delete_node(_BP_STATE["path"], node_id)


def bp_list():
    err = _need_bp()
    if err:
        return err
    return _bp_lib().cnd_bp_list(_BP_STATE["path"])


def bp_clear():
    err = _need_bp()
    if err:
        return err
    return _bp_lib().cnd_bp_clear(_BP_STATE["path"])


def bp_compile():
    err = _need_bp()
    if err:
        return err
    return _bp_lib().cnd_bp_compile(_BP_STATE["path"])
'''
