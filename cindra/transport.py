"""transport —— 执行通道抽象。

同一套 cnd_*() 调用, 两种后端:
  MockTransport       直接调 mock_ue 里的内存场景 (Mac 验证用)
  RemoteExecTransport 通过 UE Python Remote Execution 把代码发到真引擎执行

两者都暴露 .call(func, **kwargs) -> dict, agent 不关心底下是真是假。
"""
from __future__ import annotations

import json
import pprint
from typing import Any, Protocol

from .mock_ue import MockScene


def _py_literal(value: Any) -> str:
    """把 Python 值转成可嵌进远程代码的字面量 (只用 json, 安全)。"""
    return pprint.pformat(value, width=120, compact=True)


class Transport(Protocol):
    def call(self, func: str, **kwargs: Any) -> dict: ...


class MockTransport:
    """Mac 本地后端: 直接打到内存场景。"""

    def __init__(self) -> None:
        self.scene = MockScene()

    def call(self, func: str, **kwargs: Any) -> dict:
        fn = getattr(self.scene, func, None)
        if fn is None:
            return {"ok": False, "error": f"unknown func: {func}"}
        try:
            return json.loads(fn(**kwargs))
        except Exception as e:  # noqa: BLE001 - 把错误回给 agent 自检
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    def describe_scene(self) -> str:
        return self.scene.render_topdown()


class RemoteExecTransport:
    """真 UE 后端: 通过 Python Remote Execution 发送代码。

    UE 侧需开启 Python 插件的 Remote Execution (见 README)。首次调用会把
    ue_helper 的 cnd_*() 定义注入引擎, 之后每次只发一行函数调用。

    依赖 UE 自带的 `remote_execution` 模块 (引擎里有, 也可单独 pip 安装兼容实现)。
    这里做成惰性导入, 没装 UE 的机器 import cindra 其它部分不受影响。
    """

    def __init__(self, host: str = "239.0.0.1", port: int = 6766) -> None:
        self.host = host
        self.port = port
        self._conn = None
        self._bootstrapped = False

    def _ensure(self):
        if self._conn is not None:
            return
        try:
            import remote_execution as re  # UE 自带 / 兼容实现
        except ImportError as e:  # noqa
            raise RuntimeError(
                "缺少 remote_execution 模块。这需要在装了 UE 的机器上, "
                "用引擎自带的 remote_execution.py (见 README 的 Windows 接法)。"
            ) from e
        cfg = re.RemoteExecutionConfig()
        conn = re.RemoteExecution(cfg)
        conn.start()
        # 连第一个广播自己的引擎节点
        import time
        for _ in range(50):
            if conn.remote_nodes:
                break
            time.sleep(0.1)
        if not conn.remote_nodes:
            conn.stop()
            raise RuntimeError("没发现 UE 节点。确认编辑器开着且 Remote Execution 已启用。")
        conn.open_command_connection(conn.remote_nodes[0]["node_id"])
        self._conn = conn

    def _exec(self, code: str, mode: str = "ExecuteStatement") -> str:
        self._ensure()
        res = self._conn.run_command(
            code, unattended=True,
            exec_mode=mode)  # 'remote_execution' 的执行模式
        if not res or not res.get("success"):
            raise RuntimeError(f"远程执行失败: {res}")
        # 引擎里函数 return 的 JSON 在 output 里; 取最后一行非空输出
        out = res.get("output") or []
        for entry in reversed(out):
            txt = entry.get("output", "").strip()
            if txt:
                return txt
        return "{}"

    def call(self, func: str, **kwargs: Any) -> dict:
        from .ue_helper import UE_HELPER_SOURCE
        try:
            if not self._bootstrapped:
                # 多行函数定义必须用 ExecuteFile 整段执行; ExecuteStatement 只吃
                # 单条语句, 注入这一大段 helper 会失败 (Windows 首次跑常见坑)。
                self._exec(UE_HELPER_SOURCE, mode="ExecuteFile")
                self._bootstrapped = True
            args = ", ".join(f"{k}={_py_literal(v)}" for k, v in kwargs.items())
            # print 出来, 远程执行才能把返回值带回 output
            line = f"print({func}({args}))"
            raw = self._exec(line)  # 单行调用用默认 ExecuteStatement
            return json.loads(raw)
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    def describe_scene(self) -> str:
        res = self.call("cnd_list")
        actors = res.get("actors", [])
        return f"场景里 {len(actors)} 个 Actor: " + ", ".join(
            a["name"] for a in actors) if actors else "(空场景)"
