#!/usr/bin/env python3
"""跑全���模块的 _selfcheck，汇总断言数。

用法:
    python run_selfchecks.py            # 全部模块
    python run_selfchecks.py pcg_model  # 只跑指定模块

不需要 UE、不需要 API key。任何一个模块失败即退出码非 0，可直接用于 CI。
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# 与 README「验证」一节保持一致的模块顺序
MODULES = [
    "docs_index",
    "project_index",
    "mock_ue",
    "verifier",
    "pcg_model",
    "tripo_pcg_bridge",
    "session",
    "asset_index",
    "camera_math",
    "cine_model",
    "imaging",
    "lighting_rigs",
    "mock_viewport",
    "blueprint_model",
    "t3d_templates",
    "pie_tools",
    "registry",
]

# 这些模块的 selfcheck 入口需要额外参数，不能用 -m 直接调
SPECIAL: dict[str, list[str]] = {
    "mcp_server": ["--selfcheck"],
}

_COUNT_RE = re.compile(r"(\d+)\s*/\s*(\d+)")


def run(module: str) -> tuple[int, int, str]:
    """返回 (通过数, 总数, 输出)。模块自身抛错时总数记 0。"""
    args = SPECIAL.get(module, [])
    cmd = [sys.executable, "-m", f"cindra.{module}", *args]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=180)
    out = proc.stdout + proc.stderr
    passed = total = 0
    for match in _COUNT_RE.finditer(out):
        passed, total = int(match.group(1)), int(match.group(2))
    if proc.returncode != 0:
        return passed, total, out
    return passed, total, out


def main(argv: list[str]) -> int:
    targets = argv[1:] or MODULES
    total_pass = total_all = 0
    failed: list[str] = []
    for module in targets:
        try:
            passed, total, out = run(module)
        except subprocess.TimeoutExpired:
            print(f"  {module:<22} TIMEOUT")
            failed.append(module)
            continue
        if total == 0 or passed != total:
            failed.append(module)
            print(f"  {module:<22} FAIL  {passed}/{total}")
            if out.strip():
                print("\n".join(f"      {ln}" for ln in out.strip().splitlines()[-6:]))
        else:
            total_pass += passed
            total_all += total
            print(f"  {module:<22} ok    {passed}/{total}")
    print(f"\n{total_pass}/{total_all} assertions across {len(targets) - len(failed)} modules")
    if failed:
        print("failed: " + ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
