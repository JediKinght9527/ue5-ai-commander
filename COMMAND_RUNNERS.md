# Command Runners

The UE editor panel calls `command_bus.py`. It routes prompts to one of four runners.

## Runners

| runner | what |
|--------|------|
| `cindra` | Built-in agent (chat/docs/code/blueprint/pcg). Default. |
| `claude` | Claude Code CLI, via configurable command template. |
| `codex` | Codex CLI. |
| `custom` | Any command template. |

## Usage

```powershell
python -m cindra.command_bus --runner cindra --mode chat --backend ue --prompt-file prompt.txt
```

## Templates

For `claude`, `codex`, and `custom` runners, set the command template as an env var:

```powershell
$env:CINDRA_CLAUDE_COMMAND_TEMPLATE = 'claude -p {prompt:q}'
$env:CINDRA_CODEX_COMMAND_TEMPLATE = 'codex exec {prompt:q}'
$env:CINDRA_COMMAND_TEMPLATE = 'my-agent --file {prompt_file:q}'
```

Placeholders: `{prompt}` (raw), `{prompt:q}` (shell-quoted), `{prompt_file}` (file path), `{mode}`, `{backend}`, `{index}`, `{project}`, `{cwd}`.
