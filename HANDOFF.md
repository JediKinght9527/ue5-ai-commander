# Cindra — Handoff Document

## What Was Built

Cindra is a natural-language UE5 controller. You describe a scene, shot, or blueprint in plain text; Cindra translates it into UE5 Python Remote Execution calls and optionally captures a screenshot to verify the result.

### Four operating modes

| Mode | Entry point | What it does |
|------|-------------|--------------|
| `chat` (default) | `--mode chat` | Scene building: spawn assets, set materials, lighting |
| `cine` | `--mode cine` | Cinematography: camera rigs, MRQ storyboard renders |
| `blueprint` | `--mode blueprint` | Blueprint authoring via `UCindraBlueprintLib` C++ bridge |
| `mock` | `--backend mock` | Offline self-test, no UE required |

### Repository layout

```
cindra/
  cindra/
    agent/          base_agent.py, session.py, model_provider.py
    ue_helpers/     scene.py, vision.py, assets.py, cine.py, bp.py, __init__.py
    transport.py    RemoteExecClient (UE Python Remote Execution)
    imaging.py      screenshot capture + PIL helpers
    camera_math.py  orbit / dolly / crane math
    asset_index.py  content-browser enumeration + fuzzy search
    cli/main.py     Click CLI entry point
  ue_plugin/
    CindraEditorPanel/   Slate panel (future UI)
    CindraBlueprintBridge/
      Source/
        CindraBlueprintBridge.h / .cpp   module boilerplate
        CindraBlueprintLib.h / .cpp      UCindraBlueprintLib UFunction bridge
  tests/            pytest suite (mock backend, 9/9 green)
  check_ue.py       9-step self-check script
  pyproject.toml
```

## Current State

### What works (mock-verified, 9/9 green)

1. UE connection probe
2. Python helper injection
3. Scene query (`list_actors`)
4. Asset enumeration (`cnd_list_assets`)
5. Asset spawn (`cnd_spawn_asset`)
6. Material assignment (`cnd_set_material`)
7. Screenshot capture (mock viewport → PNG)
8. Camera rig execution (orbit/dolly/crane)
8b. MRQ render trigger
9. Blueprint bridge (`UCindraBlueprintLib` C++ plugin)

### What needs real-UE validation

- All 9 steps above against a live UE 5.7 editor
- `cnd_spawn_asset` path resolution (content-browser paths vary by project)
- MRQ executor: requires saved level + visible viewport
- Blueprint bridge: requires compiled `CindraBlueprintBridge` plugin

### Known rough edges

- `unreal.EditorActorSubsystem` API changed slightly in 5.7; `scene.py` may need minor fixes
- `UCindraBlueprintLib::ExecutePython` uses `IPythonScriptPlugin` — confirm the module loads before calling
- `CindraBlueprintBridge.Build.cs` lists `BlueprintGraph` as a dependency; add `KismetCompiler` if blueprint compilation is needed at runtime
- Merge conflict markers remain in `pyproject.toml` and `tests/test_rules.py` (dataveil repo, not cindra)

## How to Pick Up

### Quickest path to a live demo

```bash
cd /Users/marco/gh-polish/cindra
pip install -e ".[dev]"
python check_ue.py          # confirm 9/9 with UE running
python -m cindra.cli --backend ue --once "搭一个营地场景，加篝火，截图看看"
```

### Next engineering priorities

1. **Real-UE smoke test** — run `check_ue.py` against UE 5.7, fix any API mismatches in `ue_helpers/`
2. **Asset path resolution** — `asset_index.py` enumerates `/Game`; verify paths match `cnd_spawn_asset` expectations
3. **MRQ integration** — test `cine` mode end-to-end; render output lands in `<Project>/Saved/Cindra/renders/`
4. **Blueprint bridge compile** — build `CindraBlueprintBridge` plugin in VS 2022, enable in editor, re-run step 9
5. **Streaming vision loop** — `vision.py` has `watch_viewport`; wire it into the agent's observe step for act→observe→verify

### Model / API key

```bash
export ANTHROPIC_API_KEY=sk-ant-...   # default provider
# or
export CINDRA_MODEL_PROVIDER=deepseek
export DEEPSEEK_API_KEY=sk-...
```

Default model: `[REDACTED]` (set in `model_provider.py`).

## Files to Read First

| File | Why |
|------|-----|
| `cindra/agent/base_agent.py` | Core act→observe→verify loop |
| `cindra/ue_helpers/__init__.py` | Tool registry, lazy injection |
| `cindra/transport.py` | `RemoteExecClient` — UE wire protocol |
| `check_ue.py` | Canonical integration test, read top-to-bottom |
| `WINDOWS_SETUP_5.7.md` | Windows-specific setup and FAQ |
