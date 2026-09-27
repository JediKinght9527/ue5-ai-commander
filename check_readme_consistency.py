"""校验 README 里的数字与代码实际一致 —— 防止文档再次漂移。

这是本仓库吃过亏的地方: 之前 README 写 43 个工具 / 15 个模块,
实际是 45 / 17, 三个数字互相矛盾。所以把断言做成可执行的。
"""

import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path("/tmp/ue5")
sys.path.insert(0, str(ROOT))

from cindra import mcp_server as m  # noqa: E402

fails: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}{'  ' + detail if detail else ''}")
    if not ok:
        fails.append(label)


# ── 权威数字 ──
n_tools = len(m._registry)
per_module = Counter(s.module for s in m._registry._specs.values())
n_unwired = len(m._registry.unwired())


def counts() -> tuple[int, int, int, int]:
    """一次跑完, 拿到 (模块断言, MCP 断言, 各自总数)。

    只 spawn 两次: 一次全模块、一次 mcp_server。原来逐模块 spawn 43 次要 3 分钟,
    放进 CI 太重。数字仍然来自真实自检输出, 不是写死的。
    """
    a_mod = t_mod = 0
    p = subprocess.run(
        [sys.executable, str(ROOT / "run_selfchecks.py")],
        cwd=ROOT, capture_output=True, text=True, timeout=900,
    )
    hits = re.findall(r"(\d+)/(\d+) assertions across (\d+) modules", p.stdout)
    if hits:
        a_mod, t_mod = int(hits[-1][0]), int(hits[-1][1])

    p2 = subprocess.run(
        [sys.executable, str(ROOT / "run_selfchecks.py"), "mcp_server"],
        cwd=ROOT, capture_output=True, text=True, timeout=600,
    )
    hits2 = re.findall(r"(\d+)/(\d+) assertions", p2.stdout)
    a_mcp, t_mcp = (int(hits2[-1][0]), int(hits2[-1][1])) if hits2 else (0, 0)
    return a_mod, t_mod, a_mcp, t_mcp


a_mod, t_mod, a_mcp, t_mcp = counts()

n_py = len(list((ROOT / "cindra").glob("*.py")))

for readme in ("README.md", "README.en.md"):
    text = (ROOT / readme).read_text()
    check(
        f"{readme}: 工具数 {n_tools}",
        f"**{n_tools} 个 MCP 工具**" in text or f"**{n_tools} MCP tools**" in text,
    )
    check(
        f"{readme}: 无残留的 43/45 旧数字",
        "43 个 MCP 工具" not in text and "43 MCP tools" not in text,
    )
    check(
        f"{readme}: 模块断言数 {a_mod}/{t_mod}",
        f"{a_mod} 条断言" in text or f"{a_mod} assertions" in text,
    )
    check(
        f"{readme}: MCP 断言数 {a_mcp}/{t_mcp}",
        f"{a_mcp} 条断言" in text or f"{a_mcp} assertions" in text,
    )
    check(
        f"{readme}: 声明的模块数 {n_py} 正确", f"{n_py} 个模块" in text or f"{n_py} modules" in text
    )

# 工具清单求和必须等于注册数
zh = (ROOT / "README.md").read_text()
block = re.search(r"## 工具清单\n\n```\n(.*?)```", zh, re.S)
check("README 工具清单存在", block is not None)
if block:
    total = 0
    for line in block.group(1).split("\n"):
        m2 = re.match(r"^(\w+) \((\d+)\)", line.strip())
        if m2:
            total += int(m2.group(2))
    check("工具清单求和 == 注册数", total == n_tools, f"清单 {total} vs 注册 {n_tools}")
    # 清单里列出的模块必须都在注册表里
    listed = {
        m2.group(1).lower()
        for line in block.group(1).split("\n")
        if (m2 := re.match(r"^(\w+) \((\d+)\)", line.strip()))
    }
    check("清单模块 == 注册模块", listed == set(per_module),
          f"清单独有: {listed - set(per_module)} / 注册独有: {set(per_module) - listed}")

check("无未接线工具", n_unwired == 0, str(m._registry.unwired()))
check("README 覆盖全部注册模块", all(x in zh.lower() for x in per_module))

print()
if fails:
    print(f"{len(fails)} 项不一致: " + ", ".join(fails))
    raise SystemExit(1)
print("README 与代码完全一致")
