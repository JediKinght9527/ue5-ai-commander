"""base_agent —— 四大功能共用的 Claude agent loop。

CindraChat/Docs/Code/Blueprint 的 agent 本来是同一段手写 loop 的复制粘贴。这里把
共享部分收进 CindraAgent 基类, 子类只需声明三件不同的事:
  - SYSTEM_PROMPT : 这个模式的系统提示
  - TOOLS / dispatch : 走哪套工具 (通过 tools_module 传入)
  - _fmt_result  : 怎么把工具结果格式化成一行日志 (可选, 有通用默认)

为什么手写 loop 而非 tool_runner: 我们要在每步打印 agent 在干什么 (可观测)、
把工具结果回喂 (验证闭环)、未来插入权限确认。系统提示 + 工具表打了 prompt
cache 断点, 多轮对话里固定前缀只算一次钱。
"""
from __future__ import annotations

import json

import anthropic

DEFAULT_MODEL = "claude-opus-4-8"


class CindraAgent:
    """所有 Cindra 模式 agent 的基类。子类设 SYSTEM_PROMPT, 传 tools_module。"""

    SYSTEM_PROMPT: str = ""
    MODEL: str = DEFAULT_MODEL
    TOOL_EMOJI: str = "⚙️"   # 工具调用日志前缀, 子类可换 (docs/code 用 🔎)

    def __init__(self, target, tools_module,
                 client: anthropic.Anthropic | None = None,
                 verbose: bool = True) -> None:
        # target: dispatch 的上下文对象 (chat/blueprint 是 transport, docs/code 是 index)
        self.target = target
        self.tools_module = tools_module
        self.client = client or anthropic.Anthropic()
        self.verbose = verbose
        self.messages: list[dict] = []

    def _log(self, *a):
        if self.verbose:
            print(*a)

    def send(self, user_message: str) -> str:
        """处理一条用户消息, 跑完 agentic loop, 返回 agent 最终文本。"""
        self.messages.append({"role": "user", "content": user_message})

        # 工具表 + 系统提示是固定前缀 -> 缓存。断点放在工具表最后一项上。
        tools = [dict(t) for t in self.tools_module.TOOLS]
        tools[-1] = {**tools[-1], "cache_control": {"type": "ephemeral"}}
        system = [{"type": "text", "text": self.SYSTEM_PROMPT,
                   "cache_control": {"type": "ephemeral"}}]

        final_text = ""
        while True:
            resp = self.client.messages.create(
                model=self.MODEL,
                max_tokens=8000,
                thinking={"type": "adaptive"},
                system=system,
                tools=tools,
                messages=self.messages,
            )
            self.messages.append({"role": "assistant", "content": resp.content})

            for block in resp.content:
                if block.type == "text" and block.text.strip():
                    final_text = block.text
                    self._log(f"\n🤖 {block.text.strip()}")

            if resp.stop_reason != "tool_use":
                break

            tool_results = []
            for block in resp.content:
                if block.type != "tool_use":
                    continue
                self._log(f"   {self.TOOL_EMOJI}  {block.name}({_fmt_args(block.input)})")
                result = self.tools_module.dispatch(self.target, block.name, block.input)
                self._log(f"      → {self._fmt_result(result)}")
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": _json(result),
                    "is_error": not result.get("ok", True),
                })
            self.messages.append({"role": "user", "content": tool_results})

        return final_text

    def _fmt_result(self, r: dict) -> str:
        """把工具结果格式化成一行日志。通用默认: 错误标红, 否则简短 JSON。
        子类可覆盖以对特定 action 做更友好的展示。"""
        if not r.get("ok", True):
            return f"❌ {r.get('error')}"
        return _json({k: v for k, v in r.items() if k != "ok"})


def _json(d) -> str:
    return json.dumps(d, ensure_ascii=False)


def _fmt_args(d: dict) -> str:
    return ", ".join(f"{k}={v}" for k, v in d.items())
