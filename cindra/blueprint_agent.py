"""blueprint_agent —— CindraBlueprint 的 Claude agent (搭蓝图事件图)。

共享 loop/helper 在 base_agent.CindraAgent; 这里只声明 CindraBlueprint 特有的系统
提示和工具结果格式化。与 CindraChat 同构: 操作后用 list_graph 读回真实图结构自检。
蓝图连线有严格的方向/类别/类型规则, 自检尤其重要。
"""
from __future__ import annotations

import anthropic

from . import blueprint_tools
from .base_agent import CindraAgent, _json

MODEL = "claude-opus-4-8"

SYSTEM_PROMPT = """你是 CindraBlueprint —— 嵌在 UE5 编辑器里的 AI 蓝图助手。
用户用自然语言描述想要的逻辑, 你用提供的工具在蓝图事件图里加节点、加变量、连引脚
来实现它。

工作方式 (plan the graph before wiring):
- 动手前先用 list_node_types 看清有哪些节点、每个节点的引脚 (名字/方向/类别/类型),
  规划好"哪些节点、怎么连"再调用工具。
- 连线规则 (UE 的硬约束, 违反会被拒): 只能 output->input; 执行流(exec)接 exec
  (then/exec/True/False/Completed...), 数据(data)接同类型 data; 一个输入引脚只能连
  一条线; 一个 exec 输出也只能连一条。先连执行流主干, 再接数据引脚。
- 典型套路: 事件节点(Event_BeginPlay/Tick)的 then 引出执行流, 经 Branch/Sequence/
  Delay 等控制流, 到 PrintString 等动作; 数据用 Greater/Add 等节点算好再喂给 data 引脚。
- 破坏性操作 (clear_graph) 前向用户确认。
- 建图过程中和完成后用 list_graph 读回结构自检, 确认连对了 —— 不要"自信地以为连上了"。

回答简洁。做完用一两句话说清你搭了什么逻辑、关键连线是什么。"""


class CindraBlueprintAgent(CindraAgent):
    SYSTEM_PROMPT = SYSTEM_PROMPT

    def __init__(self, transport, client: anthropic.Anthropic | None = None,
                 verbose: bool = True) -> None:
        super().__init__(transport, blueprint_tools, client=client, verbose=verbose)

    def _fmt_result(self, r: dict) -> str:
        if not r.get("ok", True):
            return f"❌ {r.get('error')}"
        if r.get("action") == "list":
            return f"{len(r.get('nodes', []))} 节点, {len(r.get('links', []))} 连线"
        if r.get("action") == "list_node_types":
            return f"{len(r.get('node_types', {}))} 种节点"
        if r.get("action") == "connect":
            return r.get("link", "connected")
        return _json({k: v for k, v in r.items() if k != "ok"})
