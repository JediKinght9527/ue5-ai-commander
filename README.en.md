[![中文](https://img.shields.io/badge/lang-%E4%B8%AD%E6%96%87-red)](README.md)

# cindra — talk to UE5

**cindra** lets you control Unreal Engine 5 with words.

Say what you want. UE5 does it. No menus, no drag-and-drop, no API memorization.

---

## five modules

| module | one-liner | try it |
|--------|-----------|--------|
| **Chat** | edit the scene | "place 10 trees in a circle with a rock in the middle" |
| **Docs** | ask about the engine | "what's the difference between Actor and Pawn?" |
| **Code** | write C++ | "add a dash ability to the character" |
| **Blueprint** | wire up blueprints | "print hello on BeginPlay" |
| **PCG** 🆕 | procedural generation | "scatter oak trees on flat ground only, skip the slopes" |

---

## quick start

```bash
git clone https://github.com/JediKinght9527/cindra.git
cd cindra
pip install -r requirements.txt

# self-checks — no UE, no API key, any OS
python -m cindra.docs_index          # doc search 10/10
python -m cindra.project_index       # symbol index 5/5
python -m cindra.mock_ue             # scene ops 4/4
python -m cindra.verifier            # verify loop 9/9
python -m cindra.pcg_model           # PCG graph 10/10
python -m cindra.tripo_pcg_bridge    # Tripo bridge 6/6

# set your key and go
export ANTHROPIC_API_KEY=sk-ant-...

python -m cindra.cli --mode chat      --once "put 5 cubes in a row"
python -m cindra.cli --mode docs      --once "difference between Actor and Pawn in UE"
python -m cindra.cli --mode code      --once "add a dash ability to the character"
python -m cindra.cli --mode blueprint --once "print hello on BeginPlay"
python -m cindra.cli --mode pcg       --once "scatter oak trees across a 500x500 area, keep it sparse"
```

PCG mode prints an ASCII top-down map so you can literally see where the trees landed.

---

## connecting to the real engine

Windows + UE5. Add `--backend ue`:

```powershell
$env:PYTHONPATH = "C:\Program Files\Epic Games\UE_5.7\Engine\Plugins\Experimental\PythonScriptPlugin\Content\Python"
$env:ANTHROPIC_API_KEY = "sk-ant-..."
python -m cindra.cli --backend ue --once "put 5 cubes in a row"
```

UE5 editor needs to be running with Python Remote Execution turned on. Full setup in `WINDOWS_SETUP.md`.

---

## how it works

### mock-first

You don't need UE5 running to write or test. Every module has an in-memory mock: scenes are actor hashes, blueprints are graph nodes, PCG is point cloud math. When the mock passes, flip transport to `RemoteExecTransport` — same code, real engine.

### act, look, fix

After every engine action:
- snapshots before and after. An automatic diff checks "did that spawn actually happen?" Catches silent failures where the tool says `ok` but nothing changed on screen.
- screenshots feed back to the AI. The model sees the viewport itself — no human in the loop guessing whether it worked.
- undo works. Every operation wraps an editor transaction.

### hands and eyes, not a mouth

UE 5.7 ships with an AI assistant that answers questions and generates code. cindra takes a different bet: it actually does the thing. Build the graph. Compute the points. Spawn the actors. Inspect the result. Fix what's off. PCG is where this lands hardest — the official assistant tells you how PCG works; cindra builds and runs your PCG graph for you.

---

## file map

```
cindra/
├── cli.py              entry point
├── base_agent.py       shared conversation loop
├── agent.py            scene agent (+ verify hooks)
├── scene_tools.py      scene tool definitions
├── mock_ue.py          in-memory scene backend
├── transport.py        mock / real-UE dual transport
├── ue_helper.py        engine-side Python (remote exec)
├── verifier.py         hard diff checker
│
├── docs_*.py           doc Q&A (index + agent + tools)
├── code_*.py           C++ generation (project indexer + agent + tools + samples)
├── blueprint_*.py      blueprint editing (graph model + agent + tools + transport)
│
├── pcg_model.py        PCG graph model + executor 🆕
├── pcg_tools.py        PCG tool schemas 🆕
├── pcg_agent.py        PCG agent (+ verify hooks) 🆕
├── pcg_verifier.py     PCG verification layer 🆕
├── ue_pcg_helper.py    PCG engine-side helper 🆕
└── tripo_pcg_bridge.py Tripo3D bridge (text-to-3D → PCG spawn) 🆕
```

---

## license

MIT
