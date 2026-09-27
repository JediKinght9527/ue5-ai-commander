"""cine_tools —— 运镜模式的工具 schema + dispatch。

镜头数学 (orbit/dolly/crane/flyover) 在 camera_math 里算好, camera_move
把关键帧数组喂给 cnd_seq_add_keys —— agent 说"环绕一圈", 工具出整段轨迹。
render_sequence: mock 同步返回故事板帧; 真 UE 走 MRQ pending 协议,
这里轮询帧数稳定后, 把首/中/末 3 帧作为 images 回给 agent 审片。
"""

from __future__ import annotations

import os
import time
from typing import Any

from .camera_math import PRESETS

TOOLS: list[dict] = [
    {
        "name": "create_sequence",
        "description": "新建一个 Level Sequence (运镜的容器)。",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "fps": {"type": "integer", "description": "默认 24"},
                "seconds": {"type": "number", "description": "时长秒, 默认 8"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "add_cinematic_camera",
        "description": "往序列里加一台电影相机 (含 transform 轨道和整段 camera cut)。",
        "input_schema": {
            "type": "object",
            "properties": {
                "sequence": {"type": "string"},
                "name": {"type": "string", "description": "相机名, 可省"},
            },
            "required": ["sequence"],
        },
    },
    {
        "name": "camera_move",
        "description": "给相机生成一段预设运镜并写入关键帧: orbit=环绕, dolly=推拉, "
        "crane=升降, flyover=飞掠, static=定机位。工具负责全部轨迹数学, "
        "你只描述意图 (中心/距离/圈数等)。",
        "input_schema": {
            "type": "object",
            "properties": {
                "sequence": {"type": "string"},
                "camera": {"type": "string"},
                "preset": {
                    "type": "string",
                    "enum": ["orbit", "dolly", "crane", "flyover", "static"],
                },
                "center": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "orbit/crane 的环绕中心",
                },
                "distance": {"type": "number", "description": "orbit/crane 距中心距离, 默认 800"},
                "pitch": {"type": "number", "description": "orbit 俯角, 默认 20"},
                "revolutions": {"type": "number", "description": "orbit 圈数, 默认 1"},
                "start": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "dolly/flyover 起点",
                },
                "end": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "dolly/flyover 终点",
                },
                "look_at": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "dolly/static 恒看向的点",
                },
                "start_height": {"type": "number", "description": "crane 起始高度"},
                "end_height": {"type": "number", "description": "crane 结束高度"},
                "height": {"type": "number", "description": "flyover 飞行高度"},
                "seconds": {"type": "number", "description": "本段时长, 默认全序列"},
                "fps": {"type": "integer", "description": "默认 24"},
            },
            "required": ["sequence", "camera", "preset"],
        },
    },
    {
        "name": "add_camera_cut",
        "description": "指定某帧段用哪台相机 (多机位剪辑)。单相机不用调, "
        "add_cinematic_camera 已给整段默认 cut。",
        "input_schema": {
            "type": "object",
            "properties": {
                "sequence": {"type": "string"},
                "camera": {"type": "string"},
                "start_frame": {"type": "integer"},
                "end_frame": {"type": "integer"},
            },
            "required": ["sequence", "camera"],
        },
    },
    {
        "name": "render_sequence",
        "description": "渲染序列成帧序列 (mock=故事板, 真 UE=Movie Render Queue)。"
        "返回首/中/末 3 帧画面, 你要真的审片: 构图/节奏/穿帮, "
        "不满意就调整关键帧重渲, 最多 2 轮。",
        "input_schema": {
            "type": "object",
            "properties": {
                "sequence": {"type": "string"},
                "out_dir": {"type": "string"},
            },
            "required": ["sequence"],
        },
    },
    {
        "name": "review_render",
        "description": "重看已渲染序列的指定帧 (不重渲)。frames 是帧文件序号列表, "
        "如 [0, 3, 7]; 省略则取首/中/末。",
        "input_schema": {
            "type": "object",
            "properties": {
                "sequence": {"type": "string"},
                "frames": {"type": "array", "items": {"type": "integer"}},
            },
            "required": ["sequence"],
        },
    },
    {
        "name": "list_sequence",
        "description": "列出所有序列, 或看某个序列的相机/关键帧/cut 详情。",
        "input_schema": {
            "type": "object",
            "properties": {"sequence": {"type": "string"}},
        },
    },
    {
        "name": "list_actors",
        "description": "列出场景 Actor (找运镜目标/包围盒时用)。",
        "input_schema": {"type": "object", "properties": {}},
    },
]


def _build_keys(args: dict) -> list[dict] | dict:
    """camera_move 参数 -> camera_math 关键帧。返回 keys 或错误 dict。"""
    preset = args["preset"]
    fps = int(args.get("fps", 24))
    seconds = float(args.get("seconds", 8.0))
    if preset == "static":
        loc = args.get("start") or args.get("center") or [0, 0, 500]
        from .camera_math import as_vec3, look_at_rotation

        rot = list(look_at_rotation(as_vec3(loc), as_vec3(args.get("look_at", (0, 0, 0)))))
        return [
            {"frame": 0, "location": list(loc), "rotation": rot},
            {"frame": int(fps * seconds), "location": list(loc), "rotation": rot},
        ]
    fn = PRESETS.get(preset)
    if fn is None:
        return {"ok": False, "error": f"unknown preset: {preset}"}
    try:
        if preset == "orbit":
            return fn(
                tuple(args.get("center", (0, 0, 0))),
                distance=float(args.get("distance", 800)),
                pitch=float(args.get("pitch", 20)),
                revolutions=float(args.get("revolutions", 1)),
                fps=fps,
                seconds=seconds,
            )
        if preset == "dolly":
            return fn(
                tuple(args["start"]),
                tuple(args["end"]),
                look_at=tuple(args["look_at"]) if args.get("look_at") else None,
                fps=fps,
                seconds=seconds,
            )
        if preset == "crane":
            return fn(
                tuple(args.get("center", (0, 0, 0))),
                distance=float(args.get("distance", 600)),
                start_height=float(args.get("start_height", 100)),
                end_height=float(args.get("end_height", 900)),
                fps=fps,
                seconds=seconds,
            )
        if preset == "flyover":
            return fn(
                tuple(args["start"]),
                tuple(args["end"]),
                height=float(args.get("height", 500)),
                fps=fps,
                seconds=seconds,
            )
    except KeyError as e:
        return {"ok": False, "error": f"{preset} 缺少必要参数: {e}"}
    return {"ok": False, "error": f"unreachable preset: {preset}"}


def _wait_frames(out_dir: str, expected: int, timeout: float = 600.0) -> int:
    """真 UE MRQ 异步渲染: 轮询帧目录到数量稳定 (两拍不变) 或超时。"""
    deadline = time.time() + timeout
    last = -1
    stable = 0
    while time.time() < deadline:
        try:
            n = len([f for f in os.listdir(out_dir) if f.endswith(".png")])
        except OSError:
            n = 0
        if n > 0 and n == last:
            stable += 1
            if stable >= 2 and (n >= expected or stable >= 10):
                return n
        else:
            stable = 0
        last = n
        time.sleep(2.0)
    return max(0, last)


def _pick_frames(out_dir: str, indices: list[int] | None = None) -> list[str]:
    files = sorted(os.path.join(out_dir, f) for f in os.listdir(out_dir) if f.endswith(".png"))
    if not files:
        return []
    if indices:
        return [files[i] for i in indices if 0 <= i < len(files)]
    return [files[0], files[len(files) // 2], files[-1]]


def dispatch(ctx, name: str, args: dict[str, Any]) -> dict:
    transport = getattr(ctx, "transport", ctx)

    if name == "create_sequence":
        kw = {"name": args["name"]}
        if args.get("fps"):
            kw["fps"] = int(args["fps"])
        if args.get("seconds"):
            kw["seconds"] = float(args["seconds"])
        return transport.call("cnd_seq_create", **kw)

    if name == "add_cinematic_camera":
        kw = {"sequence": args["sequence"]}
        if args.get("name"):
            kw["camera_name"] = args["name"]
        return transport.call("cnd_seq_add_camera", **kw)

    if name == "camera_move":
        keys = _build_keys(args)
        if isinstance(keys, dict):
            return keys
        return transport.call(
            "cnd_seq_add_keys", sequence=args["sequence"], camera=args["camera"], keys=keys
        )

    if name == "add_camera_cut":
        return transport.call(
            "cnd_seq_add_cut",
            sequence=args["sequence"],
            camera=args["camera"],
            start_frame=args.get("start_frame"),
            end_frame=args.get("end_frame"),
        )

    if name == "render_sequence":
        kw = {"sequence": args["sequence"]}
        if args.get("out_dir"):
            kw["out_dir"] = args["out_dir"]
        res = transport.call("cnd_seq_render", **kw)
        if res.get("ok") and res.get("pending"):
            # 真 UE: MRQ 异步, 轮询帧目录
            out_dir = res.get("out_dir", "")
            n = _wait_frames(out_dir, int(res.get("expected_frames", 0)))
            if n <= 0:
                return {
                    "ok": False,
                    "error": f"渲染超时, {out_dir} 没有产出帧 (MRQ 插件是否启用? 关卡是否已保存?)",
                }
            res = dict(res)
            res.pop("pending", None)
            res["frames_rendered"] = n
            res["images"] = _pick_frames(out_dir)
        return res

    if name == "review_render":
        listed = transport.call("cnd_seq_list", sequence=args["sequence"])
        if not listed.get("ok"):
            return listed
        # mock 存了 rendered 路径; 真 UE 按约定目录找
        model = getattr(transport, "model", None)
        if model is not None:
            seq = model.sequences.get(args["sequence"], {})
            frames = seq.get("rendered", [])
            if not frames:
                return {"ok": False, "error": "还没渲染过, 先 render_sequence"}
            idx = args.get("frames")
            picks = (
                [frames[i] for i in idx if 0 <= i < len(frames)]
                if idx
                else [frames[0], frames[len(frames) // 2], frames[-1]]
            )
        else:
            out_dir = args.get("out_dir", "")
            picks = _pick_frames(out_dir, args.get("frames"))
            if not picks:
                return {"ok": False, "error": "找不到已渲染的帧"}
        return {
            "ok": True,
            "action": "review_render",
            "sequence": args["sequence"],
            "images": picks,
        }

    if name == "list_sequence":
        kw = {}
        if args.get("sequence"):
            kw["sequence"] = args["sequence"]
        return transport.call("cnd_seq_list", **kw)

    if name == "list_actors":
        return transport.call("cnd_list")

    return {"ok": False, "error": f"unknown tool: {name}"}
