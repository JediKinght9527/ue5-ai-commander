"""Command bus for running Cindra through portable CLI runners.

UE should not know whether a request is handled by Cindra's built-in agent,
Claude Code, Codex, or another command-line tool. It writes a prompt file and
calls this module. This module is the stable command boundary.
"""
from __future__ import annotations

import argparse
import contextlib
import os
import subprocess
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    with contextlib.suppress(AttributeError, ValueError):
        _stream.reconfigure(encoding="utf-8", errors="replace")


DEFAULT_CLAUDE_TEMPLATE = "claude -p {prompt:q}"
DEFAULT_CODEX_TEMPLATE = "codex exec {prompt:q}"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Cindra command bus for UE/editor integrations"
    )
    parser.add_argument("--runner", default=os.environ.get("CINDRA_RUNNER", "cindra"),
                        choices=["cindra", "claude", "codex", "custom"],
                        help="command runner to use")
    parser.add_argument("--mode", default="chat",
                        choices=["chat", "docs", "code", "blueprint"])
    parser.add_argument("--backend", default="ue", choices=["mock", "ue"])
    parser.add_argument("--index", default="lexical", choices=["lexical", "embed"])
    parser.add_argument("--project", default="")
    parser.add_argument("--prompt-file", required=True)
    parser.add_argument("--cwd", default=os.environ.get("CINDRA_PROJECT_ROOT") or os.getcwd())
    parser.add_argument("--dry-run", action="store_true",
                        help="print the command that would run")
    args = parser.parse_args(argv)

    prompt_path = Path(args.prompt_file)
    try:
        prompt = prompt_path.read_text(encoding="utf-8-sig")
    except OSError as e:
        print(f"ERROR: failed to read prompt file: {e}", file=sys.stderr)
        return 2

    runner = args.runner.lower()
    if runner == "cindra":
        return _run_cindra(args)
    if runner in ("claude", "codex", "custom"):
        return _run_template(runner, args, prompt)
    print(f"ERROR: unknown runner: {args.runner}", file=sys.stderr)
    return 2


def _run_cindra(args) -> int:
    cmd = [
        sys.executable,
        "-m",
        "cindra.cli",
        "--mode",
        args.mode,
        "--backend",
        args.backend,
        "--once-file",
        args.prompt_file,
    ]
    if args.mode == "docs":
        cmd.extend(["--index", args.index])
    if args.mode == "code" and args.project:
        cmd.extend(["--project", args.project])
    if args.dry_run:
        print(_display_cmd(cmd))
        return 0
    print(f"[command-bus] runner=cindra cwd={args.cwd}", flush=True)
    print(f"[command-bus] command={_display_cmd(cmd)}", flush=True)
    return subprocess.run(cmd, cwd=args.cwd).returncode


def _run_template(runner: str, args, prompt: str) -> int:
    template = _template_for(runner)
    if not template:
        print(
            "ERROR: custom runner requires CINDRA_COMMAND_TEMPLATE.",
            file=sys.stderr,
        )
        return 2
    command = _format_template(template, args, prompt)
    if args.dry_run:
        print(command)
        return 0
    print(f"[command-bus] runner={runner} cwd={args.cwd}", flush=True)
    print(f"[command-bus] command={command}", flush=True)
    return subprocess.run(command, cwd=args.cwd, shell=True).returncode


def _template_for(runner: str) -> str:
    if runner == "claude":
        return os.environ.get("CINDRA_CLAUDE_COMMAND_TEMPLATE", DEFAULT_CLAUDE_TEMPLATE)
    if runner == "codex":
        return os.environ.get("CINDRA_CODEX_COMMAND_TEMPLATE", DEFAULT_CODEX_TEMPLATE)
    return os.environ.get("CINDRA_COMMAND_TEMPLATE", "")


def _format_template(template: str, args, prompt: str) -> str:
    values = {
        "prompt": prompt,
        "prompt_file": str(Path(args.prompt_file).resolve()),
        "mode": args.mode,
        "backend": args.backend,
        "index": args.index,
        "project": args.project,
        "cwd": str(Path(args.cwd).resolve()),
    }
    out = template
    for key, value in values.items():
        out = out.replace("{" + key + "}", value)
        out = out.replace("{" + key + ":q}", _quote(value))
    return out


def _quote(value: str) -> str:
    return subprocess.list2cmdline([value])


def _display_cmd(cmd: list[str]) -> str:
    return subprocess.list2cmdline(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
