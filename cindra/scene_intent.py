"""Deterministic scene intent handling for high-frequency UE panel commands.

The model is still used for open-ended edits. This module handles commands that
must be reliable from a button or a short Chinese prompt: spawn basic shapes,
read the scene, and clear Cindra-owned actors.
"""

from __future__ import annotations

import re
from typing import Any

from . import scene_tools

_CN_NUMBERS = {
    "一": 1,
    "二": 2,
    "两": 2,
    "俩": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


def try_handle_scene_prompt(transport: Any, prompt: str, *, verbose: bool = True) -> bool:
    """Handle a common scene prompt directly.

    Returns True when the prompt was handled and printed its own result. Returns
    False when the caller should fall back to the model agent.
    """
    text = (prompt or "").strip()
    normalized = text.lower().replace(" ", "")
    if not normalized:
        return False

    if _is_read_scene(normalized):
        _print_scene(transport)
        return True

    if _is_clear_cindra(normalized):
        result = scene_tools.dispatch(
            transport, "clear_scene", {"prefix": scene_tools.CINDRA_ACTOR_PREFIX}
        )
        _print_result("clear_scene", result, verbose=verbose)
        _print_scene(transport)
        return True

    if not _looks_like_spawn(normalized):
        return False

    handled_any = False
    if _mentions_cube(normalized):
        count = _count_before_shape(normalized, ("cube", "方块", "立方体", "箱子")) or 1
        args: dict[str, Any] = {
            "actor_type": "cube",
            "count": count,
            "spacing": 220,
            "columns": count if _mentions_line(normalized) else None,
            "origin": _centered_origin(count, 220, 0, 0, 100),
        }
        if count == 1:
            result = scene_tools.dispatch(
                transport,
                "spawn_actor",
                {"actor_type": "cube", "location": [0, 0, 150], "scale": [2, 2, 2]},
            )
            _print_result("spawn_actor", result, verbose=verbose)
        else:
            result = scene_tools.dispatch(transport, "spawn_grid", args)
            _print_result("spawn_grid", result, verbose=verbose)
        handled_any = True

    if _mentions_sphere(normalized):
        count = _count_before_shape(normalized, ("sphere", "球", "小球", "大球")) or 1
        if "主角" in normalized or "中间" in normalized:
            count = max(1, count if not _mentions_cube(normalized) else 1)
        if count == 1:
            scale = [3, 3, 3] if "大球" in normalized or "明显" in normalized else [1.6, 1.6, 1.6]
            result = scene_tools.dispatch(
                transport,
                "spawn_actor",
                {
                    "actor_type": "sphere",
                    "name": f"{scene_tools.CINDRA_ACTOR_PREFIX}HeroSphere"
                    if "主角" in normalized or "中间" in normalized
                    else None,
                    "location": [0, 0, 300],
                    "scale": scale,
                },
            )
            _print_result("spawn_actor", result, verbose=verbose)
        else:
            result = _spawn_centered_series(transport, "sphere", count, z=220)
            _print_result("spawn_series", result, verbose=verbose)
        handled_any = True

    if handled_any:
        _print_scene(transport)
    return handled_any


def _print_result(action: str, result: dict, *, verbose: bool) -> None:
    if not verbose:
        return
    status = "OK" if result.get("ok", True) else "ERROR"
    print(f"[direct] {action}: {status} {result}")


def _print_scene(transport: Any) -> None:
    result = transport.call("cnd_list")
    if not result.get("ok", True):
        print(f"[direct] cnd_list: ERROR {result}")
        return
    actors = result.get("actors", [])
    cindra = [a for a in actors if a.get("name", "").startswith(scene_tools.CINDRA_ACTOR_PREFIX)]
    print(f"[scene] total={len(actors)} cindra={len(cindra)}")
    for actor in cindra[-30:]:
        print(f"  - {actor.get('name')} @ {actor.get('location')}")


def _looks_like_spawn(text: str) -> bool:
    return any(word in text for word in ("生成", "创建", "放", "spawn", "加一个", "新建"))


def _is_read_scene(text: str) -> bool:
    return any(word in text for word in ("有什么", "列出来", "readscene", "list", "场景里现在"))


def _is_clear_cindra(text: str) -> bool:
    return ("清除" in text or "删除" in text or "clear" in text) and (
        "cindra_" in text or "cindra" in text or "前几次" in text
    )


def _mentions_cube(text: str) -> bool:
    return any(word in text for word in ("cube", "方块", "立方体", "箱子"))


def _mentions_sphere(text: str) -> bool:
    return any(word in text for word in ("sphere", "球", "小球", "大球"))


def _mentions_line(text: str) -> bool:
    return any(word in text for word in ("一排", "排成一排", "一行", "横排"))


def _count_before_shape(text: str, shapes: tuple[str, ...]) -> int | None:
    for shape in shapes:
        idx = text.find(shape)
        if idx < 0:
            continue
        before = text[max(0, idx - 8) : idx]
        m = re.search(r"(\d+)", before)
        if m:
            return int(m.group(1))
        for cn, value in _CN_NUMBERS.items():
            if cn in before:
                return value
        if "一个" in before or "1个" in before:
            return 1
    m = re.search(r"生成(\d+)个", text)
    if m:
        return int(m.group(1))
    return None


def _centered_origin(count: int, spacing: float, x: float, y: float, z: float) -> list[float]:
    width = max(0, count - 1) * spacing
    return [x - width / 2, y, z]


def _spawn_centered_series(transport: Any, actor_type: str, count: int, *, z: float) -> dict:
    names = []
    spacing = 220
    origin = _centered_origin(count, spacing, 0, 0, z)
    for idx in range(count):
        loc = [origin[0] + idx * spacing, origin[1], origin[2]]
        result = scene_tools.dispatch(
            transport,
            "spawn_actor",
            {
                "actor_type": actor_type,
                "name": f"{scene_tools.CINDRA_ACTOR_PREFIX}{actor_type.capitalize()}_{idx + 1:03d}",
                "location": loc,
                "scale": [1.6, 1.6, 1.6],
            },
        )
        if not result.get("ok", True):
            return {"ok": False, "error": result.get("error"), "spawned": names}
        names.append(result["name"])
    return {
        "ok": True,
        "action": "spawn_series",
        "type": actor_type,
        "count": len(names),
        "names": names,
    }
