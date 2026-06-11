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

需要环境变量 ANTHROPIC_API_KEY (跑 agent 时)。
"""
from __future__ import annotations

import argparse
import os
import sys


def build_transport(backend: str):
    from .transport import MockTransport, RemoteExecTransport
    if backend == "mock":
        return MockTransport()
    if backend == "ue":
        return RemoteExecTransport()
    raise SystemExit(f"未知后端: {backend}")


def _repl(agent, banner: str, commands: dict, *, once: str | None = None,
          after_send=None) -> int:
    """四个模式共用的交互循环。

    agent     : 已构建的 Cindra*Agent
    banner    : 进入交互前打印的欢迎/帮助文字
    commands  : {"/cmd": callable} 模式专属斜杠命令 (/reset /quit 内置)
    once      : 非空则单次执行后退出
    after_send: 每次 agent.send 后调用 (如打印场景/图), once 模式也会调用
    """
    if once:
        agent.send(once)
        if after_send:
            after_send()
        return 0

    print(banner)
    while True:
        try:
            line = input("你 > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line in ("/quit", "/exit"):
            break
        if line == "/reset":
            agent.messages.clear()
            print("(对话已清空)")
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
    transport = build_transport(args.backend)
    agent = CindraChatAgent(transport, verbose=not args.quiet)

    def show_scene():
        if hasattr(transport, "describe_scene"):
            print("\n" + transport.describe_scene())

    banner = (f"CindraChat [{args.backend}] —— 用自然语言描述你要的场景。\n"
              "命令: /scene 看当前场景, /reset 清空对话, /quit 退出。\n")
    return _repl(agent, banner, {"/scene": show_scene},
                 once=args.once, after_send=show_scene)


def run_docs(args) -> int:
    from .docs_agent import CindraDocsAgent
    from .docs_index import build_index
    try:
        index = build_index(args.index)
    except Exception as e:  # noqa: BLE001
        print(f"⚠️  构建知识库索引失败: {e}", file=sys.stderr)
        return 2
    agent = CindraDocsAgent(index, verbose=not args.quiet)

    def show_topics():
        files = {}
        for c in getattr(index, "chunks", []):
            files[c["file"]] = files.get(c["file"], 0) + 1
        print(f"\n知识库主题 ({len(files)} 个文件):")
        for f, n in files.items():
            print(f"  - {f} ({n} 块)")

    banner = (f"CindraDocs [{args.index}] —— 问我任何 UE5 相关问题, 我基于本地知识库作答。\n"
              "命令: /topics 看知识库覆盖, /reset 清空对话, /quit 退出。\n")
    return _repl(agent, banner, {"/topics": show_topics}, once=args.once)


def run_code(args) -> int:
    from .code_agent import CindraCodeAgent
    from .project_index import build_project_index, SAMPLE_PROJECT
    root = args.project or SAMPLE_PROJECT
    try:
        index = build_project_index(root)
    except Exception as e:  # noqa: BLE001
        print(f"⚠️  构建工程索引失败: {e}", file=sys.stderr)
        return 2
    agent = CindraCodeAgent(index, verbose=not args.quiet)

    def show_symbols():
        print(f"\n工程符号 ({len(index.symbols)} 个):")
        for s in index.symbols:
            par = f" : {s['parent']}" if s["parent"] else ""
            print(f"  - [{s['kind']}] {s['name']}{par}  ({s['file']})")

    note = "自带示例工程" if root == SAMPLE_PROJECT else root
    banner = (f"CindraCode [{note}] —— 描述要实现的功能, 我生成符合工程规范的 UE C++。\n"
              "命令: /symbols 看工程已有符号, /reset 清空对话, /quit 退出。\n")
    return _repl(agent, banner, {"/symbols": show_symbols}, once=args.once)


def run_blueprint(args) -> int:
    from .blueprint_agent import CindraBlueprintAgent
    from .blueprint_transport import (MockBlueprintTransport,
                                      UEBlueprintTransport)
    transport = (UEBlueprintTransport() if args.backend == "ue"
                 else MockBlueprintTransport())
    agent = CindraBlueprintAgent(transport, verbose=not args.quiet)

    def show_graph():
        if hasattr(transport, "describe_graph"):
            print("\n" + transport.describe_graph())

    banner = (f"CindraBlueprint [{args.backend}] —— 用自然语言描述蓝图逻辑, 我帮你搭节点和连线。\n"
              "命令: /graph 看当前图, /reset 清空对话, /quit 退出。\n")
    return _repl(agent, banner, {"/graph": show_graph},
                 once=args.once, after_send=show_graph)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Cindra-clone —— 自然语言操控 UE5")
    p.add_argument("--mode", choices=["chat", "docs", "code", "blueprint"],
                   default="chat",
                   help="chat=改场景(默认), docs=UE问答RAG, code=生成UE C++, "
                        "blueprint=搭蓝图图")
    p.add_argument("--backend", choices=["mock", "ue"], default="mock",
                   help="[chat/blueprint] mock=Mac内存(默认), ue=真UE")
    p.add_argument("--index", choices=["lexical", "embed"], default="lexical",
                   help="[docs] lexical=关键词检索(默认,离线), embed=向量检索")
    p.add_argument("--project", metavar="DIR",
                   help="[code] UE 工程根目录, 不给则用自带示例工程")
    p.add_argument("--once", metavar="MSG", help="执行单条指令/问题后退出")
    p.add_argument("--quiet", action="store_true", help="不打印工具调用细节")
    args = p.parse_args(argv)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("⚠️  请先设置 ANTHROPIC_API_KEY 环境变量。", file=sys.stderr)
        return 2

    runners = {"chat": run_chat, "docs": run_docs,
               "code": run_code, "blueprint": run_blueprint}
    return runners[args.mode](args)


if __name__ == "__main__":
    raise SystemExit(main())
