"""check_ue —— 真 UE 连接分阶段冒烟诊断 (在装了 UE5 的 Windows 上跑)。

不需要 ANTHROPIC_API_KEY。它只验证"Python ↔ UE 引擎"这条管道通不通, 把整条
链路切成 5 个台阶, 撞在哪一阶就知道病因, 不用对着笼统报错抓瞎。

用法 (UE5 编辑器开着, 且已开启 Python Remote Execution):
    python check_ue.py

5 个台阶:
    [1] import remote_execution   —— PYTHONPATH 是否指到引擎自带模块
    [2] 发现 UE 节点              —— 编辑器开着吗? Remote Execution 开了吗?
    [3] 远程执行最简语句          —— 管道双向通吗 (1+1)
    [4] 注入 cnd_*() helper       —— ue_helper 源码在引擎里 import/定义 OK 吗
    [5] 真调 cnd_list / cnd_spawn —— unreal API 真的能 spawn 吗 (会在场景放一个 cube)

每一阶失败都打印具体原因 + 怎么修。全过 = agent 真闭环可以跑。
"""
from __future__ import annotations

import sys
import time


def _fail(stage, msg, fix):
    print(f"\n❌ [{stage}] 失败: {msg}")
    print(f"   怎么修: {fix}")
    return 1


def main() -> int:
    print("=== Cindra 真 UE 连接诊断 ===\n")

    # ---- 台阶 1: import remote_execution ----
    try:
        import remote_execution as re
        print("✅ [1] import remote_execution 成功")
    except ImportError:
        return _fail(
            "1", "找不到 remote_execution 模块",
            "把引擎自带的 remote_execution.py 所在目录加进 PYTHONPATH:\n"
            "   <UE>/Engine/Plugins/Experimental/PythonScriptPlugin/"
            "Content/Python/\n"
            "   例如 PowerShell: $env:PYTHONPATH=\"...\\Python\"")

    # ---- 台阶 2: 发现 UE 节点 ----
    cfg = re.RemoteExecutionConfig()
    conn = re.RemoteExecution(cfg)
    conn.start()
    node = None
    for _ in range(50):
        if conn.remote_nodes:
            node = conn.remote_nodes[0]
            break
        time.sleep(0.1)
    if not node:
        conn.stop()
        return _fail(
            "2", "5 秒内没发现任何 UE 节点",
            "1) 确认 UE5 编辑器正开着;\n"
            "   2) Project Settings → Plugins → Python → 勾 Enable Remote "
            "Execution, 重启编辑器;\n"
            "   3) 防火墙别拦 UDP 多播 (默认 239.0.0.1:6766)。")
    print(f"✅ [2] 发现 UE 节点: {node.get('node_id', '?')[:8]}…")
    conn.open_command_connection(node["node_id"])

    def run(code, mode):
        return conn.run_command(code, unattended=True, exec_mode=mode)

    # ---- 台阶 3: 最简远程执行 ----
    res = run("print(1 + 1)", "ExecuteStatement")
    if not res or not res.get("success"):
        conn.stop()
        return _fail("3", f"远程执行最简语句失败: {res}",
                     "管道握手有问题, 重启编辑器再试; 确认没有别的程序占用连接。")
    print(f"✅ [3] 远程执行通: 1+1 → {_last_output(res)}")

    # ---- 台阶 4: 注入 helper ----
    from cindra.ue_helper import UE_HELPER_SOURCE
    # 多行函数定义注入: 用 ExecuteFile 最稳 (整段当文件执行)
    res = run(UE_HELPER_SOURCE, "ExecuteFile")
    if not res or not res.get("success"):
        conn.stop()
        return _fail(
            "4", f"注入 cnd_*() helper 失败: {res}",
            "看引擎 Output Log 里的 Python 报错。常见: unreal API 名变更、"
            "缩进/编码问题。把报错贴回来我帮你改 ue_helper.py。")
    print("✅ [4] cnd_*() helper 注入成功")

    # ---- 台阶 5: 真调 unreal API ----
    res = run("print(cnd_list())", "ExecuteStatement")
    if not res or not res.get("success"):
        conn.stop()
        return _fail("5a", f"cnd_list() 执行失败: {res}",
                     "EditorActorSubsystem API 可能有变, 看 Output Log 报错。")
    print(f"✅ [5a] cnd_list() 通: {_last_output(res)[:80]}…")

    res = run("print(cnd_spawn(actor_type='cube', location=[0,0,200]))",
              "ExecuteStatement")
    if not res or not res.get("success"):
        conn.stop()
        return _fail("5b", f"cnd_spawn() 执行失败: {res}",
                     "spawn/mesh 加载 API 可能有变, 看 Output Log 报错。")
    print(f"✅ [5b] cnd_spawn() 通: {_last_output(res)}")
    print("       ↑ 现在去编辑器视口看看 —— 应该多了一个 cube。")

    conn.stop()
    print("\n🎉 全部 5 阶通过! 真闭环可以跑:")
    print("   set ANTHROPIC_API_KEY=sk-ant-...")
    print('   python -m cindra.cli --backend ue --once "生成5个cube排成一排"')
    return 0


def _last_output(res) -> str:
    for entry in reversed(res.get("output") or []):
        txt = (entry.get("output") or "").strip()
        if txt:
            return txt
    return "(无输出)"


if __name__ == "__main__":
    raise SystemExit(main())
