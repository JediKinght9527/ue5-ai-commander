# Command Runners

Cindra has a stable command boundary for editor integrations:

```powershell
python -m cindra.command_bus --runner cindra --backend ue --prompt-file prompt.txt
```

The UE panel calls `cindra.command_bus`. The command bus then routes the prompt
to one of these runners:

| Runner | Purpose |
|---|---|
| `cindra` | Built-in Cindra scene/docs/code/blueprint agent. |
| `claude` | External Claude Code CLI through a command template. |
| `codex` | External Codex CLI through a command template. |
| `custom` | Any command-line agent you provide. |

## Built-In Runner

```powershell
python -m cindra.command_bus --runner cindra --mode chat --backend ue --prompt-file prompt.txt
```

This is the default. It keeps using Cindra's direct scene commands and model
provider layer.

## Claude Code Runner

Set a command template if your Claude Code CLI flags differ:

```powershell
$env:CINDRA_CLAUDE_COMMAND_TEMPLATE = 'claude -p {prompt:q}'
python -m cindra.command_bus --runner claude --prompt-file prompt.txt
```

## Codex Runner

Set a command template if your Codex CLI flags differ:

```powershell
$env:CINDRA_CODEX_COMMAND_TEMPLATE = 'codex exec {prompt:q}'
python -m cindra.command_bus --runner codex --prompt-file prompt.txt
```

## Custom Runner

```powershell
$env:CINDRA_COMMAND_TEMPLATE = 'my-agent --file {prompt_file:q}'
python -m cindra.command_bus --runner custom --prompt-file prompt.txt
```

Available placeholders:

| Placeholder | Meaning |
|---|---|
| `{prompt}` / `{prompt:q}` | Prompt text, raw or shell-quoted. |
| `{prompt_file}` / `{prompt_file:q}` | Prompt file path, raw or shell-quoted. |
| `{mode}` | `chat`, `docs`, `code`, or `blueprint`. |
| `{backend}` | `mock` or `ue`. |
| `{index}` | Docs index mode. |
| `{project}` | Project root passed to code mode. |
| `{cwd}` | Working directory used by the bus. |

## UE Panel

The panel has a `runner` field. Use:

```text
cindra
claude
codex
custom
```

Changing the runner does not require recompiling the UE plugin. For CLI tools
that change their arguments over time, update only the environment template.
