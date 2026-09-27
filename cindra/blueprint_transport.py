"""blueprint_transport —— CindraBlueprint 的执行通道, 复刻 transport.py 双后端。

  MockBlueprintTransport  打到内存蓝图图 (Mac 验证用, 还能文本渲染)
  UEBlueprintTransport    通过 UE Python Remote Execution 调引擎里的 bp_*()
                          (那些函数用 C++/Python 操作真 UEdGraph/UK2Node)

两者都暴露 .call(func, **kwargs) -> dict, agent 不关心底下是内存图还是真引擎。
和 CindraChat 一样: mock 证明整条链路对, 接真引擎只换 transport, agent/工具不动。

CindraBlueprint 是四功能里最难、最具护城河的一块, 因为它要在 UE 侧真正操作
BlueprintGraph。下面 UE_BP_HELPER_NOTE 写清了真后端的接法与卡点。
"""

from __future__ import annotations

import json
from typing import Any

from .blueprint_model import BlueprintGraph


class MockBlueprintTransport:
    """Mac 本地后端: 直接打到内存蓝图图。"""

    def __init__(self) -> None:
        self.graph = BlueprintGraph()

    def call(self, func: str, **kwargs: Any) -> dict:
        fn = getattr(self.graph, func, None)
        if fn is None:
            return {"ok": False, "error": f"unknown func: {func}"}
        try:
            return json.loads(fn(**kwargs))
        except Exception as e:  # noqa: BLE001 - 把错误回给 agent 自检
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    def describe_graph(self) -> str:
        return self.graph.render()


# UE 侧真后端的接法说明 (对照 ue_helper.py 的角色)。CindraBlueprint 的真正难点
# 在这里: 必须用 C++ 写一个编辑器插件操作 BlueprintGraph, Python 远程执行只是
# 触发入口。
UE_BP_HELPER_NOTE = """\
# CindraBlueprint 真后端 (UE 侧) 接法

操作 BlueprintGraph 不能只靠 Python —— 核心 API (UEdGraph / UK2Node /
UEdGraphPin / FKismetEditorUtilities) 是 C++ 编辑器模块。真后端需要:

1. 一个编辑器插件 (C++), 暴露几个能被 Python/远程调用的函数:
   - bp_add_node(blueprint_path, node_type, name)
       用 UK2Node_Event / UK2Node_CallFunction / UK2Node_IfThenElse 等
       在目标 Blueprint 的事件图里 SpawnNode, 设好位置。
   - bp_connect(from_node, from_pin, to_node, to_pin)
       取两端 UEdGraphPin, 调 UEdGraphSchema::TryCreateConnection
       (它内部就做方向/类别/类型/单入线校验 —— 和 mock 的校验一一对应)。
   - bp_add_variable / bp_delete_node / bp_list / bp_clear 同理。

2. 关键卡点 (与之前 MCP_BRIDGE.md 记录一致):
   - **GameThread / 编辑器线程**: 图操作必须在主线程, 用 AsyncTask 调度回来。
   - **事务**: 包 FScopedTransaction, Ctrl+Z 能整步撤销。
   - **编译**: 改完图要 FKismetEditorUtilities::CompileBlueprint, 否则不生效。
   - **标脏/保存**: MarkBlueprintAsModified, 让编辑器知道要重编/可保存。
   - **验证闭环**: bp_list 读回真实图结构给 agent 自检, 别"自信地以为连上了"。

3. Python 远程执行只负责把上面 C++ 函数的调用转发进引擎 (同 RemoteExecTransport)。

把这些实现好后, UEBlueprintTransport.call 就和 MockBlueprintTransport.call
对外完全一致, agent 与工具层无需改动。
"""


class UEBlueprintTransport:
    """真 UE 后端: RemoteExecClient + ue_helpers/bp.py 胶水 +
    CindraBlueprintBridge C++ 插件 (UCindraBlueprintLib)。

    首次调用注入 bp 胶水源并跑 bp_probe() 探测插件 —— 没编译/没启用时
    返回可执行的修复指引, 不假装成功。真图操作的实现见
    ue_plugin/CindraEditorPanel/Source/CindraBlueprintBridge/。
    """

    def __init__(self, host: str = "239.0.0.1", port: int = 6766, client=None) -> None:
        from .transport import RemoteExecClient

        self.client = client or RemoteExecClient(host, port)
        self._injected = False
        self._probed = False

    def _ensure(self) -> dict | None:
        """注入胶水 + 探测插件。返回错误 dict 或 None。"""
        import json as _json

        from .ue_helpers import HELPER_MODULES

        if not self._injected:
            self.client.exec(HELPER_MODULES["bp"], mode="ExecuteFile")
            self._injected = True
        if not self._probed:
            raw = self.client.exec("print(bp_probe())")
            probe = _json.loads(raw)
            if not probe.get("ok"):
                return probe
            self._probed = True
        return None

    def call(self, func: str, **kwargs: Any) -> dict:
        import pprint

        try:
            err = self._ensure()
            if err is not None:
                return err
            args = ", ".join(
                f"{k}={pprint.pformat(v, width=120, compact=True)}" for k, v in kwargs.items()
            )
            raw = self.client.exec(f"print({func}({args}))")
            return json.loads(raw)
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    def describe_graph(self) -> str:
        res = self.call("bp_list")
        if not res.get("ok"):
            return f"(无法读取真图: {res.get('error')})"
        return f"真蓝图图: {len(res.get('nodes', []))} 节点, {len(res.get('links', []))} 连线"
