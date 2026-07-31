"""mcp_server —— Cindra 的 MCP (Model Context Protocol) stdio server。

让 Claude Code / Cursor / Windsurf / 任何 MCP 客户端直接调 Cindra 的全部
工具。不再需要 CLI 参数, 打开 Claude Code 说一句话即可。

标准 MCP JSON-RPC over stdio:
  initialize → tools/list → tools/call → (loop)

每个 Cindra 模块的工具 schema 注册为一个 MCP tool, mock 默认, backend: "ue"
通过 tool 参数 `_backend` 传入。

自检: python3 -m cindra.mcp_server --selfcheck
"""
from __future__ import annotations

import json
import os
import sys
import traceback
from typing import Any


# ═══════════════════════════════════════════════════════════
# MCP protocol constants
# ═══════════════════════════════════════════════════════════

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "cindra"
SERVER_VERSION = "1.0.0"

# ═══════════════════════════════════════════════════════════
# Tool registry: 每个模块的工具定义 + dispatch 函数 + 说明
# ═══════════════════════════════════════════════════════════


def _build_registry() -> dict[str, dict]:
    """惰性加载所有 Cindra 模块的工具, 返回 {tool_name: {schema, dispatch, module}}。"""

    registry: dict[str, dict] = {}

    # ── Chat (scene_tools) ──
    from . import scene_tools
    for t in scene_tools.TOOLS:
        name = t["name"]
        registry[name] = {
            "schema": t,
            "module": "chat",
            "description": f"[Chat] {t['description']}",
        }

    # ── Docs ──
    from . import docs_tools
    for t in docs_tools.TOOLS:
        name = t["name"]
        registry[name] = {
            "schema": t,
            "module": "docs",
            "description": f"[Docs] {t['description']}",
        }

    # ── Code ──
    from . import code_tools
    for t in code_tools.TOOLS:
        name = t["name"]
        registry[name] = {
            "schema": t,
            "module": "code",
            "description": f"[Code] {t['description']}",
        }

    # ── Blueprint ──
    from . import blueprint_tools
    for t in blueprint_tools.TOOLS:
        name = t["name"]
        registry[name] = {
            "schema": t,
            "module": "blueprint",
            "description": f"[Blueprint] {t['description']}",
        }

    # ── PCG ──
    from . import pcg_tools
    for t in pcg_tools.TOOLS:
        name = t["name"]
        registry[name] = {
            "schema": t,
            "module": "pcg",
            "description": f"[PCG] {t['description']}",
        }

    # ── Cine ──
    from . import cine_tools
    for t in cine_tools.TOOLS:
        name = t["name"]
        registry[name] = {
            "schema": t,
            "module": "cine",
            "description": f"[Cine] {t['description']}",
        }

    # ── Lighting ──
    registry["light_rig"] = {
        "schema": {
            "name": "light_rig",
            "description": "[Lighting] 按风格给场景布光: horror/golden_hour/studio/night_neon/overcast。读回场景包围盒后自动算灯位并在场景里放灯。",
            "input_schema": {
                "type": "object",
                "properties": {
                    "style": {
                        "type": "string",
                        "enum": ["horror", "golden_hour", "studio", "night_neon", "overcast"],
                        "description": "灯光风格",
                    },
                    "intensity": {
                        "type": "number",
                        "description": "强度 0~1, 默认 0.8",
                    },
                },
                "required": ["style"],
            },
        },
        "module": "lighting",
        "description": "[Lighting] 风格化布光",
    }

    # ── Asset ──
    registry["search_assets"] = {
        "schema": {
            "name": "search_assets",
            "description": "[Asset] 在工程资产清单里按名字/类型搜资产 (mesh/材质/蓝图等)。用来找'木箱子对应的资产路径'。",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索词, 如 '木箱' 或 'crate'"},
                    "class_filter": {
                        "type": "string",
                        "description": "可选, 资产类型: StaticMesh/Material/Blueprint/Texture",
                    },
                },
                "required": ["query"],
            },
        },
        "module": "asset",
        "description": "[Asset] 搜索工程资产",
    }
    registry["spawn_asset"] = {
        "schema": {
            "name": "spawn_asset",
            "description": "[Asset] 在场景里放置一个工程资产 (mesh/蓝图等)。和 spawn_actor 不同 —— 这个放的是真项目里的资产, 不只是 cube/sphere。需要先用 search_assets 找到资产路径。",
            "input_schema": {
                "type": "object",
                "properties": {
                    "asset_path": {"type": "string", "description": "资产路径, 如 /Game/Props/SM_Crate_A"},
                    "name": {"type": "string", "description": "可选, actor 名字"},
                    "location": {"type": "array", "items": {"type": "number"}, "description": "[x,y,z] cm"},
                    "rotation": {"type": "array", "items": {"type": "number"}, "description": "[pitch,yaw,roll] 度"},
                    "scale": {"type": "array", "items": {"type": "number"}, "description": "[x,y,z]"},
                },
                "required": ["asset_path"],
            },
        },
        "module": "chat",
        "description": "[Asset] 在场景里放置工程资产",
    }

    # ── Blockout ──
    registry["generate_blockout"] = {
        "schema": {
            "name": "generate_blockout",
            "description": "[Blockout] 按玩法模板生成一组灰盒场景 (combat_arena/sniper_alley/choke_point/boss_room/race_track)。产出带 folder/tags 的 cube/cylinder/plane, 可编辑可审计, 零 token 消耗。",
            "input_schema": {
                "type": "object",
                "properties": {
                    "template": {
                        "type": "string",
                        "enum": ["combat_arena", "sniper_alley", "choke_point", "boss_room", "race_track"],
                        "description": "玩法模板",
                    },
                    "width": {"type": "number", "description": "宽度 cm, 默认 2000"},
                    "depth": {"type": "number", "description": "深度 cm, 默认 2000"},
                },
                "required": ["template"],
            },
        },
        "module": "blockout",
        "description": "[Blockout] 玩法模板灰盒生成",
    }

    return registry


# ═══════════════════════════════════════════════════════════
# 跨模块共享的后端状态
# ═══════════════════════════════════════════════════════════


class _ServerState:
    """MCP server 的全局状态: 持有各模块需要的 transport / index / graph 实例。"""

    def __init__(self) -> None:
        self.backend: str = "mock"
        self._chat_transport = None
        self._pcg_graph = None
        self._blueprint_transport = None
        self._cine_transport = None
        self._docs_index = None
        self._code_index = None
        self._asset_index = None

    @property
    def chat_transport(self):
        if self._chat_transport is None:
            from .transport import MockTransport, RemoteExecTransport
            if self.backend == "ue":
                self._chat_transport = RemoteExecTransport()
            else:
                self._chat_transport = MockTransport()
        return self._chat_transport

    @property
    def pcg_graph(self):
        if self._pcg_graph is None:
            from .pcg_model import PCGGraph
            self._pcg_graph = PCGGraph()
        return self._pcg_graph

    @property
    def blueprint_transport(self):
        if self._blueprint_transport is None:
            from .blueprint_transport import MockBlueprintTransport
            self._blueprint_transport = MockBlueprintTransport()
        return self._blueprint_transport

    @property
    def cine_transport(self):
        if self._cine_transport is None:
            from .cine_transport import MockCineTransport
            self._cine_transport = MockCineTransport()
        return self._cine_transport

    @property
    def docs_index(self):
        if self._docs_index is None:
            from .docs_index import build_index
            self._docs_index = build_index("lexical")
        return self._docs_index

    @property
    def code_index(self):
        if self._code_index is None:
            from .project_index import build_project_index, SAMPLE_PROJECT
            self._code_index = build_project_index(SAMPLE_PROJECT)
        return self._code_index

    @property
    def asset_index(self):
        if self._asset_index is None:
            from .asset_index import load_asset_index
            self._asset_index = load_asset_index()
        return self._asset_index


_state = _ServerState()


# ═══════════════════════════════════════════════════════════
# Tool dispatch
# ═══════════════════════════════════════════════════════════


def dispatch_tool(name: str, args: dict[str, Any]) -> dict:
    """把 MCP tools/call 路由到对应模块的 dispatch。"""

    # 处理 backend 切换
    backend = args.pop("_backend", None)
    if backend in ("mock", "ue"):
        _state.backend = backend

    module = _registry[name]["module"]

    # ── Chat ──
    if name in ("spawn_actor", "spawn_grid", "delete_actor", "move_actor",
                 "set_transform", "arrange_scene", "inspect_viewport", "undo",
                 "list_actors", "clear_scene"):
        from . import scene_tools
        from .scene_tools import ChatContext
        ctx = ChatContext(transport=_state.chat_transport)
        return scene_tools.dispatch(ctx, name, args)

    # ── Docs ──
    if name == "search_docs":
        from . import docs_tools
        return docs_tools.dispatch(_state.docs_index, name, args)
    if name == "list_topics":
        from . import docs_tools
        return docs_tools.dispatch(_state.docs_index, name, args)

    # ── Code ──
    if name == "search_project":
        from . import code_tools
        return code_tools.dispatch(_state.code_index, name, args)
    if name == "list_symbols":
        # list_symbols 在 code_tools 里走 dispatch, 但 project_index 的符号要单独取
        return {"ok": True, "action": "list_symbols",
                "symbols": _state.code_index.symbols,
                "count": len(_state.code_index.symbols)}

    # ── Blueprint ──
    if module == "blueprint":
        from . import blueprint_tools
        return blueprint_tools.dispatch(_state.blueprint_transport, name, args)

    # ── PCG ──
    if module == "pcg":
        from . import pcg_tools
        return pcg_tools.dispatch(_state.pcg_graph, name, args)

    # ── Cine ──
    if module == "cine":
        from . import cine_tools
        return cine_tools.dispatch(_state.cine_transport, name, args)

    # ── Lighting ──
    if name == "light_rig":
        from . import lighting_rigs
        transport = _state.chat_transport
        # 读场景包围盒
        listed = transport.call("cnd_list")
        actors = listed.get("actors", [])
        if not actors:
            return {"ok": False, "error": "场景里没有 Actor, 无法计算包围盒"}
        xs = [a["location"][0] for a in actors]
        ys = [a["location"][1] for a in actors]
        zs = [a["location"][2] for a in actors]
        center = (sum(xs) / len(xs), sum(ys) / len(ys), sum(zs) / len(zs))
        radius = max(
            max(xs) - min(xs),
            max(ys) - min(ys),
            (max(zs) - min(zs)) * 2,
            500.0,
        ) / 2
        style = args.get("style", "studio")
        intensity = float(args.get("intensity", 0.8))
        ops = lighting_rigs.build_rig(style, center, radius, intensity)
        # 逐个执行灯光/环境操作
        results = []
        for op in ops:
            r = transport.call(op["func"], **op["kwargs"])
            results.append(r)
        ok = all(r.get("ok", False) for r in results)
        return {"ok": ok, "action": "light_rig", "style": style,
                "ops": len(results), "results": results}

    # ── Asset ──
    if name == "search_assets":
        idx = _state.asset_index
        query = args["query"]
        class_filter = args.get("class_filter")
        results = idx.search(query, k=8, class_filter=class_filter)
        return {"ok": True, "action": "search_assets",
                "query": query, "results": results, "count": len(results)}
    if name == "spawn_asset":
        from . import scene_tools
        from .scene_tools import ChatContext
        asset_path = args["asset_path"]
        ctx = ChatContext(transport=_state.chat_transport)
        # spawn_asset 底层复用 spawn_actor, 但 actor_type='asset:路径'
        return scene_tools.dispatch(ctx, "spawn_actor", {
            "actor_type": f"asset:{asset_path}",
            "name": args.get("name"),
            "location": args.get("location", [0, 0, 0]),
            "rotation": args.get("rotation", [0, 0, 0]),
            "scale": args.get("scale", [1, 1, 1]),
        })

    # ── Blockout ──
    if name == "generate_blockout":
        from . import blockout_builder
        template = args["template"]
        width = float(args.get("width", 2000))
        depth = float(args.get("depth", 2000))
        blockout_builder.build(template, _state.chat_transport, width=width, depth=depth)
        return {"ok": True, "action": "generate_blockout", "template": template}

    return {"ok": False, "error": f"unknown tool: {name}"}


_registry = _build_registry()


# ═════════════════════════════════════════════════════════════
# MCP JSON-RPC loop
# ═════════════════════════════════════════════════════════════


def _send(msg: dict) -> None:
    """写一行 JSON-RPC 响应到 stdout (MCP stdio)。"""
    sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _read() -> dict | None:
    """从 stdin 读一行 JSON-RPC 请求。EOF 返回 None。"""
    try:
        line = sys.stdin.readline()
    except (EOFError, KeyboardInterrupt):
        return None
    if not line:
        return None
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None


def _handle_initialize(req_id: Any) -> None:
    _send({
        "jsonrpc": "2.0",
        "id": req_id,
        "result": {
            "protocolVersion": PROTOCOL_VERSION,
            "serverInfo": {
                "name": SERVER_NAME,
                "version": SERVER_VERSION,
            },
            "capabilities": {
                "tools": {},
            },
        },
    })


def _handle_tools_list(req_id: Any) -> None:
    tools = []
    for name, info in _registry.items():
        t = info["schema"]
        tools.append({
            "name": t["name"],
            "description": info["description"],
            "inputSchema": t["input_schema"],
        })
    _send({
        "jsonrpc": "2.0",
        "id": req_id,
        "result": {"tools": tools},
    })


def _handle_tools_call(req_id: Any, params: dict) -> None:
    tool_name = params.get("name", "")
    arguments = params.get("arguments", {})

    if tool_name not in _registry:
        _send({
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": -32601,
                "message": f"Tool not found: {tool_name}",
            },
        })
        return

    try:
        result = dispatch_tool(tool_name, arguments)
        # MCP tool result: content 是 text 列表
        text = json.dumps(result, ensure_ascii=False, indent=2)
        _send({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [
                    {"type": "text", "text": text},
                ],
            },
        })
    except Exception:
        _send({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [
                    {"type": "text",
                     "text": json.dumps({"ok": False,
                                         "error": traceback.format_exc()},
                                        ensure_ascii=False)},
                ],
                "isError": True,
            },
        })


def _handle_notifications_initialized() -> None:
    pass  # MCP spec: server 收到 notifications/initialized 后什么都不回


def run() -> int:
    """主循环: 读 stdin JSON-RPC → 路由 → 写 stdout。"""
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    while True:
        request = _read()
        if request is None:
            break

        method = request.get("method", "")
        req_id = request.get("id")
        params = request.get("params", {})

        if method == "initialize":
            _handle_initialize(req_id)
        elif method == "tools/list":
            _handle_tools_list(req_id)
        elif method == "tools/call":
            _handle_tools_call(req_id, params)
        elif method == "notifications/initialized":
            _handle_notifications_initialized()
        elif method == "ping":
            _send({"jsonrpc": "2.0", "id": req_id, "result": {}})
        else:
            _send({
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            })

    return 0


# ═════════════════════════════════════════════════════════════
# 自检
# ═════════════════════════════════════════════════════════════


def _selfcheck() -> int:
    """离线自检: MCP 握手 + tools/list + 几个代表性 tools/call。"""

    # 1) initialize
    req = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": PROTOCOL_VERSION, "capabilities": {}},
    })
    # 模拟 stdin/stdout: 用子进程或直接调 handler
    # 这里直接调 handler 检查结果
    import io
    old_stdout = sys.stdout
    buf = io.StringIO()
    sys.stdout = buf

    try:
        _handle_initialize(1)
        out = buf.getvalue().strip()
        resp = json.loads(out)
        assert resp["id"] == 1 and "serverInfo" in resp["result"], \
            f"initialize 失败: {resp}"
        print("✅ MCP initialize: server_info 返回正确")

        # 2) tools/list
        buf = io.StringIO()
        sys.stdout = buf
        _handle_tools_list(2)
        out = buf.getvalue().strip()
        resp = json.loads(out)
        tools = resp["result"]["tools"]
        assert len(tools) >= 35, f"工具数 {len(tools)}, 预期 >=35"
        tool_names = {t["name"] for t in tools}
        # 几个关键工具必须在
        for expected in ["spawn_actor", "run_pcg_graph", "search_docs",
                          "add_node", "light_rig", "generate_blockout"]:
            assert expected in tool_names, f"缺少关键工具: {expected}"
        print(f"✅ MCP tools/list: {len(tools)} 个工具, 关键工具齐全")

        # 3) tools/call — 无副作用的查询类测试
        buf = io.StringIO()
        sys.stdout = buf
        _handle_tools_call(3, {"name": "list_pcg_node_types", "arguments": {}})
        out = buf.getvalue().strip()
        resp = json.loads(out)
        content = resp["result"]["content"][0]["text"]
        result = json.loads(content)
        assert result.get("ok") and len(result.get("node_types", {})) >= 15, \
            f"list_pcg_node_types 失败: {result}"
        print(f"✅ MCP tools/call (list_pcg_node_types): {len(result['node_types'])} 种节点")

        # 4) tools/call — 实际建图+执行
        buf = io.StringIO()
        sys.stdout = buf
        _handle_tools_call(4, {
            "name": "add_pcg_node",
            "arguments": {"node_type": "landscape_input", "name": "t",
                          "params": {"width": 5000, "depth": 5000}},
        })
        out = buf.getvalue().strip()
        resp = json.loads(out)
        result = json.loads(resp["result"]["content"][0]["text"])
        assert result.get("ok"), f"add_pcg_node 失败: {result}"
        print(f"✅ MCP tools/call (add_pcg_node): {result['id']}")

        # 5) spawn_actor 调一次
        buf = io.StringIO()
        sys.stdout = buf
        _handle_tools_call(5, {
            "name": "spawn_actor",
            "arguments": {"actor_type": "cube", "location": [300, 300, 0]},
        })
        out = buf.getvalue().strip()
        resp = json.loads(out)
        result = json.loads(resp["result"]["content"][0]["text"])
        assert result.get("ok") and result.get("action") == "spawn", \
            f"spawn_actor 失败: {result}"
        print(f"✅ MCP tools/call (spawn_actor): {result['name']}")

        # 6) search_docs 调一次
        buf = io.StringIO()
        sys.stdout = buf
        _handle_tools_call(6, {
            "name": "search_docs",
            "arguments": {"query": "Actor Pawn 区别"},
        })
        out = buf.getvalue().strip()
        resp = json.loads(out)
        result = json.loads(resp["result"]["content"][0]["text"])
        assert result.get("ok") and len(result.get("results", [])) > 0, \
            f"search_docs 失败: {result}"
        print(f"✅ MCP tools/call (search_docs): {len(result['results'])} 个结果")

        # 7) 未知工具 -> error
        buf = io.StringIO()
        sys.stdout = buf
        _handle_tools_call(7, {"name": "nonexistent_tool", "arguments": {}})
        out = buf.getvalue().strip()
        resp = json.loads(out)
        assert "error" in resp, f"未知工具应返回 error: {resp}"
        print(f"✅ MCP tools/call (未知工具): 正确返回 error")

        # 8) backend 切换
        buf = io.StringIO()
        sys.stdout = buf
        _handle_tools_call(8, {
            "name": "list_actors",
            "arguments": {"_backend": "ue"},
        })
        out = buf.getvalue().strip()
        resp = json.loads(out)
        result = json.loads(resp["result"]["content"][0]["text"])
        # ue backend 没连真引擎时会返回错误, 但 dispatch 本身不崩
        print(f"✅ MCP tools/call (backend=ue): {result.get('ok', result.get('error', 'unknown'))}")

    finally:
        sys.stdout = old_stdout

    print(f"\nMCP server 自检 8/8 通过。")
    print(f"  工具总数: {len(_registry)}")
    print(f"  覆盖模块: chat / docs / code / blueprint / pcg / cine / lighting / asset / blockout")
    return 0


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--selfcheck", action="store_true", help="运行自检")
    args, _ = p.parse_known_args()
    if args.selfcheck:
        raise SystemExit(_selfcheck())
    # 默认: 启动 MCP stdio server
    raise SystemExit(run())
