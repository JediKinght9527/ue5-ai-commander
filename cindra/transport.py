"""transport —— 执行通道抽象。

同一套 cnd_*() 调用, 两种后端:
  MockTransport       直接调 mock_ue 里的内存场景 (Mac 验证用)
  RemoteExecTransport 通过 UE Python Remote Execution 把代码发到真引擎执行

两者都暴露 .call(func, **kwargs) -> dict, agent 不关心底下是真是假。

v2: 连接层抽成 RemoteExecClient (蓝图 transport 复用同一条连接逻辑);
注入源按命名空间懒加载 (见 ue_helpers 注册表) —— 首次调到某模块的函数
才注入该模块, 单 blob 变多个小包, 易诊断也不怕撞消息体积上限。
"""
from __future__ import annotations

import json
import pprint
from typing import Any, Protocol

from .mock_ue import MockScene
from .ue_helpers import HELPER_MODULES, module_for


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

    def viewport(self) -> dict:
        """视觉通道 (mock 版): ASCII 俯视图就是"截图"的离线替身。
        让 Mac 上就能全链路验证"agent 亲眼看场景再自我修正"的闭环。"""
        return {"ok": True, "action": "viewport",
                "view": self.scene.render_topdown()}


class RemoteExecClient:
    """UE Python Remote Execution 连接 (供场景/蓝图等多个 transport 复用)。

    依赖 UE 自带的 `remote_execution` 模块 (引擎里有, 也可单独 pip 安装
    兼容实现)。惰性导入, 没装 UE 的机器 import cindra 其它部分不受影响。
    """

    def __init__(self, host: str = "239.0.0.1", port: int = 6766) -> None:
        self.host = host
        self.port = port
        self._conn = None

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
        for _ in range(300):
            if conn.remote_nodes:
                break
            time.sleep(0.1)
        if not conn.remote_nodes:
            conn.stop()
            raise RuntimeError("没发现 UE 节点。确认编辑器开着且 Remote Execution 已启用。")
        conn.open_command_connection(conn.remote_nodes[0]["node_id"])
        self._conn = conn

    def exec(self, code: str, mode: str = "ExecuteStatement") -> str:
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


class RemoteExecTransport:
    """真 UE 后端: 通过 Python Remote Execution 发送代码。

    UE 侧需开启 Python 插件的 Remote Execution (见 README)。首次调用某个
    命名空间 (scene/vision/assets/...) 的函数时注入该命名空间的 cnd_*()
    定义, 之后每次只发一行函数调用。
    """

    def __init__(self, host: str = "239.0.0.1", port: int = 6766,
                 client: RemoteExecClient | None = None) -> None:
        self.client = client or RemoteExecClient(host, port)
        self._injected: set[str] = set()

    def _ensure_module(self, func: str) -> None:
        module = module_for(func)
        if module in self._injected:
            return
        # 多行函数定义必须用 ExecuteFile 整段执行; ExecuteStatement 只吃
        # 单条语句, 注入 helper 段会失败 (Windows 首次跑常见坑)。
        self.client.exec(HELPER_MODULES[module], mode="ExecuteFile")
        self._injected.add(module)

    def call(self, func: str, **kwargs: Any) -> dict:
        try:
            self._ensure_module(func)
            args = ", ".join(f"{k}={_py_literal(v)}" for k, v in kwargs.items())
            # print 出来, 远程执行才能把返回值带回 output
            line = f"print({func}({args}))"
            raw = self.client.exec(line)  # 单行调用用默认 ExecuteStatement
            return json.loads(raw)
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    def describe_scene(self) -> str:
        res = self.call("cnd_list")
        actors = res.get("actors", [])
        return f"场景里 {len(actors)} 个 Actor: " + ", ".join(
            a["name"] for a in actors) if actors else "(空场景)"

    def viewport(self, width: int = 1280, height: int = 720) -> dict:
        """视觉通道 (真 UE 版): 请求视口截图 → 轮询文件落盘 → 返回图片路径。

        cnd_screenshot 是异步的 (引擎在随后数帧末尾写 PNG), 而且截图请求在
        remote exec 里没法阻塞等待 (会卡 GameThread)。所以引擎侧只发起请求,
        这里在 CLI 侧轮询"文件出现 + 大小连续两次一致"才算写完。
        CLI 和 UE 跑在同一台 Windows 上, 所以能直接读到这个文件。
        """
        import os
        import tempfile
        import time
        import uuid
        path = os.path.join(tempfile.gettempdir(),
                            f"cindra_shot_{uuid.uuid4().hex[:8]}.png")
        res = self.call("cnd_screenshot", path=path, width=width, height=height)
        if not res.get("ok"):
            return res
        deadline = time.time() + 10.0
        last_size = -1
        while time.time() < deadline:
            if os.path.exists(path):
                size = os.path.getsize(path)
                if size > 0 and size == last_size:  # 两次采样大小一致 = 写完
                    return {"ok": True, "action": "viewport",
                            "_image_path": path, "size_bytes": size}
                last_size = size
            time.sleep(0.4)
        return {"ok": False, "error":
                "截图超时: 引擎 10s 内没写出文件。已知坑: 视口被藏起来时"
                "不出图 —— 确认编辑器视口可见, 再重试 inspect_viewport。"}
