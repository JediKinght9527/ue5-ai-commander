"""session —— 会话持久化 (跨进程续聊)。

v1 每次 python -m cindra.cli 都是全新 agent, 上一次摆的场景/聊的上下文全丢。
v2: --session NAME 把 {mode, messages, scene_manifest} 存到
~/.cindra/sessions/NAME.json, 下次同名启动自动恢复。

图片处理: 消息里的 image block 只存路径 stub (体积小, 且历史截图对下一次
会话价值低); 恢复时保持文字 stub, agent 需要看就重新 look_at_scene。
mock 场景: 全量 actor dict 存盘, 恢复时重建 MockScene —— mock 也能"接着摆"。

自检: python3 -m cindra.session
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SESSIONS_DIR = Path.home() / ".cindra" / "sessions"


def _stub_images(messages: list[dict]) -> list[dict]:
    """深拷贝消息, image block -> 文字 stub (路径保留在文字里)。"""
    out = json.loads(json.dumps(messages, ensure_ascii=False))
    for msg in out:
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for tr in content:
            if not (isinstance(tr, dict) and tr.get("type") == "tool_result"):
                continue
            inner = tr.get("content")
            if not isinstance(inner, list):
                continue
            for i, blk in enumerate(inner):
                if isinstance(blk, dict) and blk.get("type") == "image":
                    inner[i] = {"type": "text",
                                "text": "(历史截图, 已随会话存档省略)"}
    return out


def session_path(name: str) -> Path:
    return SESSIONS_DIR / f"{name}.json"


def save_session(name: str, mode: str, agent: Any, transport: Any) -> str:
    """存会话。scene_manifest: mock 存全量 actors (可重建), 真后端存 cnd_list
    读回的清单 (场景本体在 UE 关卡里, 存清单仅供参考)。"""
    manifest: dict = {}
    scene = getattr(transport, "scene", None)
    if scene is not None:
        manifest = {"kind": "mock", "actors": scene.actors,
                    "camera": scene.camera}
    else:
        try:
            manifest = {"kind": "real", "list": transport.call("cnd_list")}
        except Exception:
            manifest = {"kind": "real", "list": None}
    payload = {
        "version": 1,
        "mode": mode,
        "messages": _stub_images(agent.messages),
        "scene_manifest": manifest,
    }
    path = session_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                    encoding="utf-8")
    return str(path)


def load_session(name: str, agent: Any, transport: Any) -> bool:
    """恢复会话到已构建的 agent/transport。没有存档返回 False。"""
    path = session_path(name)
    if not path.is_file():
        return False
    payload = json.loads(path.read_text(encoding="utf-8"))
    agent.messages = payload.get("messages", [])
    manifest = payload.get("scene_manifest") or {}
    scene = getattr(transport, "scene", None)
    if scene is not None and manifest.get("kind") == "mock":
        scene.actors = manifest.get("actors", {})
        if manifest.get("camera"):
            scene.camera = manifest["camera"]
    return True


def list_sessions() -> list[str]:
    if not SESSIONS_DIR.is_dir():
        return []
    return sorted(p.stem for p in SESSIONS_DIR.glob("*.json"))


def _selfcheck() -> None:
    import tempfile
    from unittest import mock as um

    from .mock_ue import MockScene

    class _Agent:
        def __init__(self):
            self.messages = []

    class _Transport:
        def __init__(self):
            self.scene = MockScene()

    ok = 0
    # 嵌套 with 有意保留: 内层还包着 try/finally 做 SESSIONS_DIR 状态恢复,
    # 合成一行反而看不出恢复边界
    with tempfile.TemporaryDirectory() as td:  # noqa: SIM117
        with um.patch.object(Path, "home", return_value=Path(td)):  # noqa: SIM117
            # 猴补 SESSIONS_DIR 依赖的 home —— 模块级常量已求值, 直接补常量
            import cindra.session as sess
            old = sess.SESSIONS_DIR
            sess.SESSIONS_DIR = Path(td) / "sessions"
            try:
                t = _Transport()
                t.scene.cnd_spawn(actor_type="cube", location=[100, 200, 0])
                t.scene.cnd_spawn(actor_type="sphere", location=[0, 0, 50])
                a = _Agent()
                a.messages = [
                    {"role": "user", "content": "放两个东西"},
                    {"role": "user", "content": [
                        {"type": "tool_result", "tool_use_id": "x",
                         "content": [
                             {"type": "text", "text": "{}"},
                             {"type": "image", "source": {
                                 "type": "base64", "media_type": "image/png",
                                 "data": "AAAA"}}]}]},
                ]
                p = sess.save_session("t1", "chat", a, t)
                assert Path(p).is_file()
                ok += 1
                print("[1/3] save_session 落盘 ✓")

                t2, a2 = _Transport(), _Agent()
                assert sess.load_session("t1", a2, t2)
                assert t2.scene.actors == t.scene.actors, "场景没恢复"
                assert len(a2.messages) == 2
                ok += 1
                print("[2/3] load_session 场景+消息恢复 ✓")

                inner = a2.messages[1]["content"][0]["content"]
                assert all(b.get("type") != "image" for b in inner), \
                    "图片应存为 stub"
                assert not sess.load_session("nope", a2, t2)
                assert sess.list_sessions() == ["t1"]
                ok += 1
                print("[3/3] 图片 stub + 缺档/列表 ✓")
            finally:
                sess.SESSIONS_DIR = old
    print(f"session 自检 {ok}/3 全部通过")


if __name__ == "__main__":
    _selfcheck()
