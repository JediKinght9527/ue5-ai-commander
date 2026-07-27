"""ue_helpers —— 注入真 UE 的 cnd_*() 源码模块注册表。

原来 ue_helper.py 是一个 173 行的单 blob; v2 能力翻了几倍, 单包注入
既容易撞 remote-exec 消息体积上限, 出错也没法定位是哪部分坏了。
拆成按需懒注入的独立命名空间: transport 第一次调到某模块的函数时才注入
该模块源码 (见 RemoteExecTransport._injected)。

每个模块源码必须幂等 (纯 def, import 时无副作用), 编辑器重启后重注入安全。
"""
from __future__ import annotations

from .assets import SOURCE as _ASSETS_SOURCE
from .bp import SOURCE as _BP_SOURCE
from .cine import SOURCE as _CINE_SOURCE
from .scene import SOURCE as _SCENE_SOURCE
from .vision import SOURCE as _VISION_SOURCE

# module id -> 注入源码
HELPER_MODULES: dict[str, str] = {
    "scene": _SCENE_SOURCE,
    "vision": _VISION_SOURCE,
    "assets": _ASSETS_SOURCE,
    "cine": _CINE_SOURCE,
    "bp": _BP_SOURCE,
}

# cnd 函数 -> 所属模块 (缺省落到 scene)
FUNC_TO_MODULE: dict[str, str] = {
    # scene
    "cnd_spawn": "scene",
    "cnd_delete": "scene",
    "cnd_move": "scene",
    "cnd_set_transform": "scene",
    "cnd_list": "scene",
    "cnd_clear": "scene",
    # vision
    "cnd_set_camera": "vision",
    "cnd_frame_actors": "vision",
    "cnd_screenshot": "vision",
    # assets / lighting / env / pcg
    "cnd_list_assets": "assets",
    "cnd_spawn_asset": "assets",
    "cnd_set_material": "assets",
    "cnd_spawn_light": "assets",
    "cnd_spawn_env": "assets",
    "cnd_pcg_spawn_volume": "assets",
    "cnd_pcg_generate": "assets",
    "cnd_env_info": "assets",
    # cine (Sequencer + MRQ)
    "cnd_seq_create": "cine",
    "cnd_seq_add_camera": "cine",
    "cnd_seq_add_keys": "cine",
    "cnd_seq_add_cut": "cine",
    "cnd_seq_list": "cine",
    "cnd_seq_render": "cine",
}


def module_for(func: str) -> str:
    return FUNC_TO_MODULE.get(func, "scene")
