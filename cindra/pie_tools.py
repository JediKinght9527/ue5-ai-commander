"""pie_tools —— PIE (Play-In-Editor) 自动化工具。

Cindra "手和眼"的运行时延伸: agent 不仅能生成代码/蓝图, 还能自己启动游戏、
模拟输入、读日志、发现错误、修正后重跑。这是 Autonomix 的差异化功能,
Cindra 做简洁版 —— mock 端全链路可验证。

三个工具:
  launch_pie    — 启动 PIE (mock: 模拟日志; 真 UE: console command)
  stop_pie      — 停止 PIE
  read_pie_log  — 读最近 N 行 PIE 日志 (mock: 从 scene 状态生成; 真 UE: Saved/Logs)

自检: python3 -m cindra.pie_tools
"""
from __future__ import annotations

import json
from typing import Any

TOOLS: list[dict] = [
    {
        "name": "launch_pie",
        "description": "启动 Play-In-Editor (模拟运行游戏)。mock 后端模拟启动并生成模拟日志; "
                       "真 UE 端实际启动 PIE 会话。启动后应用 read_pie_log 读日志检查错误。",
        "input_schema": {
            "type": "object",
            "properties": {
                "play_mode": {
                    "type": "string",
                    "enum": ["selected_viewport", "new_editor_window", "standalone"],
                    "description": "PIE 模式, 默认 selected_viewport",
                },
            },
        },
    },
    {
        "name": "stop_pie",
        "description": "停止 PIE 会话。完成测试后清理, 回到编辑模式。",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "read_pie_log",
        "description": "读取 PIE 运行的日志 (最近 N 行)。检查错误/警告, 判断运行是否正常。"
                       "mock 后端基于场景内容模拟真实日志; 真 UE 端读数 Saved/Logs。",
        "input_schema": {
            "type": "object",
            "properties": {
                "n": {"type": "integer", "description": "返回最近多少行, 默认 50"},
                "level": {"type": "string",
                          "enum": ["all", "errors", "warnings", "info"],
                          "description": "日志级别过滤, 默认 all"},
            },
        },
    },
]


# ═══════════════════════════════════════════════════════════════
# mock PIE 后端
# ═══════════════════════════════════════════════════════════════


class MockPIESession:
    """模拟 PIE 运行状态 + 日志。"""

    def __init__(self) -> None:
        self.running: bool = False
        self.logs: list[dict] = []
        self._log_counter: int = 0

    def launch(self, play_mode: str = "selected_viewport") -> dict:
        if self.running:
            return {"ok": False, "error": "PIE 已经在运行中"}
        self.running = True
        self._log_counter += 1
        # 模拟标准 PIE 启动日志
        self.logs = [
            {"seq": self._log_counter, "level": "info",
             "msg": "LogPlayLevel: PIE: Play in editor start (mode={})".format(play_mode)},
            {"seq": self._log_counter + 1, "level": "info",
             "msg": "LogPlayLevel: PIE: World Initialized"},
            {"seq": self._log_counter + 2, "level": "info",
             "msg": "LogGameMode: GameMode initialized with default pawn"},
            {"seq": self._log_counter + 3, "level": "info",
             "msg": "LogPlayLevel: PIE: Server logged in"},
        ]
        self._log_counter += 4
        return {"ok": True, "action": "launch_pie",
                "play_mode": play_mode, "running": True}

    def stop(self) -> dict:
        if not self.running:
            return {"ok": False, "error": "PIE 没有在运行"}
        self.running = False
        self.logs.append({"seq": self._log_counter, "level": "info",
                          "msg": "LogPlayLevel: PIE: Play in editor stop"})
        self._log_counter += 1
        return {"ok": True, "action": "stop_pie", "running": False}

    def read_log(self, n: int = 50, level: str = "all") -> dict:
        # 取最近 n 行
        logs = self.logs[-n:] if n > 0 else list(self.logs)
        # level: "all" / "errors" / "warnings" / "info" — 单复数都接受
        level_map = {"errors": "error", "warnings": "warning", "info": "info"}
        target_level = level_map.get(level, level)
        if target_level != "all":
            logs = [l for l in logs if l["level"] == target_level]
        errors = [l for l in logs if l["level"] == "error"]
        warnings = [l for l in logs if l["level"] == "warning"]
        return {"ok": True, "action": "read_pie_log",
                "running": self.running,
                "total_lines": len(self.logs),
                "returned": len(logs),
                "errors": len(errors),
                "warnings": len(warnings),
                "logs": logs}

    def inject_error(self, msg: str) -> None:
        """给日志注入一条错误 (mock 端模拟运行时错误)。"""
        self.logs.append({"seq": self._log_counter, "level": "error",
                          "msg": f"LogBlueprint: Error: {msg}"})
        self._log_counter += 1

    def inject_warning(self, msg: str) -> None:
        """给日志注入一条警告。"""
        self.logs.append({"seq": self._log_counter, "level": "warning",
                          "msg": f"LogBlueprint: Warning: {msg}"})
        self._log_counter += 1

    def inject_log_from_scene(self, actors: list[dict]) -> None:
        """从 scene 里的 actor 列表生成模拟 PIE 日志。

        模拟真实 UE 运行时的日志: 每个 actor 初始化一行, 蓝图编译警告,
        Tick 速度检查等。用于 mock 端验证 agent "读日志→发现错误→修正" 的闭环。
        """
        # actor 初始化
        for a in actors:
            self.logs.append({
                "seq": self._log_counter, "level": "info",
                "msg": f"LogActor: Spawned {a.get('name', '?')} at "
                       f"{a.get('location', [0, 0, 0])}",
            })
            self._log_counter += 1
        # 模拟蓝图编译结果
        bp_actors = [a for a in actors if a.get("type", "").startswith("asset:")]
        if bp_actors:
            for a in bp_actors:
                self.logs.append({
                    "seq": self._log_counter, "level": "info",
                    "msg": f"LogBlueprint: Compiled {a['name']} (0 errors, 0 warnings)",
                })
                self._log_counter += 1
        # 如果有太多 actor 在同一位置，生成碰撞警告
        positions = {}
        for a in actors:
            k = tuple(int(x / 50) * 50 for x in a.get("location", [0, 0, 0]))
            positions[k] = positions.get(k, 0) + 1
        for k, count in positions.items():
            if count >= 3:
                self.logs.append({
                    "seq": self._log_counter, "level": "warning",
                    "msg": f"LogCollision: Warning: {count} actors overlap near {list(k)}",
                })
                self._log_counter += 1
        # 没有 Pawn → 错误
        has_pawn = any(a.get("type") == "player" or "pawn" in a.get("name", "").lower()
                       for a in actors)
        if not has_pawn:
            self.logs.append({
                "seq": self._log_counter, "level": "error",
                "msg": "LogGameMode: Error: No Player Pawn found. PIE may not function correctly.",
            })
            self._log_counter += 1


# 全局 mock session (dispatch 用)
_mock_pie = MockPIESession()


# ═══════════════════════════════════════════════════════════════
# dispatch
# ═══════════════════════════════════════════════════════════════


def dispatch(transport_or_session, name: str, args: dict[str, Any]) -> dict:
    """执行 PIE 工具调用。

    transport_or_session: MockTransport 或 RemoteExecTransport 或 MockPIESession
    """

    if name == "launch_pie":
        play_mode = args.get("play_mode", "selected_viewport")
        # 检测是 mock 还是真 UE
        if hasattr(transport_or_session, "launch"):
            return transport_or_session.launch(play_mode)
        else:
            # 真 UE: console command
            return transport_or_session.call(
                "cnd_console", cmd="PlayInEditor",
                params={"play_mode": play_mode},
            )

    if name == "stop_pie":
        if hasattr(transport_or_session, "stop"):
            return transport_or_session.stop()
        else:
            return transport_or_session.call("cnd_console", cmd="StopPlayInEditor")

    if name == "read_pie_log":
        n = int(args.get("n", 50))
        level = args.get("level", "all")
        if hasattr(transport_or_session, "read_log"):
            return transport_or_session.read_log(n, level)
        else:
            # 真 UE: 读 Saved/Logs/<Project>.log 最后 N 行
            return transport_or_session.call(
                "cnd_read_log", lines=n, level=level,
            )

    return {"ok": False, "error": f"unknown tool: {name}"}


# ═══════════════════════════════════════════════════════════════
# 预注入 mock PIE 日志 (MCP 端集成用)
# ═══════════════════════════════════════════════════════════════


def get_mock_session() -> MockPIESession:
    return _mock_pie


# ═══════════════════════════════════════════════════════════════
# 自检
# ═══════════════════════════════════════════════════════════════


def _selfcheck() -> int:
    """离线自检: 启动 PIE → 注入错误 → 读日志 → 停止。"""
    s = MockPIESession()

    # 1) 启动
    r = s.launch()
    assert r["ok"] and s.running
    print("✅ launch_pie: PIE 启动, 4 条启动日志")

    # 2) 读日志
    r = s.read_log()
    assert r["ok"] and r["returned"] >= 4
    assert r["errors"] == 0 and r["warnings"] == 0
    print(f"✅ read_pie_log: {r['returned']} 行, 0 错误")

    # 3) 注入错误 + 读
    s.inject_error("Accessed None: PlayerController is null")
    s.inject_error("Blueprint Runtime Error: Divide by zero in BP_Math")
    r = s.read_log()
    assert r["errors"] == 2
    print(f"✅ inject_error: 2 条错误被 read_log 准确计数")

    # 4) 按级别过滤
    r = s.read_log(level="errors")
    assert r["returned"] == 2
    r = s.read_log(level="warnings")
    assert r["returned"] == 0
    print("✅ read_pie_log(level=errors): 只返回 2 条错误, 过滤正确")

    # 5) 停止
    r = s.stop()
    assert r["ok"] and not s.running
    print("✅ stop_pie: PIE 停止")

    # 6) 重复启动 → 拒绝
    r = s.launch()
    assert r["ok"]
    r = s.launch()
    assert not r["ok"] and "已经在运行" in r["error"]
    s.stop()
    print("✅ 重复启动被拒")

    # 7) 空停止 → 拒绝
    r = s.stop()
    assert not r["ok"] and "没有在运行" in r["error"]
    print("✅ 空停止被拒")

    # 8) scene → 模拟日志
    s.launch()
    mock_actors = [
        {"name": "cube_1", "location": [0, 0, 0], "type": "cube"},
        {"name": "cube_2", "location": [50, 0, 0], "type": "cube"},
        {"name": "cube_3", "location": [0, 50, 0], "type": "cube"},
        {"name": "cube_4", "location": [50, 50, 0], "type": "cube"},
        {"name": "cube_5", "location": [25, 25, 0], "type": "cube"},
        {"name": "cube_6", "location": [30, 30, 0], "type": "cube"},
        {"name": "BP_MyActor_1", "location": [200, 200, 0], "type": "asset:/Game/BP_MyActor"},
        {"name": "BP_MyActor_2", "location": [300, 300, 0], "type": "asset:/Game/BP_MyActor"},
    ]
    s.inject_log_from_scene(mock_actors)
    r = s.read_log()
    # 有重叠(6个在25-50区域) → 碰撞警告, 无Pawn → 错误, 2蓝图编译
    assert r["warnings"] >= 1 and r["errors"] >= 1, \
        f"场景模拟日志应有 warning+error: w={r['warnings']} e={r['errors']}"
    print(f"✅ scene→log: {r['total_lines']} 行, {r['warnings']} 警告, {r['errors']} 错误 (模拟真实关卡)")
    s.stop()

    print(f"\nPIE 自检 8/8 通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(_selfcheck())
