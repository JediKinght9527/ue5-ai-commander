[![中文](https://img.shields.io/badge/lang-%E4%B8%AD%E6%96%87-red)](README.md)

# cindra

A toolset for controlling Unreal Engine 5.7 with natural language. Scene editing, RAG, C++ generation, Blueprints, PCG procedural generation, cinematics, lighting, PIE automation. Works with Claude Code or Cursor via MCP. Mock backend runs on Mac without UE.

---

## install

```bash
git clone https://github.com/JediKinght9527/ue5-ai-commander.git
cd cindra
pip install -r requirements.txt
```

## usage

### MCP (recommended)

Add to Claude Code `settings.json`:

```json
{
  "mcpServers": {
    "cindra": {
      "command": "python",
      "args": ["-m", "cindra.mcp_server"]
    }
  }
}
```

Then just say what you want:

```
> put 10 trees in a circle with a rock in the middle
> scatter oak trees on flat ground only, skip the slopes
> print hello on BeginPlay
```

### CLI

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python -m cindra.cli --mode chat      --once "put 5 cubes in a row"
python -m cindra.cli --mode docs      --once "Actor vs Pawn difference"
python -m cindra.cli --mode code      --once "add a dash ability to the character"
python -m cindra.cli --mode blueprint --once "print hello on BeginPlay"
python -m cindra.cli --mode pcg       --once "scatter oak trees across 500x500, keep it sparse"
```

PCG mode prints an ASCII top-down map showing each spawn point.

### connect to UE 5.7

Windows, editor open, Python Remote Execution enabled:

```powershell
$env:PYTHONPATH = "C:\Program Files\Epic Games\UE_5.7\Engine\Plugins\Experimental\PythonScriptPlugin\Content\Python"
$env:ANTHROPIC_API_KEY = "sk-ant-..."
python -m cindra.cli --backend ue --once "put 5 cubes"
```

For MCP, pass `_backend: "ue"` in the tool arguments. See `WINDOWS_SETUP.md`. Run `check_ue.py` first time.

---

## modules

| module | does | example |
|--------|------|---------|
| Chat | edit scenes | "put 10 trees in a circle, a rock in the middle" |
| Docs | UE Q&A (RAG) | "difference between Actor and Pawn" |
| Code | generate UE C++ | "add a dash ability to the character" |
| Blueprint | wire blueprints | "print hello on BeginPlay" |
| PCG | procedural generation | "scatter oak trees, flat ground only" |

All five share one agent loop + mock/real dual backend.

---

## tools

```
Chat (10)        spawn_actor, spawn_grid, delete_actor, move_actor,
                 set_transform, arrange_scene, inspect_viewport, undo,
                 list_actors, clear_scene

Docs (2)         search_docs, list_topics

Code (2)         search_project, list_symbols

Blueprint (11)   create_blueprint, compile_blueprint, list_node_types,
                 add_node, add_variable, connect_pins, delete_node,
                 list_graph, clear_graph, list_blueprint_templates,
                 inject_blueprint_t3d

PCG (9)          list_pcg_node_types, add_pcg_node, connect_pcg_pins,
                 set_pcg_param, delete_pcg_node, list_pcg_graph,
                 run_pcg_graph, inspect_pcg_result, clear_pcg_graph

Cine (8)         create_sequence, add_cinematic_camera, camera_move,
                 add_camera_cut, render_sequence, review_render,
                 list_sequence, list_actors

Lighting (1)     light_rig (5 styles: horror/golden_hour/studio/
                 night_neon/overcast)

Asset (2)        search_assets, spawn_asset

Blockout (1)     generate_blockout (combat_arena/sniper_alley/
                 choke_point/boss_room/race_track)

PIE (3)          launch_pie, stop_pie, read_pie_log
```

Blueprint T3D injection: `inject_blueprint_t3d` injects entire sub-graphs (BeginPlay→Print, Branch→dual-print, etc.) in one call — 7 templates, no add-node-connect-repeat.

PIE automation: `launch_pie` → `read_pie_log` → fix → repeat.

---

## verification

No UE, no API key, any OS:

```bash
python -m cindra.docs_index          # 10/10
python -m cindra.project_index       #  5/5
python -m cindra.mock_ue             #  6/6
python -m cindra.verifier            #  9/9
python -m cindra.pcg_model           # 10/10
python -m cindra.tripo_pcg_bridge    #  6/6
python -m cindra.session             #  3/3
python -m cindra.asset_index         #  8/8
python -m cindra.camera_math         #  4/4
python -m cindra.cine_model          #  4/4
python -m cindra.imaging             #  3/3
python -m cindra.lighting_rigs       #  4/4
python -m cindra.mock_viewport       #  4/4
python -m cindra.blueprint_model     #  5/5
python -m cindra.t3d_templates       #  6/6
python -m cindra.pie_tools           #  8/8
python -m cindra.mcp_server --selfcheck  # 8/8
```

15 modules, 103 assertions, all passing.

---

## design

### mock-first

Every module has an in-memory mock: scenes as dicts, blueprints as graph nodes, PCG as point cloud math, viewport as PNG renderer. Mock passes → flip transport → same code runs against the real engine.

### verify loop

Before/after scene snapshots are diffed automatically. Silent failures (tool says `ok`, nothing actually changed) are caught and rewritten as `VERIFY FAILED`. Screenshots feed back to the agent. Undo on failure.

### multi-model

Switch via `CINDRA_MODEL_PROVIDER` env var. Supports Anthropic / OpenAI / DeepSeek / GLM / OpenRouter / SiliconFlow / Moonshot / DashScope / Volcengine Ark / any OpenAI-compatible endpoint.

### text-to-3D bridge

Tripo3D integration: prompt → GLB model → auto-import into UE → PCG spawner uses it. `tripo_pcg_bridge.py`. Mock end-to-end verifiable offline.

---

## files

```
cindra/
├── cli.py              entry point
├── mcp_server.py       43 MCP tools
├── base_agent.py       shared agent loop
├── agent.py            scene agent
├── verifier.py         hard diff checker
├── scene_tools.py      scene tools
├── mock_ue.py          in-memory scene
├── transport.py        mock/ue dual backend
├── ue_helper.py        engine-side Python
├── blockout_builder.py blockout templates
├── scene_intent.py     fast path for common prompts
├── session.py          conversation persistence
├── model_provider.py   10+ model adapters
├── asset_index.py      asset search
├── docs_*.py           UE Q&A
├── code_*.py           C++ generation
├── blueprint_*.py      blueprint editing
├── t3d_templates.py    T3D injection
├── pcg_model.py        PCG graph engine (19 nodes)
├── pcg_tools.py        PCG tools
├── pcg_agent.py        PCG agent
├── pcg_verifier.py     PCG verify
├── ue_pcg_helper.py    PCG engine side
├── tripo_pcg_bridge.py Tripo3D bridge
├── pie_tools.py        PIE automation
├── cine_*.py           cinematic camera
├── lighting_rigs.py    stylistic lighting
├── camera_math.py      camera math
├── mock_viewport.py    PNG viewport renderer
├── imaging.py          PNG encoder
├── command_bus.py      CLI runner bridge
└── __init__.py
```

MIT
