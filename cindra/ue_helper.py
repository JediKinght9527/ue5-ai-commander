"""ue_helper —— 兼容薄层。

v2 起注入源按命名空间拆到 cindra/ue_helpers/ (scene/vision/assets/...),
transport 按需懒注入。这里保留 UE_HELPER_SOURCE 指向 scene 模块,
让 check_ue.py 等旧引用不破。新代码请用 cindra.ue_helpers。
"""
from .ue_helpers import FUNC_TO_MODULE, HELPER_MODULES, module_for  # noqa: F401

UE_HELPER_SOURCE = HELPER_MODULES["scene"]
