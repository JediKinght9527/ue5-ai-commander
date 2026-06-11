"""model_provider —— Cindra agent 的模型调用适配层。

内部 agent loop 只认识一种规范化的 text/tool_use 结构。这里把 Anthropic
Messages API 和 OpenAI-compatible Chat Completions 都适配成这套结构, 让
DeepSeek/GLM/OpenAI 这类兼容接口可以共用同一套 Cindra 工具循环。
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Any
from urllib import request, error


DEFAULT_ANTHROPIC_MODEL = "claude-opus-4-8"
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-flash"
DEFAULT_GLM_MODEL = "glm-5.1"
DEFAULT_OPENROUTER_MODEL = "anthropic/claude-sonnet-4.5"
DEFAULT_SILICONFLOW_MODEL = "Qwen/Qwen3-Coder-480B-A35B-Instruct"
DEFAULT_MOONSHOT_MODEL = "kimi-k2-0711-preview"
DEFAULT_DASHSCOPE_MODEL = "qwen-max"
DEFAULT_ARK_MODEL = "doubao-seed-1-6"


@dataclass
class ModelBlock:
    type: str
    text: str = ""
    id: str = ""
    name: str = ""
    input: dict[str, Any] | None = None

    def to_message_block(self) -> dict[str, Any]:
        if self.type == "text":
            return {"type": "text", "text": self.text}
        if self.type == "tool_use":
            return {
                "type": "tool_use",
                "id": self.id,
                "name": self.name,
                "input": self.input or {},
            }
        raise ValueError(f"unknown block type: {self.type}")


@dataclass
class ModelResponse:
    content: list[ModelBlock]
    stop_reason: str


class AnthropicProvider:
    def __init__(self, client: Any | None = None) -> None:
        if client is None:
            import anthropic
            client = anthropic.Anthropic()
        self.client = client

    def create(self, *, model: str, system_prompt: str, tools: list[dict],
               messages: list[dict], max_tokens: int) -> ModelResponse:
        anthropic_tools = [dict(t) for t in tools]
        if anthropic_tools:
            anthropic_tools[-1] = {
                **anthropic_tools[-1],
                "cache_control": {"type": "ephemeral"},
            }
        system = [{"type": "text", "text": system_prompt,
                   "cache_control": {"type": "ephemeral"}}]
        resp = self.client.messages.create(
            model=model,
            max_tokens=max_tokens,
            thinking={"type": "adaptive"},
            system=system,
            tools=anthropic_tools,
            messages=messages,
        )
        return ModelResponse(
            content=[_anthropic_block_to_model_block(b) for b in resp.content],
            stop_reason=resp.stop_reason,
        )


class OpenAICompatibleProvider:
    def __init__(self, *, provider_name: str, api_key: str, base_url: str,
                 model: str) -> None:
        self.provider_name = provider_name
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model

    def create(self, *, model: str, system_prompt: str, tools: list[dict],
               messages: list[dict], max_tokens: int) -> ModelResponse:
        payload = {
            "model": self.model or model,
            "messages": _to_openai_messages(system_prompt, messages),
            "tools": [_to_openai_tool(t) for t in tools],
            "tool_choice": "auto",
            "max_tokens": max_tokens,
            "stream": False,
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = request.Request(
            f"{self.base_url}/chat/completions",
            data=data,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with request.urlopen(req, timeout=120) as resp:
                raw = resp.read().decode("utf-8")
        except error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"{self.provider_name} chat completion failed: "
                f"HTTP {e.code}: {detail}"
            ) from e
        except error.URLError as e:
            raise RuntimeError(
                f"{self.provider_name} chat completion failed: {e}"
            ) from e

        obj = json.loads(raw)
        choice = obj["choices"][0]
        msg = choice.get("message") or {}
        blocks: list[ModelBlock] = []
        content = msg.get("content")
        if isinstance(content, str) and content.strip():
            blocks.append(ModelBlock(type="text", text=content))
        for call in msg.get("tool_calls") or []:
            fn = call.get("function") or {}
            args = fn.get("arguments") or "{}"
            try:
                parsed_args = json.loads(args) if isinstance(args, str) else args
            except json.JSONDecodeError:
                parsed_args = {"_raw_arguments": args}
            blocks.append(ModelBlock(
                type="tool_use",
                id=call.get("id", ""),
                name=fn.get("name", ""),
                input=parsed_args if isinstance(parsed_args, dict) else {},
            ))
        finish = choice.get("finish_reason")
        stop_reason = "tool_use" if msg.get("tool_calls") or finish == "tool_calls" else "end_turn"
        return ModelResponse(content=blocks, stop_reason=stop_reason)


def build_provider(client: Any | None = None) -> Any:
    provider = provider_name()
    if provider == "anthropic":
        return AnthropicProvider(client)

    api_key = _api_key_for(provider)
    model = _model_for(provider)
    base_url = _base_url_for(provider)
    if not api_key:
        raise RuntimeError(config_error() or f"{provider} API key missing")
    if not model:
        raise RuntimeError(config_error() or f"{provider} model missing")
    return OpenAICompatibleProvider(
        provider_name=provider,
        api_key=api_key,
        base_url=base_url,
        model=model,
    )


def provider_name() -> str:
    explicit = (os.environ.get("CINDRA_MODEL_PROVIDER")
                or os.environ.get("CINDRA_PROVIDER"))
    if explicit:
        return _normalize_provider(explicit)
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.environ.get("DEEPSEEK_API_KEY"):
        return "deepseek"
    if (os.environ.get("ZAI_API_KEY") or os.environ.get("GLM_API_KEY")
            or os.environ.get("BIGMODEL_API_KEY")):
        return "glm"
    if os.environ.get("OPENROUTER_API_KEY"):
        return "openrouter"
    if os.environ.get("SILICONFLOW_API_KEY"):
        return "siliconflow"
    if os.environ.get("MOONSHOT_API_KEY"):
        return "moonshot"
    if os.environ.get("DASHSCOPE_API_KEY"):
        return "dashscope"
    if os.environ.get("ARK_API_KEY"):
        return "ark"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    return "anthropic"


def selected_model(default_model: str = DEFAULT_ANTHROPIC_MODEL) -> str:
    provider = provider_name()
    if provider == "anthropic":
        return os.environ.get("CINDRA_MODEL") or os.environ.get("ANTHROPIC_MODEL") or default_model
    return _model_for(provider) or default_model


def config_error() -> str | None:
    provider = provider_name()
    if provider == "anthropic":
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return ("请先设置 ANTHROPIC_API_KEY, 或设置 CINDRA_MODEL_PROVIDER="
                    "deepseek/glm/openrouter/siliconflow/moonshot/"
                    "dashscope/ark/openai 并提供对应 API key。")
        return None

    if not _api_key_for(provider):
        names = {
            "openai": "OPENAI_API_KEY 或 CINDRA_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY 或 CINDRA_API_KEY",
            "glm": "ZAI_API_KEY / GLM_API_KEY / BIGMODEL_API_KEY 或 CINDRA_API_KEY",
            "openrouter": "OPENROUTER_API_KEY 或 CINDRA_API_KEY",
            "siliconflow": "SILICONFLOW_API_KEY 或 CINDRA_API_KEY",
            "moonshot": "MOONSHOT_API_KEY 或 CINDRA_API_KEY",
            "dashscope": "DASHSCOPE_API_KEY 或 CINDRA_API_KEY",
            "ark": "ARK_API_KEY 或 CINDRA_API_KEY",
        }
        return f"请先设置 {names.get(provider, 'CINDRA_API_KEY')}。"
    if not _model_for(provider):
        return ("请设置 CINDRA_MODEL 指定 OpenAI-compatible 模型名 "
                "(例如 OpenAI/Codex 账号可用的模型 id)。")
    return None


def _normalize_provider(value: str) -> str:
    v = value.strip().lower()
    aliases = {
        "claude": "anthropic",
        "anthropic": "anthropic",
        "openai": "openai",
        "codex": "openai",
        "deepseek": "deepseek",
        "zai": "glm",
        "z.ai": "glm",
        "glm": "glm",
        "bigmodel": "glm",
        "zhipu": "glm",
        "openrouter": "openrouter",
        "siliconflow": "siliconflow",
        "sf": "siliconflow",
        "moonshot": "moonshot",
        "kimi": "moonshot",
        "dashscope": "dashscope",
        "qwen": "dashscope",
        "aliyun": "dashscope",
        "ark": "ark",
        "volcengine": "ark",
        "doubao": "ark",
    }
    if v not in aliases:
        raise RuntimeError(
            "未知 CINDRA_MODEL_PROVIDER: "
            f"{value} (可选 anthropic/openai/codex/deepseek/glm/"
            "openrouter/siliconflow/moonshot/dashscope/ark)"
        )
    return aliases[v]


def _api_key_for(provider: str) -> str:
    common = os.environ.get("CINDRA_API_KEY")
    if provider == "openai":
        return common or os.environ.get("OPENAI_API_KEY", "")
    if provider == "deepseek":
        return common or os.environ.get("DEEPSEEK_API_KEY", "")
    if provider == "glm":
        return (common or os.environ.get("ZAI_API_KEY", "")
                or os.environ.get("GLM_API_KEY", "")
                or os.environ.get("BIGMODEL_API_KEY", ""))
    if provider == "openrouter":
        return common or os.environ.get("OPENROUTER_API_KEY", "")
    if provider == "siliconflow":
        return common or os.environ.get("SILICONFLOW_API_KEY", "")
    if provider == "moonshot":
        return common or os.environ.get("MOONSHOT_API_KEY", "")
    if provider == "dashscope":
        return common or os.environ.get("DASHSCOPE_API_KEY", "")
    if provider == "ark":
        return common or os.environ.get("ARK_API_KEY", "")
    return ""


def _model_for(provider: str) -> str:
    common = os.environ.get("CINDRA_MODEL")
    if provider == "openai":
        return common or os.environ.get("OPENAI_MODEL", "")
    if provider == "deepseek":
        return common or os.environ.get("DEEPSEEK_MODEL", DEFAULT_DEEPSEEK_MODEL)
    if provider == "glm":
        return (common or os.environ.get("ZAI_MODEL", "")
                or os.environ.get("GLM_MODEL", DEFAULT_GLM_MODEL))
    if provider == "openrouter":
        return common or os.environ.get("OPENROUTER_MODEL", DEFAULT_OPENROUTER_MODEL)
    if provider == "siliconflow":
        return common or os.environ.get("SILICONFLOW_MODEL", DEFAULT_SILICONFLOW_MODEL)
    if provider == "moonshot":
        return common or os.environ.get("MOONSHOT_MODEL", DEFAULT_MOONSHOT_MODEL)
    if provider == "dashscope":
        return common or os.environ.get("DASHSCOPE_MODEL", DEFAULT_DASHSCOPE_MODEL)
    if provider == "ark":
        return common or os.environ.get("ARK_MODEL", DEFAULT_ARK_MODEL)
    return common or DEFAULT_ANTHROPIC_MODEL


def _base_url_for(provider: str) -> str:
    common = os.environ.get("CINDRA_BASE_URL")
    if provider == "openai":
        return common or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    if provider == "deepseek":
        return common or os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    if provider == "glm":
        if common:
            return common
        if os.environ.get("BIGMODEL_API_KEY") and not os.environ.get("ZAI_API_KEY"):
            return os.environ.get("BIGMODEL_BASE_URL",
                                  "https://open.bigmodel.cn/api/paas/v4")
        return (os.environ.get("ZAI_BASE_URL", "")
                or os.environ.get("GLM_BASE_URL", "")
                or os.environ.get("BIGMODEL_BASE_URL", "")
                or "https://api.z.ai/api/paas/v4")
    if provider == "openrouter":
        return common or os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    if provider == "siliconflow":
        return common or os.environ.get("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
    if provider == "moonshot":
        return common or os.environ.get("MOONSHOT_BASE_URL", "https://api.moonshot.cn/v1")
    if provider == "dashscope":
        return common or os.environ.get("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    if provider == "ark":
        return common or os.environ.get("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
    return common or ""


def _anthropic_block_to_model_block(block: Any) -> ModelBlock:
    btype = getattr(block, "type", None) or block.get("type")
    if btype == "text":
        return ModelBlock(type="text", text=getattr(block, "text", None) or block.get("text", ""))
    if btype == "tool_use":
        return ModelBlock(
            type="tool_use",
            id=getattr(block, "id", None) or block.get("id", ""),
            name=getattr(block, "name", None) or block.get("name", ""),
            input=getattr(block, "input", None) or block.get("input", {}),
        )
    return ModelBlock(type="text", text=str(block))


def _to_openai_tool(tool: dict) -> dict:
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool.get("description", ""),
            "parameters": tool.get("input_schema") or {
                "type": "object",
                "properties": {},
            },
        },
    }


def _to_openai_messages(system_prompt: str, messages: list[dict]) -> list[dict]:
    out = [{"role": "system", "content": system_prompt}]
    for msg in messages:
        role = msg["role"]
        content = msg.get("content")
        if isinstance(content, str):
            out.append({"role": role, "content": content})
            continue
        if role == "assistant":
            text_parts = []
            tool_calls = []
            for block in content or []:
                if block.get("type") == "text" and block.get("text"):
                    text_parts.append(block["text"])
                elif block.get("type") == "tool_use":
                    tool_calls.append({
                        "id": block["id"],
                        "type": "function",
                        "function": {
                            "name": block["name"],
                            "arguments": json.dumps(block.get("input") or {},
                                                    ensure_ascii=False),
                        },
                    })
            item: dict[str, Any] = {
                "role": "assistant",
                "content": "\n".join(text_parts) if text_parts else None,
            }
            if tool_calls:
                item["tool_calls"] = tool_calls
            out.append(item)
            continue
        for block in content or []:
            if block.get("type") == "tool_result":
                out.append({
                    "role": "tool",
                    "tool_call_id": block["tool_use_id"],
                    "content": block.get("content", ""),
                })
    return out
