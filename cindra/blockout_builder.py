"""Deterministic action-game blockout generation for Unreal Engine.

Cindra's commercial wedge is not a generic "AI can do anything" chat box.
It is a production helper for UE designers: generate editable combat spaces
with stable names, folders, tags, and an audit report that can be reviewed
without spending model credits.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import scene_tools

BLOCKOUT_PREFIX = "Cindra_Blockout_"
BLOCKOUT_FOLDER = "Cindra/Blockouts"


@dataclass(frozen=True)
class Piece:
    name: str
    actor_type: str
    location: list[float]
    scale: list[float]
    tags: tuple[str, ...]
    rotation: list[float] | None = None


@dataclass(frozen=True)
class Layout:
    kind: str
    intent: str
    width: float
    depth: float
    pieces: tuple[Piece, ...]
    notes: tuple[str, ...]


def try_handle_blockout_prompt(
    transport: Any, prompt: str, *, verbose: bool = True
) -> bool:
    text = prompt or ""
    normalized = _normalize(text)

    if _has_any(normalized, _clear_keywords()):
        result = transport.call("cnd_clear", prefix=BLOCKOUT_PREFIX)
        _print_result("clear_blockout", result, verbose=verbose)
        return True

    if _has_any(normalized, _inspect_keywords()):
        _print_summary(transport)
        return True

    if not _looks_like_blockout(normalized):
        return False

    layout = _select_layout(normalized)
    result = build_layout(transport, layout)
    _print_result("build_blockout", result, verbose=verbose)
    _print_report(layout, result)
    _print_summary(transport)
    return True


def build_layout(transport: Any, layout: Layout) -> dict:
    spawned: list[str] = []
    errors: list[dict] = []
    for piece in layout.pieces:
        result = _spawn_piece(transport, layout.kind, piece)
        if result.get("ok", True):
            spawned.append(result.get("name", piece.name))
        else:
            errors.append({"piece": piece.name, "error": result.get("error")})

    report = _quality_report(layout, spawned, errors)
    return {
        "ok": not errors,
        "action": "build_blockout",
        "kind": layout.kind,
        "intent": layout.intent,
        "count": len(spawned),
        "names": spawned,
        "errors": errors,
        "report": report,
    }


def build_arena(transport: Any) -> dict:
    return build_layout(transport, _arena_layout())


def build_cover_arena(transport: Any) -> dict:
    return build_layout(transport, _cover_arena_layout())


def build_corridor(transport: Any) -> dict:
    return build_layout(transport, _corridor_layout())


def build_room(transport: Any) -> dict:
    return build_layout(transport, _room_layout())


def build_boss_arena(transport: Any) -> dict:
    return build_layout(transport, _boss_arena_layout())


def build_gauntlet(transport: Any) -> dict:
    return build_layout(transport, _gauntlet_layout())


def _select_layout(text: str) -> Layout:
    if _has_any(text, ("gauntlet", "combatlane", "encounterchain", "\u8fde\u6218", "\u6218\u6597\u8d70\u5eca", "\u5173\u5361\u8282\u594f")):
        return _gauntlet_layout()
    if _has_any(text, ("corridor", "hallway", "lane", "zoulang", "\u8d70\u5eca", "\u901a\u9053")):
        return _corridor_layout()
    if _has_any(text, ("boss", "duel", "wukong", "blackmyth", "heishenhua", "yaoguai", "\u9ed1\u795e\u8bdd", "\u609f\u7a7a", "\u5996\u602a", "\u8001\u677f", "\u9996\u9886", "\u7cbe\u82f1\u602a")):
        return _boss_arena_layout()
    if _has_any(text, ("room", "chamber", "interior", "fangjian", "\u623f\u95f4", "\u5ba4\u5185")):
        return _room_layout()
    if _has_any(text, ("coverarena", "shooter", "cover", "sheji", "\u5c04\u51fb", "\u63a9\u4f53")):
        return _cover_arena_layout()
    return _arena_layout()


def _arena_layout() -> Layout:
    pieces = _room_shell("Arena", 2200, 1600)
    pieces += _boxes(
        "Arena_Cover",
        [[-650, -380, 90], [0, -380, 90], [650, -380, 90],
         [-650, 380, 90], [0, 380, 90], [650, 380, 90]],
        [1.7, 0.45, 0.9],
        ("cover", "combat"),
    )
    pieces += (
        _marker("Arena_PlayerStart", [-850, 0, 130], ("player_start", "combat")),
        _marker("Arena_Objective", [850, 0, 130], ("objective", "combat")),
    )
    return Layout(
        "Arena",
        "Symmetric test arena for fast movement and objective iteration.",
        2200,
        1600,
        tuple(pieces),
        ("Readable lanes", "Six editable cover pieces", "Player start faces objective"),
    )


def _cover_arena_layout() -> Layout:
    pieces = _room_shell("CoverArena", 2400, 1800)
    pieces += _boxes(
        "CoverArena_LowCover",
        [[-760, -520, 80], [-260, -520, 80], [260, -520, 80], [760, -520, 80],
         [-760, 0, 80], [760, 0, 80],
         [-760, 520, 80], [-260, 520, 80], [260, 520, 80], [760, 520, 80]],
        [1.45, 0.35, 0.75],
        ("cover", "combat", "sightline"),
    )
    pieces += _boxes(
        "CoverArena_Pillar",
        [[-420, 0, 180], [420, 0, 180]],
        [0.5, 0.5, 1.8],
        ("pillar", "sightline", "combat"),
    )
    pieces += (
        _marker("CoverArena_PlayerStart_A", [-980, 0, 130], ("player_start", "spawn")),
        _marker("CoverArena_PlayerStart_B", [980, 0, 130], ("player_start", "spawn")),
        _marker("CoverArena_CenterObjective", [0, 0, 130], ("objective", "combat")),
    )
    return Layout(
        "CoverArena",
        "Shooter-style cover arena for line-of-sight and flank testing.",
        2400,
        1800,
        tuple(pieces),
        ("Two spawn sides", "Ten low cover pieces", "Center objective anchors the fight"),
    )


def _corridor_layout() -> Layout:
    pieces = _room_shell("Corridor", 900, 2600)
    pieces += _boxes(
        "Corridor_Beat",
        [[-260, -760, 80], [260, -260, 80], [-260, 260, 80], [260, 760, 80]],
        [1.0, 0.35, 0.75],
        ("beat", "cover", "pacing"),
    )
    pieces += (
        _marker("Corridor_Entry", [0, -1100, 130], ("entry", "player_start", "pacing")),
        _marker("Corridor_Exit", [0, 1100, 130], ("exit", "pacing")),
    )
    return Layout(
        "Corridor",
        "Linear encounter lane with alternating combat beats.",
        900,
        2600,
        tuple(pieces),
        ("Entry and exit are explicit", "Alternating blockers create rhythm"),
    )


def _room_layout() -> Layout:
    pieces = _room_shell("Room", 1400, 1100)
    pieces += _boxes(
        "Room_Prop",
        [[-360, -260, 70], [360, -260, 70], [0, 240, 70]],
        [0.8, 0.8, 0.7],
        ("prop", "composition"),
    )
    pieces += (
        _marker("Room_PlayerStart", [0, -360, 130], ("player_start", "composition")),
        _marker("Room_Focus", [0, 0, 130], ("focus", "objective", "composition")),
    )
    return Layout(
        "Room",
        "Small interior greybox for composition and interactable placement.",
        1400,
        1100,
        tuple(pieces),
        ("Player start and focus point", "Three editable prop volumes"),
    )


def _boss_arena_layout() -> Layout:
    pieces = _room_shell("MythicBossArena", 3000, 2400, wall_height=360)
    pieces += _boxes(
        "MythicBossArena_OuterPillar",
        [[-1100, -780, 210], [0, -880, 210], [1100, -780, 210],
         [-1100, 780, 210], [0, 880, 210], [1100, 780, 210]],
        [0.55, 0.55, 2.1],
        ("pillar", "readability", "mythic"),
    )
    pieces += _boxes(
        "MythicBossArena_DodgeLane",
        [[-620, -300, 35], [620, -300, 35], [-620, 300, 35], [620, 300, 35]],
        [2.2, 0.18, 0.12],
        ("dodge_lane", "combat", "readability"),
    )
    pieces += _boxes(
        "MythicBossArena_PhaseGate",
        [[0, -1030, 170], [0, 1030, 170]],
        [2.8, 0.28, 1.7],
        ("phase_gate", "boss", "mythic"),
    )
    pieces += (
        _marker("MythicBossArena_PlayerStart", [0, -650, 130], ("player_start", "boss")),
        _marker("MythicBossArena_BossStart", [0, 450, 180], ("boss_start", "boss")),
        _marker("MythicBossArena_HealShrine", [-900, 0, 120], ("shrine", "resource")),
        _marker("MythicBossArena_ObjectiveBell", [900, 0, 120], ("objective", "mythic")),
    )
    return Layout(
        "MythicBossArena",
        "Black-Myth-style boss arena: readable duel space, phase gates, shrine, and dodge lanes.",
        3000,
        2400,
        tuple(pieces),
        (
            "Boss and player starts are separated for opening readability",
            "Pillars frame the arena without blocking the center duel",
            "Phase gates and shrine are named for later Blueprint/gameplay binding",
        ),
    )


def _gauntlet_layout() -> Layout:
    pieces = _room_shell("MythicGauntlet", 1200, 3400, wall_height=320)
    pieces += _boxes(
        "MythicGauntlet_BeatGate",
        [[0, -1000, 150], [0, 0, 150], [0, 1000, 150]],
        [2.2, 0.22, 1.5],
        ("gate", "encounter", "pacing"),
    )
    pieces += _boxes(
        "MythicGauntlet_EnemyPod",
        [[-360, -760, 90], [360, -760, 90],
         [-360, 260, 90], [360, 260, 90],
         [-360, 1260, 90], [360, 1260, 90]],
        [0.7, 0.7, 0.9],
        ("enemy_pod", "encounter", "combat"),
    )
    pieces += (
        _marker("MythicGauntlet_Entry", [0, -1450, 130], ("entry", "player_start", "pacing")),
        _marker("MythicGauntlet_FinalReward", [0, 1500, 130], ("reward", "objective")),
    )
    return Layout(
        "MythicGauntlet",
        "Action-game encounter chain with three readable combat beats.",
        1200,
        3400,
        tuple(pieces),
        ("Three gates define pacing", "Enemy pods are separated per beat", "Reward marker ends the route"),
    )


def _room_shell(
    kind: str, width: float, depth: float, *, wall_height: float = 300,
    wall_thickness: float = 40
) -> tuple[Piece, ...]:
    half_w = width / 2
    half_d = depth / 2
    return (
        _box(f"{kind}_Floor", [0, 0, -10], [width / 100, depth / 100, 0.12], ("floor", "walkable")),
        _box(f"{kind}_Wall_North", [0, half_d, wall_height / 2], [width / 100, wall_thickness / 100, wall_height / 100], ("wall", "boundary")),
        _box(f"{kind}_Wall_South", [0, -half_d, wall_height / 2], [width / 100, wall_thickness / 100, wall_height / 100], ("wall", "boundary")),
        _box(f"{kind}_Wall_East", [half_w, 0, wall_height / 2], [wall_thickness / 100, depth / 100, wall_height / 100], ("wall", "boundary")),
        _box(f"{kind}_Wall_West", [-half_w, 0, wall_height / 2], [wall_thickness / 100, depth / 100, wall_height / 100], ("wall", "boundary")),
    )


def _boxes(
    prefix: str, positions: list[list[float]], scale: list[float],
    tags: tuple[str, ...]
) -> tuple[Piece, ...]:
    return tuple(
        _box(f"{prefix}_{idx:02d}", pos, scale, tags)
        for idx, pos in enumerate(positions, start=1)
    )


def _box(name: str, location: list[float], scale: list[float], tags: tuple[str, ...]) -> Piece:
    return Piece(
        name=f"{BLOCKOUT_PREFIX}{name}",
        actor_type="cube",
        location=location,
        scale=scale,
        tags=("cindra", "blockout", *tags),
    )


def _marker(label: str, location: list[float], tags: tuple[str, ...]) -> Piece:
    return Piece(
        name=f"{BLOCKOUT_PREFIX}{label}",
        actor_type="sphere",
        location=location,
        scale=[0.9, 0.9, 0.9],
        tags=("cindra", "blockout", "marker", *tags),
    )


def _spawn_piece(transport: Any, kind: str, piece: Piece) -> dict:
    args = {
        "actor_type": piece.actor_type,
        "name": piece.name,
        "location": piece.location,
        "scale": piece.scale,
        "folder": f"{BLOCKOUT_FOLDER}/{kind}",
        "tags": list(piece.tags),
    }
    if piece.rotation is not None:
        args["rotation"] = piece.rotation
    return scene_tools.dispatch(transport, "spawn_actor", args)


def _quality_report(layout: Layout, spawned: list[str], errors: list[dict]) -> dict:
    tags = [tag for piece in layout.pieces for tag in piece.tags]
    required = ("floor", "wall", "player_start")
    missing = [tag for tag in required if tag not in tags]
    score = 100
    score -= len(errors) * 20
    score -= len(missing) * 15
    if not any(tag in tags for tag in ("objective", "boss_start", "reward", "exit")):
        score -= 10
    if layout.kind != "Room" and not any(tag in tags for tag in ("cover", "dodge_lane", "enemy_pod", "pillar")):
        score -= 10
    score = max(0, min(100, score))
    return {
        "score": score,
        "missing": missing,
        "piece_count": len(layout.pieces),
        "spawned_count": len(spawned),
        "tags": sorted(set(tags)),
        "notes": list(layout.notes),
    }


def _looks_like_blockout(text: str) -> bool:
    return _has_any(text, (
        "blockout", "greybox", "graybox", "whitebox", "levelprototype",
        "combatspace", "arena", "boss", "gauntlet", "corridor", "room",
        "heishenhua", "blackmyth", "wukong",
        "\u767d\u76d2", "\u7070\u76d2", "\u5173\u5361", "\u7ade\u6280\u573a",
        "\u6218\u6597", "\u573a\u5730", "\u573a\u666f", "\u8d70\u5eca",
        "\u623f\u95f4", "\u63a9\u4f53", "\u9ed1\u795e\u8bdd",
        "\u609f\u7a7a", "\u5996\u602a", "\u9996\u9886",
    ))


def _clear_keywords() -> tuple[str, ...]:
    return (
        "clearblockout", "clearwhitebox", "cleargreybox",
        "\u6e05\u9664\u767d\u76d2", "\u6e05\u7406\u767d\u76d2",
        "\u5220\u9664\u767d\u76d2", "\u6e05\u9664\u7070\u76d2",
    )


def _inspect_keywords() -> tuple[str, ...]:
    return (
        "inspectblockout", "listblockout", "readblockout",
        "\u67e5\u770b\u767d\u76d2", "\u5217\u51fa\u767d\u76d2",
        "\u573a\u666f\u91cc\u73b0\u5728\u6709\u4ec0\u4e48",
    )


def _normalize(text: str) -> str:
    return "".join(text.lower().split())


def _has_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def _print_result(action: str, result: dict, *, verbose: bool) -> None:
    if verbose:
        status = "OK" if result.get("ok", True) else "ERROR"
        print(f"[blockout] {action}: {status} {result}")


def _print_report(layout: Layout, result: dict) -> None:
    report = result.get("report", {})
    print(f"[blockout] layout={layout.kind} score={report.get('score')} count={result.get('count')}")
    print(f"[blockout] intent={layout.intent}")
    for note in report.get("notes", []):
        print(f"  note: {note}")
    missing = report.get("missing") or []
    if missing:
        print(f"  missing: {', '.join(missing)}")


def _print_summary(transport: Any) -> None:
    result = transport.call("cnd_list")
    if not result.get("ok", True):
        print(f"[blockout] list: ERROR {result}")
        return
    actors = result.get("actors", [])
    blockout = [a for a in actors if a.get("name", "").startswith(BLOCKOUT_PREFIX)]
    print(f"[blockout] actors={len(blockout)}")
    for actor in blockout[-60:]:
        tags = actor.get("tags")
        folder = actor.get("folder")
        suffix = ""
        if folder:
            suffix += f" folder={folder}"
        if tags:
            suffix += f" tags={','.join(tags)}"
        print(f"  - {actor.get('name')} @ {actor.get('location')}{suffix}")


def _selfcheck() -> int:
    from .transport import MockTransport

    cases = [
        ("\u7ade\u6280\u573a\u5173\u5361\u767d\u76d2", "Arena", 13),
        ("\u5c04\u51fb\u63a9\u4f53\u7ade\u6280\u573a\u767d\u76d2", "CoverArena", 20),
        ("\u8d70\u5eca\u5173\u5361\u767d\u76d2", "Corridor", 11),
        ("\u623f\u95f4\u7070\u76d2", "Room", 10),
        ("\u9ed1\u795e\u8bdd\u9996\u9886\u6218\u6597\u767d\u76d2", "MythicBossArena", 21),
        ("\u8fde\u6218\u6218\u6597\u8d70\u5eca\u5173\u5361\u8282\u594f", "MythicGauntlet", 16),
    ]
    for prompt, expected, min_count in cases:
        transport = MockTransport()
        handled = try_handle_blockout_prompt(transport, prompt, verbose=False)
        assert handled, f"not handled: {prompt}"
        actors = transport.call("cnd_list").get("actors", [])
        blockout = [a for a in actors if a["name"].startswith(BLOCKOUT_PREFIX)]
        assert len(blockout) >= min_count, f"expected at least {min_count}, got {len(blockout)}"
        assert any(expected in a["name"] for a in blockout), (
            f"expected {expected} actors, got {[a['name'] for a in blockout]}"
        )
        assert all(a.get("folder") for a in blockout), "missing UE folder metadata"
        assert any("player_start" in a.get("tags", []) for a in blockout), "missing player start tag"
        print(f"OK {expected}: {len(blockout)} actors")

    transport = MockTransport()
    assert try_handle_blockout_prompt(transport, "\u9ed1\u795e\u8bddboss\u767d\u76d2", verbose=False)
    assert try_handle_blockout_prompt(transport, "\u6e05\u9664\u767d\u76d2", verbose=False)
    remaining = transport.call("cnd_list").get("actors", [])
    assert not remaining, f"clear failed: {remaining}"
    print("OK clear_blockout")
    return 0


if __name__ == "__main__":
    raise SystemExit(_selfcheck())
