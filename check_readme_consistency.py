"""校验文档里的数字与代码实际一致 —— 防止文档再次漂移。

这是本仓库吃过亏的地方: 之前 README 写 43 个工具 / 清单求和 49 / 实际 45,
三个数字互相矛盾。所以把断言做成可执行的, 且覆盖全部文档而不只是 README ——
后来 marketing-post.md 里也漂移出同样的旧数字。
"""

import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent  # 仓库根目录, 不能硬编码本地路径
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

# 覆盖所有对读者宣称数字的文档。CHANGELOG 记的是历史, 不参与一致性校验。
DOCS = ["README.md", "README.en.md", "COMMAND_RUNNERS.md",
        "WINDOWS_SETUP.md", "docs/marketing-post.md"]

# 规则: 文档"声明了某个数字"就必须是对的; 没声明的不算错。
# COMMAND_RUNNERS / WINDOWS_SETUP 这类专题文档本来就不必复述总数,
# 硬要求它们写全反而会逼出一堆无意义的重复数字。
STALE = {
    "tools": ("43 个 MCP 工具", "43 MCP tools", "43 tools", "45 个 MCP 工具"),
    "modules": ("15 个模块", "15 modules"),
    "assertions": ("103 条断言", "103 offline assertions", "103 self-checks"),
    "domains": ("9 domains", "9 个域"),
}

for doc in DOCS:
    text = (ROOT / doc).read_text()
    # 陈旧数字: 任何文档里都不许出现
    for _kind, olds in STALE.items():
        for old in olds:
            check(f"{doc}: 无陈旧的 {old!r}", old not in text)

    # 声明了就必须对得上
    if "MCP 工具" in text or "MCP tools" in text or "tools across" in text:
        nums = {int(x) for x in re.findall(r"(\d+) (?:个 )?MCP 工具|(\d+) MCP tools|(\d+) tools", text) for x in x if x}
        check(f"{doc}: 提到的工具数 {sorted(nums)} 正确", not nums or nums == {n_tools})
    if "条断言" in text or "offline assertions" in text or "self-checks" in text:
        nums = {int(x) for x in re.findall(r"(\d+) 条断言|(\d+) offline assertions|(\d+) self-checks", text) for x in x if x}
        demo_a, demo_t = 3, 3  # cindra.demo --check 的 3 条
        legal_a = {a_mod, t_mod, a_mcp, t_mcp, demo_t, a_mod + t_mcp,
                   a_mod + t_mcp + demo_t, t_mod + t_mcp,
                   a_mod + a_mcp + demo_t, t_mod + t_mcp + demo_t}
        check(f"{doc}: 提到的断言数 {sorted(nums)} 正确", not nums or nums <= legal_a)
    if "个模块" in text or "modules" in text:
        nums = {int(x) for x in re.findall(r"(\d+) 个模块|(\d+) modules", text) for x in x if x}
        from run_selfchecks import MODULES  # 自检覆盖的模块清单
        legal_m = {n_py, len(MODULES)}  # py 文件数 / 自检模块数
        check(f"{doc}: 提到的模块数 {sorted(nums)} 正确", not nums or nums <= legal_m)
    if "domains" in text or "个域" in text:
        nums = {int(x) for x in re.findall(r"(\d+) domains|(\d+) 个域", text) for x in x if x}
        check(f"{doc}: 提到的域数 {sorted(nums)} 正确", not nums or nums == {len(per_module)})

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
