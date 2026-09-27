"""cine_transport —— 运镜模式的执行通道。

MockCineTransport 同时持有 CineModel + MockScene: 序列操作打到模型,
场景操作 (cnd_list 等) 打到场景 —— chat 搭的景 (经 --session 恢复) 能被
故事板直接"拍"到。真后端直接复用 RemoteExecTransport (cnd_seq_* 注入源
在 ue_helpers/cine.py, FUNC_TO_MODULE 已注册), 场景与序列共用一条连接。
"""

from __future__ import annotations

import json
from typing import Any

from .cine_model import CineModel
from .mock_ue import MockScene


class MockCineTransport:
    def __init__(self, scene: MockScene | None = None) -> None:
        self.scene = scene or MockScene()
        self.model = CineModel(scene_actors=lambda: self.scene.actors)

    def call(self, func: str, **kwargs: Any) -> dict:
        target = self.model if func.startswith("cnd_seq_") else self.scene
        fn = getattr(target, func, None)
        if fn is None:
            return {"ok": False, "error": f"unknown func: {func}"}
        try:
            return json.loads(fn(**kwargs))
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    def describe_scene(self) -> str:
        seqs = sorted(self.model.sequences)
        return (
            f"序列: {', '.join(seqs) if seqs else '(无)'}; 场景 {len(self.scene.actors)} 个 Actor"
        )
