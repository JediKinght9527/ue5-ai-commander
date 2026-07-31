# Windows + UE 5.7

## prerequisites

- Windows 10/11
- UE 5.7 editor (Epic Games Launcher)
- Python 3.11+
- Python Remote Execution enabled in the editor

## one-time setup

### 1. enable Python Remote Execution

Edit → Plugins → search Python → enable **Python Editor Script Plugin**. Restart editor.

Edit → Project Settings → Plugins → Python → check **Enable Remote Execution**. Default endpoint `239.0.0.1:6766`. Restart.

### 2. PYTHONPATH

```powershell
$env:PYTHONPATH = "C:\Program Files\Epic Games\UE_5.7\Engine\Plugins\Experimental\PythonScriptPlugin\Content\Python"
```

Add to system env vars for permanent.

### 3. install

```powershell
cd cindra
pip install -r requirements.txt
```

### 4. verify the pipe

UE editor open, level loaded, viewport visible:

```powershell
python check_ue.py
```

All 5 stages pass = ready. The script tells you what's wrong and how to fix each stage.

### 5. API key

```powershell
$env:ANTHROPIC_API_KEY = "sk-ant-..."

# or another provider
$env:CINDRA_MODEL_PROVIDER = "deepseek"
$env:DEEPSEEK_API_KEY = "sk-..."
```

## usage

```powershell
# CLI
python -m cindra.cli --backend ue --once "put 5 cubes in a row"
python -m cindra.cli --backend ue --once "apply horror lighting to the scene"

# MCP: pass _backend: "ue" in tool arguments
```

## known issues

- spawn crashes if viewport is hidden. Keep a visible viewport.
- Ctrl+Z may not undo without `actor.modify()` — handled in ue_helper.py.
- Chinese characters garbled: `chcp 65001`.

## model providers

| provider | env var | default model |
|----------|---------|--------------|
| Anthropic | `ANTHROPIC_API_KEY` | claude-opus-4-8 |
| OpenAI | `OPENAI_API_KEY` + `CINDRA_MODEL` | must set |
| DeepSeek | `DEEPSEEK_API_KEY` | deepseek-v4-flash |
| GLM | `ZAI_API_KEY` | glm-5.1 |
| OpenRouter | `OPENROUTER_API_KEY` | anthropic/claude-sonnet-4.5 |
| SiliconFlow | `SILICONFLOW_API_KEY` | Qwen/Qwen3-Coder-480B |
| Moonshot | `MOONSHOT_API_KEY` | kimi-k2-0711-preview |
| DashScope | `DASHSCOPE_API_KEY` | qwen-max |
| Volcengine | `ARK_API_KEY` | doubao-seed-1-6 |
