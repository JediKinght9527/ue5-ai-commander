"""cli —— Cindra-clone 命令行入口。

CindraChat (改场景):
  python -m cindra.cli                  # Mac mock 后端 (默认, 无需 UE)
  python -m cindra.cli --backend ue     # 接真 UE (需开 Remote Execution)
  python -m cindra.cli --once "生成10个cube排成网格"   # 单次执行非交互

CindraDocs (UE 问答 RAG):
  python -m cindra.cli --mode docs                 # lexical 检索 (默认, 离线)
  python -m cindra.cli --mode docs --index embed   # 向量检索 (需 embedding 依赖)
  python -m cindra.cli --mode docs --once "Actor 和 Pawn 区别"

CindraCode (生成符合工程规范的 UE C++, 配项目索引器):
  python -m cindra.cli --mode code                 # 索引自带示例工程
  python -m cindra.cli --mode code --project /path/to/UEProject
  python -m cindra.cli --mode code --once "加一个冲刺技能到角色上"

CindraBlueprint (自然语言搭蓝图事件图):
  python -m cindra.cli --mode blueprint                 # mock 内存图 (默认, 无需 UE)
  python -m cindra.cli --mode blueprint --backend ue    # 真 UE (需 C++ 插件, 见说明)
  python -m cindra.cli --mode blueprint --once "BeginPlay 时打印 hello"

CindraPCG (自然语言操控 UE5.7 PCG 程序化生成, 🆕):
  python -m cindra.cli --mode pcg                       # mock 内存图 (默认)
  python -m cindra.cli --mode pcg --once "在地表上只在平坦区域随机生成橡树"

需要环境变量 ANTHROPIC_API_KEY (跑 agent 时)。
"""
from __future__ import annotations

import argparse
import contextlib
import sys
from pathlib import Path

# Windows consoles are often not UTF-8. Reconfigure so logs from the UE panel
# survive redirection into Saved/Cindra/*.out.txt.
for _stream in (sys.stdout, sys.stderr):
    with contextlib.suppress(AttributeError, ValueError):
        _stream.reconfigure(encoding="utf-8", errors="replace")


def build_transport(backend: str):
    from .transport import MockTransport, RemoteExecTransport
    if backend == "mock":
        return MockTransport()
    if backend == "ue":
        return RemoteExecTransport()
    raise SystemExit(f"unknown backend: {backend}")


def _check_model_config(args) -> int:
    from .model_provider import config_error, provider_name, selected_model

    err = config_error()
    if err:
        print(f"WARNING: {err}", file=sys.stderr)
        return 2
    if not args.quiet:
        print(f"model: {provider_name()} / {selected_model()}")
    return 0


def _repl(agent, banner: str, commands: dict, *, once: str | None = None,
          after_send=None) -> int:
    if once:
        agent.send(once)
        if after_send:
            after_send()
        return 0

    print(banner)
    while True:
        try:
            line = input("you > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line in ("/quit", "/exit"):
            break
        if line == "/reset":
            agent.messages.clear()
            print("(conversation reset)")
            continue
        if line in commands:
            commands[line]()
            continue
        agent.send(line)
        if after_send:
            after_send()
    return 0


def run_chat(args) -> int:
    from .agent import CindraChatAgent
    from .blockout_builder import try_handle_blockout_prompt
    from .scene_intent import try_handle_scene_prompt

    transport = build_transport(args.backend)
    if args.once and try_handle_blockout_prompt(
        transport, args.once, verbose=not args.quiet
    ):
        return 0
    if args.once and try_handle_scene_prompt(
        transport, args.once, verbose=not args.quiet
    ):
        return 0

    config_status = _check_model_config(args)
    if config_status:
        return config_status

    asset_index = None
    if getattr(args, "refresh_assets", False):
        # 真后端: 让 UE 枚举 AssetRegistry 写 manifest, 再从盘上加载
        res = transport.call("cnd_list_assets")
        if res.get("ok"):
            from .asset_index import load_asset_index
            asset_index = load_asset_index(res["path"])
            print(f"asset manifest: {res['count']} 条 <- {res['path']}")
        else:
            print(f"WARNING: 资产枚举失败: {res.get('error')}", file=sys.stderr)

    agent = CindraChatAgent(transport, verbose=not args.quiet,
                            asset_index=asset_index)

    session_name = getattr(args, "session", None)
    if session_name:
        from .session import load_session, save_session
        if load_session(session_name, agent, transport):
            print(f"(session '{session_name}' 已恢复, "
                  f"{len(agent.messages)} 条历史消息)")

    def show_scene():
        if hasattr(transport, "describe_scene"):
            print("\n" + transport.describe_scene())

    def look():
        from .scene_tools import dispatch
        res = dispatch(agent.target, "look_at_scene", {})
        print(f"📷 {res.get('path') if res.get('ok') else res.get('error')}")

    def save_now():
        if not session_name:
            print("(未指定 --session, 无处可存)")
            return
        from .session import save_session
        print(f"(已存到 {save_session(session_name, 'chat', agent, transport)})")

    banner = (f"CindraChat [{args.backend}] -- describe the scene you want.\n"
              "Commands: /scene, /look, /save, /reset, /quit.\n")
    rc = _repl(agent, banner,
               {"/scene": show_scene, "/look": look, "/save": save_now},
               once=args.once, after_send=show_scene)
    if session_name:
        from .session import save_session
        save_session(session_name, "chat", agent, transport)
    return rc


def run_docs(args) -> int:
    config_status = _check_model_config(args)
    if config_status:
        return config_status

    from .docs_agent import CindraDocsAgent
    from .docs_index import build_index
    try:
        index = build_index(args.index)
    except Exception as e:  # noqa: BLE001
        print(f"WARNING: failed to build docs index: {e}", file=sys.stderr)
        return 2
    agent = CindraDocsAgent(index, verbose=not args.quiet)

    def show_topics():
        files = {}
        for c in getattr(index, "chunks", []):
            files[c["file"]] = files.get(c["file"], 0) + 1
        print(f"\ndocs topics ({len(files)} files):")
        for f, n in files.items():
            print(f"  - {f} ({n} chunks)")

    banner = (f"CindraDocs [{args.index}] -- ask UE5 questions from local docs.\n"
              "Commands: /topics, /reset, /quit.\n")
    return _repl(agent, banner, {"/topics": show_topics}, once=args.once)


def run_code(args) -> int:
    config_status = _check_model_config(args)
    if config_status:
        return config_status

    from .code_agent import CindraCodeAgent
    from .project_index import SAMPLE_PROJECT, build_project_index
    root = args.project or SAMPLE_PROJECT
    try:
        index = build_project_index(root)
    except Exception as e:  # noqa: BLE001
        print(f"WARNING: failed to build project index: {e}", file=sys.stderr)
        return 2
    agent = CindraCodeAgent(index, verbose=not args.quiet)

    def show_symbols():
        print(f"\nproject symbols ({len(index.symbols)}):")
        for s in index.symbols:
            parent = f" : {s['parent']}" if s["parent"] else ""
            print(f"  - [{s['kind']}] {s['name']}{parent}  ({s['file']})")

    note = "sample project" if root == SAMPLE_PROJECT else root
    banner = (f"CindraCode [{note}] -- describe the UE C++ feature to build.\n"
              "Commands: /symbols, /reset, /quit.\n")
    return _repl(agent, banner, {"/symbols": show_symbols}, once=args.once)


def run_blueprint(args) -> int:
    config_status = _check_model_config(args)
    if config_status:
        return config_status

    from .blueprint_agent import CindraBlueprintAgent
    from .blueprint_transport import MockBlueprintTransport, UEBlueprintTransport
    transport = (UEBlueprintTransport() if args.backend == "ue"
                 else MockBlueprintTransport())
    agent = CindraBlueprintAgent(transport, verbose=not args.quiet)

    def show_graph():
        if hasattr(transport, "describe_graph"):
            print("\n" + transport.describe_graph())

    banner = (f"CindraBlueprint [{args.backend}] -- describe Blueprint logic.\n"
              "Commands: /graph, /reset, /quit.\n")
    return _repl(agent, banner, {"/graph": show_graph},
                 once=args.once, after_send=show_graph)


def run_pcg(args) -> int:
    import json as _json

    from .pcg_agent import CindraPCGAgent
    from .transport import MockTransport

    agent = CindraPCGAgent(verbose=not args.quiet)

    # 如果给了 --context-scene, 从 mock scene 加载 actors 作 get_actor_data 输入
    if args.context_scene:
        scene = MockTransport().scene
        # 预建场景 actors (用 CLI spawn 命令)
        if args.context_scene != "empty":
            try:
                ops = _json.loads(args.context_scene)
                for op in ops:
                    scene.cnd_spawn(**op)
            except Exception:
                pass
        ctx = {"scene_actors": [
            {"name": a["name"], "location": a["location"],
             "rotation": a.get("rotation", [0, 0, 0]),
             "scale": a.get("scale", [1, 1, 1])}
            for a in scene.actors.values()
        ]}
        agent.pcg_graph._context = ctx

    def show_result():
        print("\n" + agent.pcg_graph.render())
        print(agent.pcg_graph.render_stats())

    banner = ("CindraPCG —— 用自然语言描述程序化生成规则, "
              "我帮你搭 UE5.7 PCG 图并执行。\n"
              "命令: /graph 看当前图, /result 看俯视图+统计, "
              "/reset 清空对话和图, /quit 退出。\n")

    def reset():
        agent.messages.clear()
        agent.pcg_graph.clear()

    return _repl(agent, banner, {# 之前这里是 "\n" + list_graph(), 而 list_graph() 返回 dict ——
# /graph 一敲就 TypeError。list_graph 是给 agent/MCP 用的结构化数据,
# 人看的应该用 render_stats()。
                                 "/graph": lambda: print("\n" + agent.pcg_graph.render_stats()),
                                 "/result": show_result, "/reset": reset},
                 once=args.once, after_send=show_result)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Cindra-clone —— 自然语言操控 UE5")
    p.add_argument("--mode", choices=["chat", "docs", "code", "blueprint", "pcg"],
                   default="chat",
                   help="chat=scene editing, docs=UE docs RAG, code=UE C++, "
                        "blueprint=Blueprint graph, cine=cinematics "
                        "(Sequencer + Movie Render Queue)")
    p.add_argument("--backend", choices=["mock", "ue"], default="mock",
                   help="[chat/blueprint] mock=memory backend, ue=real UE")
    p.add_argument("--index", choices=["lexical", "embed"], default="lexical",
                   help="[docs] lexical=offline keyword search, embed=vector search")
    p.add_argument("--project", metavar="DIR",
                   help="[code] UE 工程根目录, 不给则用自带示例工程")
    p.add_argument("--once", metavar="MSG", help="执行单条指令/问题后退出")
    p.add_argument("--quiet", action="store_true", help="不打印工具调用细节")
    p.add_argument("--context-scene", metavar="JSON",
                   help="[pcg] pre-load mock scene actors as PCG input (JSON list)")
    args = p.parse_args(argv)

    if args.once and args.once_file:
        p.error("--once and --once-file cannot be used together")
    if args.once_file:
        try:
            args.once = Path(args.once_file).read_text(encoding="utf-8-sig")
        except OSError as e:
            print(f"Failed to read --once-file: {e}", file=sys.stderr)
            return 2

    runners = {"chat": run_chat, "docs": run_docs,
               "code": run_code, "blueprint": run_blueprint,
               "pcg": run_pcg}
    return runners[args.mode](args)


if __name__ == "__main__":
    raise SystemExit(main())
