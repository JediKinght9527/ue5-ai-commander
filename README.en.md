[![en](https://img.shields.io/badge/lang-English-blue)](README.en.md)

# cindra — speak to Unreal Engine

Say what you want. The engine does it. No menus, no drag-and-drop.

Works with Claude Code, Cursor, or any MCP client. Mock backend runs on Mac/Linux without UE. Flip to `--backend ue` on Windows when your editor is open.

---

## 30 seconds

```bash
git clone https://github.com/JediKinght9527/cindra.git && cd cindra && pip install -r requirements.txt

# A) Claude Code (MCP) — just say what you want
# Add to claude settings.json mcpServers:
#   "cindra": {"command": "python", "args": ["-m", "cindra.mcp_server"]}
> 生成5棵树围成一圈, 中间放块石头
> 在这片地形上只在平坦区域撒橡树, 斜坡别长树
> BeginPlay 时在屏幕上打印 hello

# B) CLI — five modules, five one-liners
export ANTHROPIC_API_KEY=sk-ant-...
python -m cindra.cli --mode chat      --once "put 5 cubes in a row"
python -m cindra.cli --mode docs      --once "Actor vs Pawn difference"
python -m cindra.cli --mode code      --once "add a dash ability to the character"
python -m cindra.cli --mode blueprint --once "print hello on BeginPlay"
python -m cindra.cli --mode pcg       --once "scatter oak trees, flat ground only, keep it sparse"
```

PCG mode prints an ASCII top-down map showing where every tree landed.

---

## what it does

| module | what | example |
|--------|------|---------|
| **Chat** | edit the scene | "place 10 trees in a circle, a rock in the middle" |
| **Docs** | search the engine | "what's the difference between Actor and Pawn?" |
| **Code** | write C++ | "add a dash ability to the character" |
| **Blueprint** | wire blueprints | "print hello on BeginPlay" |
| **PCG** | procedural generation | "scatter oak trees, flat ground only, skip the slopes" |

All five share one agent loop + mock/real dual backend. Mock runs everywhere. Real UE needs Windows + UE 5.7 editor + Python Remote Execution enabled.

---

## self-checks (no UE, no key, any OS)

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
python -m cindra.mcp_server --selfcheck  # 8/8, 43 tools
```

**103 assertions. All green.** 15 modules. 9 tool domains.

---

## how it works

### mock-first

No UE needed to build or test. Each module has an in-memory mock: scenes as actor hashes, blueprints as graph nodes, PCG as point cloud math, viewport as deterministic PNG renderer. Mock passes → flip transport — same code, real engine.

### act → verify → fix

After each engine action: before/after scene snapshots diff automatically ("you said you spawned a cube — did the count actually go up?"). Tools returning `ok` while nothing changed are caught and fed back as `VERIFY FAILED`. The agent sees screenshots. It can undo.

### 43 MCP tools, 9 domains

Chat (10) · Docs (2) · Code (2) · Blueprint (11) · PCG (9) · Cine (8) · Lighting (1) · Asset (2) · Blockout (5 templates) · PIE (3)

Blueprint T3D injection: templates for common patterns (event→print, branch→dual-print, compare→branch, delayed print) — one call builds an entire sub-graph instead of add-node-connect-repeat.

PIE automation: `launch_pie` → simulate input → `read_pie_log` → fix bugs → repeat. Agent tests its own code.

### 10+ model providers

Anthropic · OpenAI · DeepSeek · GLM/Z.AI · OpenRouter · SiliconFlow · Moonshot/Kimi · DashScope/Qwen · Volcengine/Doubao · any OpenAI-compatible endpoint

---

## real UE connection

Windows + UE 5.7 editor open + Python Remote Execution on:

```powershell
$env:PYTHONPATH = "C:\Program Files\Epic Games\UE_5.7\Engine\Plugins\Experimental\PythonScriptPlugin\Content\Python"
$env:ANTHROPIC_API_KEY = "sk-ant-..."
python -m cindra.cli --backend ue --once "put 5 cubes in a row"

# Or via MCP: pass _backend: "ue" in tool arguments
```

See `WINDOWS_SETUP.md` for details. First run `check_ue.py` to diagnose the pipeline.

---

## files

```
cindra/
├── cli.py              entry point
├── mcp_server.py       43 MCP tools, 9 domains
├── base_agent.py       shared agent loop (pre/post hooks + image feedback)
├── agent.py            scene agent (+ verify hooks)
├── verifier.py         hard diff checker (zero tokens)
├── scene_tools.py      scene tool schemas + dispatch
├── mock_ue.py          in-memory scene backend (+ camera + undo)
├── transport.py        mock / real-UE dual transport
├── ue_helper.py        engine-side Python (remote exec)
├── blockout_builder.py deterministic blockout templates (5 game modes)
├── scene_intent.py     fast path for common Chinese prompts
├── session.py          conversation persistence
├── model_provider.py   10+ LLM provider adapters
├── asset_index.py      project asset search (BM25)
│
├── docs_*.py           doc Q&A (index + agent + tools)
├── code_*.py           C++ generation (project indexer + agent + tools + samples)
├── blueprint_*.py      blueprint editing (graph model + agent + tools + transport)
├── t3d_templates.py    blueprint T3D injection (7 templates)
│
├── pcg_model.py        PCG graph model + executor (19 node types)
├── pcg_tools.py        PCG tool schemas
├── pcg_agent.py        PCG agent (+ verify hooks)
├── pcg_verifier.py     PCG verification layer
├── ue_pcg_helper.py    PCG engine-side helper
├── tripo_pcg_bridge.py Tripo3D text-to-3D → PCG spawn
│
├── pie_tools.py        PIE automation (launch/stop/read log)
├── cine_*.py           cinematic camera (agent + model + tools + transport)
├── lighting_rigs.py    stylistic lighting (5 styles)
├── camera_math.py      3D camera math (orbit/dolly/crane/flyover)
├── mock_viewport.py    deterministic PNG viewport renderer
├── imaging.py          pure-stdlib PNG encoder
├── command_bus.py      portable CLI runner bridge
└── __init__.py
```

---

## vs the field

Cindra's bet: the AI should **do**, not just explain.

| capability | cindra | typical UE AI tool |
|------------|--------|-------------------|
| mock backend (no UE needed) | yes | no |
| verify loop (snapshot diff, zero token) | yes | no (LLM-based visual check) |
| PCG graph from natural language | yes (19 node types) | no (tells you how PCG works) |
| text-to-3D → auto-import → PCG spawn | yes (Tripo bridge) | no |
| automated PIE playtesting | yes | no |
| dual backend (mock/real transparent) | yes | no |
| MCP tools | 43 | varies |
| blueprint T3D injection | 7 templates | varies |

---

## license

MIT
