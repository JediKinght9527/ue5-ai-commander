"""cli -- Cindra command line entry point."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Windows consoles are often not UTF-8. Reconfigure so logs from the UE panel
# survive redirection into Saved/Cindra/*.out.txt.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


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
    from .project_index import build_project_index, SAMPLE_PROJECT
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
    from .blueprint_transport import (MockBlueprintTransport,
                                      UEBlueprintTransport)
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


def run_cine(args) -> int:
    config_status = _check_model_config(args)
    if config_status:
        return config_status

    from .cine_agent import CindraCineAgent
    if args.backend == "ue":
        from .transport import RemoteExecTransport
        transport = RemoteExecTransport()
    else:
        from .cine_transport import MockCineTransport
        transport = MockCineTransport()
        # 有会话就把 chat 搭的 mock 场景搬进来 —— 故事板拍的就是你搭的景
        session_name = getattr(args, "session", None)
        if session_name:
            from .session import load_session

            class _Holder:
                messages: list = []
            load_session(session_name, _Holder(), transport)
            if transport.scene.actors:
                print(f"(从 session '{session_name}' 载入 "
                      f"{len(transport.scene.actors)} 个 Actor 的场景)")

    agent = CindraCineAgent(transport, verbose=not args.quiet)

    def storyboard():
        if hasattr(transport, "describe_scene"):
            print("\n" + transport.describe_scene())

    banner = (f"CindraCine [{args.backend}] -- describe the shot you want.\n"
              "Commands: /storyboard, /reset, /quit.\n")
    return _repl(agent, banner, {"/storyboard": storyboard},
                 once=args.once, after_send=storyboard)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Cindra -- natural-language control for UE5",
        epilog=("Model env vars: ANTHROPIC_API_KEY by default; "
                "DeepSeek: CINDRA_MODEL_PROVIDER=deepseek + DEEPSEEK_API_KEY; "
                "GLM/Z.AI: CINDRA_MODEL_PROVIDER=glm + ZAI_API_KEY/GLM_API_KEY; "
                "also supports openai/codex/openrouter/siliconflow/moonshot/"
                "dashscope/ark + corresponding API key."),
    )
    p.add_argument("--mode", choices=["chat", "docs", "code", "blueprint",
                                      "cine"],
                   default="chat",
                   help="chat=scene editing, docs=UE docs RAG, code=UE C++, "
                        "blueprint=Blueprint graph, cine=cinematics "
                        "(Sequencer + Movie Render Queue)")
    p.add_argument("--backend", choices=["mock", "ue"], default="mock",
                   help="[chat/blueprint] mock=memory backend, ue=real UE")
    p.add_argument("--index", choices=["lexical", "embed"], default="lexical",
                   help="[docs] lexical=offline keyword search, embed=vector search")
    p.add_argument("--project", metavar="DIR",
                   help="[code] UE project root; defaults to bundled sample")
    p.add_argument("--once", metavar="MSG", help="run one instruction/question and exit")
    p.add_argument("--quiet", action="store_true", help="hide tool call details")
    p.add_argument("--session", metavar="NAME",
                   help="[chat] persist/restore conversation + scene under "
                        "~/.cindra/sessions/NAME.json")
    p.add_argument("--refresh-assets", action="store_true",
                   help="[chat, ue backend] re-enumerate the project asset "
                        "registry into a manifest before starting")
    p.add_argument("--once-file", metavar="FILE",
                   help="read one UTF-8 prompt/question from a file, then exit")
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
               "cine": run_cine}
    return runners[args.mode](args)


if __name__ == "__main__":
    raise SystemExit(main())
