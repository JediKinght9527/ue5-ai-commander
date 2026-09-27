"""工具注册表：把「工具有哪些」和「工具怎么执行」收到一处。

之前这两件事分散在两个地方：`_build_registry()` 登记 schema，`dispatch_tool()`
再用一串 `if name == ...` 重复描述同一份映射。工具一多，两边必然漂移。

现在一条工具 = 一个 `ToolSpec`：

    ToolSpec(
        name="add_pcg_node",
        description="...",
        input_schema={...},
        module="pcg",
        handler=lambda args, state: pcg_tools.dispatch(state.pcg_graph, "add_pcg_node", args),
    )

handler 签名统一为 `(args: dict, state: ServerState) -> dict`，由 `resolve()` 查表调用。
`handler=None` 表示该工具的 schema 已登记但未接线，`resolve()` 会明确报错而不是
悄悄走 unknown tool 分支——这样漏接的工具在自检里立刻暴露。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:  # 避免运行时循环导入
    from .mcp_server import _ServerState

Handler = Callable[[dict, "_ServerState"], dict]


@dataclass(frozen=True)
class ToolSpec:
    """一个 MCP 工具的完整定义：对外暴露的 schema + 内部执行入口。"""

    name: str
    description: str
    input_schema: dict
    module: str
    handler: Handler | None = None

    def to_mcp(self) -> dict:
        """转成 MCP tools/list 里的形状。"""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }


class ToolRegistry:
    """按名字存 ToolSpec，并负责执行时的查表。"""

    def __init__(self) -> None:
        self._specs: dict[str, ToolSpec] = {}
        # 登记过程中发现的同名冲突：(工具名, 被跳过的模块)
        self.conflicts: list[tuple[str, str]] = []

    def add(self, spec: ToolSpec, *, on_conflict: str = "error") -> bool:
        """登记一个工具。返回是否真的登记进去了。

        `on_conflict="skip"` 时，同名工具保留先注册者并把冲突记进 `conflicts`；
        旧实现用 dict 赋值重复键会静默覆盖，导致 tools/list 展示 A 模块的描述
        而实际执行 B 模块的逻辑，所以这里宁可显式暴露冲突。
        """
        if spec.name in self._specs:
            if on_conflict == "skip":
                self.conflicts.append((spec.name, spec.module))
                return False
            raise ValueError(f"工具名重复注册: {spec.name}")
        self._specs[spec.name] = spec
        return True

    def extend(self, specs: list[ToolSpec], *, on_conflict: str = "error") -> None:
        for spec in specs:
            self.add(spec, on_conflict=on_conflict)

    def rebind(self, name: str, handler: Handler) -> None:
        """给已登记的工具换一个 handler，保持 schema / description 不变。

        用于「schema 由模块统一登记，但执行入口特殊」的工具。
        """
        self._specs[name] = replace(self.require(name), handler=handler)

    # ── 查询 ──

    def __contains__(self, name: object) -> bool:
        return name in self._specs

    def __len__(self) -> int:
        return len(self._specs)

    def names(self) -> list[str]:
        return list(self._specs)

    def get(self, name: str) -> ToolSpec | None:
        return self._specs.get(name)

    def require(self, name: str) -> ToolSpec:
        """取已登记的工具, 没有就抛 KeyError。用于内部/自检这种"必然存在"的场景,
        省掉每处 `x = reg.get(n); assert x is not None` 的收窄噪音。"""
        spec = self._specs.get(name)
        if spec is None:
            raise KeyError(f"未登记的工具: {name}")
        return spec

    def module_of(self, name: str) -> str | None:
        spec = self._specs.get(name)
        return spec.module if spec else None

    def to_mcp_list(self) -> list[dict]:
        """MCP tools/list 响应用的工具清单。"""
        return [spec.to_mcp() for spec in self._specs.values()]

    # ── 执行 ──

    def resolve(self, name: str, args: dict, state: _ServerState) -> dict:
        """按名字执行工具。未知工具与未接线工具分别给出可区分的错误。"""
        spec = self._specs.get(name)
        if spec is None:
            return {"ok": False, "error": f"unknown tool: {name}"}
        if spec.handler is None:
            return {
                "ok": False,
                "error": f"tool not wired: {name} (module={spec.module})",
            }
        return spec.handler(args, state)

    def unwired(self) -> list[str]:
        """返回已登记但没有 handler 的工具名，供自检断言用。"""
        return [n for n, s in self._specs.items() if s.handler is None]


def specs_from_tools(
    label: str,
    module_id: str,
    tools: list[dict],
    handler: Handler,
) -> list[ToolSpec]:
    """把某个 `*_tools.py` 里的 `TOOLS: list[dict]` 转成 ToolSpec 列表。

    `*_tools` 模块的 TOOLS 条目只有 name/description/input_schema，
    执行入口统一交给该模块自己的 `dispatch`，所以这里只需要一个 handler。

    对外描述沿用原有格式 `[Label] 原描述`，保证 tools/list 输出逐字不变。
    """
    return [
        ToolSpec(
            name=t["name"],
            description=f"[{label}] {t['description']}",
            input_schema=t["input_schema"],
            module=module_id,
            handler=handler,
        )
        for t in tools
    ]


def _selfcheck() -> int:
    """离线自检: 注册、查表、冲突、未接线的行为。"""

    def ok(msg: str) -> None:
        print(f"✅ {msg}")

    class _Stub:
        """占位 state。注册表本身不碰 state, handler 也不碰 —— 给个真实对象
        比传 None 诚实。用 cast 是因为 _ServerState 只在 TYPE_CHECKING 下可见
        (避免运行时循环导入), 静态检查这里拿不到真类型。"""

        backend = "mock"

    # 1) 注册与查表
    reg = ToolRegistry()
    reg.add(ToolSpec("a", "[X] a", {"type": "object"}, "x", lambda args, s: {"ok": True}))
    assert "a" in reg and len(reg) == 1
    ok("注册与 __contains__")

    # 2) 重名默认报错
    try:
        reg.add(ToolSpec("a", "[Y] a", {"type": "object"}, "y", lambda args, s: {}))
        raise AssertionError("重名应该报错")
    except ValueError:
        ok("重名默认抛错")

    # 3) on_conflict=skip 保留先注册者并记录
    reg.add(
        ToolSpec("a", "[Y] a", {"type": "object"}, "y", lambda args, s: {}),
        on_conflict="skip",
    )
    assert reg.require("a").module == "x", "skip 应该保留先注册者"
    assert reg.conflicts == [("a", "y")]
    ok("skip 保留先注册者并记冲突")

    # 4) rebind 换 handler 但保留 schema
    reg.rebind("a", lambda args, s: {"ok": "rebound"})
    assert reg.require("a").input_schema == {"type": "object"}
    assert reg.resolve("a", {}, cast("_ServerState", _Stub())) == {"ok": "rebound"}
    ok("rebind 保留 schema")

    # 5) rebind 不存在的工具要报错
    try:
        reg.rebind("nope", lambda args, s: {})
        raise AssertionError("rebind 不该成功")
    except KeyError:
        ok("rebind 未知工具抛 KeyError")

    # 6) 未接线工具给出可区分的错误
    reg.add(ToolSpec("loose", "[Z] loose", {"type": "object"}, "z"))
    err = reg.resolve("loose", {}, cast("_ServerState", _Stub()))
    assert err["ok"] is False and "not wired" in err["error"]
    assert reg.unwired() == ["loose"]
    ok("未接线工具报 'not wired' 并可列出")

    # 7) 未知工具
    err = reg.resolve("ghost", {}, cast("_ServerState", _Stub()))
    assert err == {"ok": False, "error": "unknown tool: ghost"}
    ok("未知工具报 'unknown tool'")

    # 8) to_mcp_list 形状
    listed = reg.to_mcp_list()
    assert set(listed[0]) == {"name", "description", "inputSchema"}
    ok("to_mcp_list 输出 MCP 形状")

    # 9) specs_from_tools 描述格式
    specs = specs_from_tools(
        "Chat",
        "chat",
        [{"name": "t1", "description": "做点事", "input_schema": {"type": "object"}}],
        lambda args, s: {},
    )
    assert specs[0].description == "[Chat] 做点事" and specs[0].module == "chat"
    ok("specs_from_tools 保持 [Label] 描述格式")

    print("\nregistry 自检 9/9 通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(_selfcheck())
