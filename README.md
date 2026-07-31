[![en](https://img.shields.io/badge/lang-English-blue)](README.en.md)

# cindra

自然语言控制 Unreal Engine 5.7 的工具集。43 个 MCP 工具，覆盖场景编辑、问答、C++ 生成、蓝图、PCG 程序化生成、运镜、布光、PIE 自动化。支持 Claude Code / Cursor，mock 后端在 Mac 上就能跑，不用开 UE。

---

## 安装

```bash
git clone https://github.com/JediKinght9527/ue5-ai-commander.git
cd cindra
pip install -r requirements.txt
```

## 使用

### MCP（推荐）

在 Claude Code 的 `settings.json` 里加：

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

然后直接说你要干什么就行：

```
> 生成10棵树围成一圈，中间放块石头
> 这块地形上，只在平坦的地方撒橡树，斜坡别长树
> BeginPlay 时打印 hello
```

### CLI

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python -m cindra.cli --mode chat      --once "生成5个cube排一排"
python -m cindra.cli --mode docs      --once "Actor 和 Pawn 什么区别"
python -m cindra.cli --mode code      --once "给角色加一段冲刺逻辑"
python -m cindra.cli --mode blueprint --once "BeginPlay 时打印 hello"
python -m cindra.cli --mode pcg       --once "在500x500区域里撒橡树, 别太密"
```

PCG 跑完会打印 ASCII 俯视图，能看到每个 spawn 点的位置。

### 接 UE 5.7

Windows 上编辑器开着，Python Remote Execution 开启：

```powershell
$env:PYTHONPATH = "C:\Program Files\Epic Games\UE_5.7\Engine\Plugins\Experimental\PythonScriptPlugin\Content\Python"
$env:ANTHROPIC_API_KEY = "sk-ant-..."
python -m cindra.cli --backend ue --once "生成5个cube"
```

MCP 方式在 tool 参数里传 `_backend: "ue"`。详细配置见 `WINDOWS_SETUP.md`。第一次跑用 `check_ue.py` 诊断。

---

## 模块

| 模块 | 做什么 | 例子 |
|------|--------|------|
| Chat | 改场景 | "生成 10 棵树围成圈，中间放块石头" |
| Docs | UE 问答 (RAG) | "Actor 和 Pawn 什么区别" |
| Code | 生成 UE C++ | "给角色加一段冲刺逻辑" |
| Blueprint | 搭蓝图图 | "BeginPlay 时打印 hello" |
| PCG | 程序化生成 | "只在平坦区域撒橡树，斜坡别长" |

五个模块共用同一套 agent loop + mock/real 双后端。

---

## 工具清单

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

Blockout (1)     generate_blockout (5 templates: combat_arena/
                 sniper_alley/choke_point/boss_room/race_track)

PIE (3)          launch_pie, stop_pie, read_pie_log
```

蓝图 T3D 注入：`inject_blueprint_t3d` 直接注入整张子图（BeginPlay→Print、Branch→双路打印等 7 个模板），不用逐节点 add→connect。

PIE 自动化：`launch_pie` → `read_pie_log` → 有错就改 → 重跑。

---

## 验证

不用 UE、不用 API key，任何系统都能跑：

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

15 个模块，103 条断言，全部通过。

---

## 设计

### mock 先行

每个模块在内存里有 mock：场景是 dict，蓝图是图节点，PCG 是点云计算，视口是 PNG 渲染。mock 全绿 → 切 transport → 同一套代码在真 UE 里跑。

### 验证闭环

每次改场景前后拍快照，diff 对账。工具返回 ok 但引擎里没生效的静默失败会被抓出来，改写成 `VERIFY FAILED`。截图回喂给 agent，改坏了 undo。

### 多模型

通过 `CINDRA_MODEL_PROVIDER` 环境变量切换。支持 Anthropic / OpenAI / DeepSeek / GLM / OpenRouter / SiliconFlow / Moonshot / DashScope / Volcengine Ark / 任意 OpenAI 兼容接口。

---

## 文件

```
cindra/
├── cli.py              入口
├── mcp_server.py       43 个 MCP 工具
├── base_agent.py       共享 agent loop
├── agent.py            场景 agent
├── verifier.py          硬校验 (快照 diff)
├── scene_tools.py       场景工具
├── mock_ue.py           内存场景
├── transport.py         mock/ue 双后端
├── ue_helper.py         引擎侧 Python
├── blockout_builder.py  灰盒模板
├── scene_intent.py      常用中文指令优先路径
├── session.py           会话持久化
├── model_provider.py    10+ 模型适配
├── asset_index.py       资产检索
├── docs_*.py            UE 问答
├── code_*.py            生成 C++
├── blueprint_*.py       蓝图编辑
├── t3d_templates.py     T3D 注入模板
├── pcg_model.py         PCG 图引擎 (19 节点)
├── pcg_tools.py         PCG 工具
├── pcg_agent.py         PCG agent
├── pcg_verifier.py      PCG 校验
├── ue_pcg_helper.py     PCG 引擎侧
├── tripo_pcg_bridge.py  Tripo3D 桥接
├── pie_tools.py         PIE 自动化
├── cine_*.py            运镜模式
├── lighting_rigs.py     风格化布光
├── camera_math.py       相机数学
├── mock_viewport.py     PNG 视口渲染
├── imaging.py           PNG 编码
├── command_bus.py       CLI runner 桥
└── __init__.py
```

MIT
