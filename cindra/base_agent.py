"""base_agent —— 四大功能共用的 agent loop。

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
from typing import Any

from .model_provider import (DEFAULT_ANTHROPIC_MODEL, build_provider,
                             selected_model)

DEFAULT_MODEL = DEFAULT_ANTHROPIC_MODEL


class CindraAgent:
    """所有 Cindra 模式 agent 的基类。子类设 SYSTEM_PROMPT, 传 tools_module。"""

    SYSTEM_PROMPT: str = ""
    MODEL: str = DEFAULT_MODEL
    TOOL_EMOJI: str = "⚙️"   # 工具调用日志前缀, 子类可换 (docs/code 用 🔎)
    # 单次 send 内某工具的调用上限 (视觉闭环要在代码层封顶, 不能只靠提示词)。
    PER_SEND_TOOL_LIMITS: dict[str, int] = {}
    # 对话里最多保留几张历史截图 (更早的替换成文字 stub, 控住上下文成本)
    IMAGE_WINDOW: int = 3

    def __init__(self, target, tools_module,
                 client: Any | None = None,
                 verbose: bool = True) -> None:
        # target: dispatch 的上下文对象 (chat/blueprint 是 transport, docs/code 是 index)
        self.target = target
        self.tools_module = tools_module
        self.client = build_provider(client)
        self.verbose = verbose
        self.messages: list[dict] = []

    def _log(self, *a):
        if self.verbose:
            print(*a)

    def send(self, user_message: str) -> str:
        """处理一条用户消息, 跑完 agentic loop, 返回 agent 最终文本。"""
        self.messages.append({"role": "user", "content": user_message})

        tools = [dict(t) for t in self.tools_module.TOOLS]
        model = selected_model(self.MODEL)

        final_text = ""
        tool_counts: dict[str, int] = {}
        while True:
            self._prune_old_images()
            resp = self.client.create(
                model=model,
                max_tokens=8000,
                system_prompt=self.SYSTEM_PROMPT,
                tools=tools,
                messages=self.messages,
            )
            self.messages.append({
                "role": "assistant",
                "content": [b.to_message_block() for b in resp.content],
            })

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
                limit = self.PER_SEND_TOOL_LIMITS.get(block.name)
                tool_counts[block.name] = tool_counts.get(block.name, 0) + 1
                if limit is not None and tool_counts[block.name] > limit:
                    result = {"ok": False,
                              "error": f"{block.name} 本轮已达上限 {limit} 次, "
                                       "请基于已有信息收尾。"}
                else:
                    result = self.tools_module.dispatch(
                        self.target, block.name, block.input)
                self._log(f"      → {self._fmt_result(result)}")
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": _tool_result_content(result),
                    "is_error": not result.get("ok", True),
                })
            self.messages.append({"role": "user", "content": tool_results})

        return final_text

    def _prune_old_images(self) -> None:
        """只保留最近 IMAGE_WINDOW 张图, 更早的换成文字 stub。"""
        slots = []  # (message, content_list, index)
        for msg in self.messages:
            content = msg.get("content")
            if not isinstance(content, list):
                continue
            for tr in content:
                if not (isinstance(tr, dict) and tr.get("type") == "tool_result"):
                    continue
                inner = tr.get("content")
                if not isinstance(inner, list):
                    continue
                for i, blk in enumerate(inner):
                    if isinstance(blk, dict) and blk.get("type") == "image":
                        slots.append((inner, i))
        for inner, i in slots[:max(0, len(slots) - self.IMAGE_WINDOW)]:
            inner[i] = {"type": "text", "text": "(较早的截图已省略)"}

    def _fmt_result(self, r: dict) -> str:
        """把工具结果格式化成一行日志。通用默认: 错误标红, 否则简短 JSON。
        子类可覆盖以对特定 action 做更友好的展示。"""
        if not r.get("ok", True):
            return f"❌ {r.get('error')}"
        return _json({k: v for k, v in r.items() if k != "ok"})


def _json(d) -> str:
    return json.dumps(d, ensure_ascii=False)


def _tool_result_content(result: dict):
    """工具结果 -> tool_result content。

    约定: dispatch 返回值带 "images": [png路径...] 时, 组装成
    text + image blocks (视觉闭环的入口); 否则保持纯 JSON 字符串。
    图片读盘失败/超限不炸整轮 —— 降级成文字说明, agent 自己决定重拍。
    """
    images = result.get("images")
    if not images:
        return _json(result)
    from .imaging import b64_file

    rest = {k: v for k, v in result.items() if k != "images"}
    blocks: list[dict] = [{"type": "text", "text": _json(rest)}]
    for path in images:
        try:
            blocks.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/png",
                           "data": b64_file(path)},
            })
        except Exception as e:  # noqa: BLE001
            blocks.append({"type": "text",
                           "text": f"(截图读取失败 {path}: {e})"})
    return blocks


def _fmt_args(d: dict) -> str:
    return ", ".join(f"{k}={v}" for k, v in d.items())
