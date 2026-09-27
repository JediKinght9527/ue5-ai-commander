[![en](https://img.shields.io/badge/lang-English-blue)](README.en.md)
[![CI](https://github.com/JediKinght9527/ue5-ai-commander/actions/workflows/self-check.yml/badge.svg)](https://github.com/JediKinght9527/ue5-ai-commander/actions/workflows/self-check.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-7395be)](https://docs.astral.sh/uv/)
[![License](https://img.shields.io/badge/license-MIT-f0b642)](LICENSE)

# ue5-ai-commander

自然语言控制 Unreal Engine 5.7。**48 个 MCP 工具**：改场景、PCG 程序化生成、搭蓝图、写 C++、UE 问答、运镜、布光、PIE 自动化。支持 Claude Code / Cursor。

**没装 UE 也能跑** —— mock 后端在任何机器上验证整条链路，不需要引擎、不需要 API key。

<p align="center">
  <img src="assets/demo_view.png" width="720" alt="PCG 生成的橡树林 (mock 渲染)">
</p>

上面这片橡树林来自一条 PCG 管线（landscape → sampler → 平坦过滤 → 随机变换 → spawn），在 200×200m 地形上撒出 141 棵橡树，只长在平坦区域。三行命令复现，全程 mock。

<p align="center">
  <img src="assets/terminal-demo.png" width="880" alt="真实终端输出: demo 生成、全模块自检、MCP 自检">
  <br>
  <sub>真跑出来的输出，不是排版伪造 —— 106 条模块断言 + 12 条 MCP 断言全绿，48 个工具全部接线</sub>
</p>

---

## 安装

```bash
git clone https://github.com/JediKinght9527/ue5-ai-commander.git
cd ue5-ai-commander
uv sync --frozen --extra dev      # 或: pip install -e .
```

只要 stdlib 也能跑，唯一的运行时依赖是 `anthropic`（只有接 Claude API 时才用得上）。

## 使用

### MCP（推荐）

加到 Claude Code 的 `settings.json`：

```json
{
  "mcpServers": {
    "ue5": {
      "command": "uv",
      "args": ["--directory", "/path/to/ue5-ai-commander", "run", "python", "-m", "cindra.mcp_server"]
    }
  }
}
```

然后直接说人话：`只在平坦区域撒 100 棵橡树，别长在斜坡上`。

### CLI

```bash
uv run --frozen python -m cindra.cli --once "放三个 cube 围成圈"
uv run --frozen python -m cindra.cli --mode pcg --once "生成一段赛道"
```

### 接真 UE 5.7

见 [WINDOWS_SETUP.md](WINDOWS_SETUP.md)。切 `--backend ue` 即可，工具 schema 和 agent 逻辑一行都不用改。

## 模块

| 模块 | 做什么 | 例子 |
|------|--------|------|
| Chat | 改场景 | "生成 10 棵树围成圈，中间放块石头" |
| Docs | UE 问答 (RAG) | "Actor 和 Pawn 什么区别" |
| Code | 生成 UE C++ | "给角色加一段冲刺逻辑" |
| Blueprint | 搭蓝图图 | "BeginPlay 时打印 hello" |
| PCG | 程序化生成 | "只在平坦区域撒橡树，斜坡别长" |
| Cine | 运镜 | "镜头从高空缓缓推向主角" |
| PIE | 启动 / 读日志 / 停止 | "跑起来看看有没有报错" |
| Lighting | 风格化布光 | "换成恐怖片打光" |
| Asset | 搜资产并放置 | "把木箱摆到桌上" |
| Blockout | 灰盒场景 | "生成一个狙击巷道" |

十个模块共用同一套 agent loop 和 mock/real 双后端。

## 工具清单

```
Chat (11)        spawn_actor, spawn_grid, delete_actor, move_actor,
                 set_transform, arrange_scene, inspect_viewport, undo,
                 list_actors, clear_scene, spawn_asset

Docs (2)         search_docs, list_topics

Code (2)         search_project, list_symbols

Blueprint (11)   create_blueprint, compile_blueprint, list_node_types,
                 add_node, add_variable, connect_pins, delete_node,
                 list_graph, clear_graph, list_blueprint_templates,
                 inject_blueprint_t3d

PCG (9)          list_pcg_node_types, add_pcg_node, connect_pcg_pins,
                 set_pcg_param, delete_pcg_node, list_pcg_graph,
                 run_pcg_graph, inspect_pcg_result, clear_pcg_graph

Cine (7)         create_sequence, add_cinematic_camera, camera_move,
                 render_sequence, review_render, list_sequence,
                 inspect_viewport

PIE (3)          launch_pie, stop_pie, read_pie_log

Lighting (1)     light_rig (5 styles: horror/golden_hour/studio/
                 night_neon/overcast)

Asset (1)        search_assets

Blockout (1)     generate_blockout (5 templates: combat_arena/
                 sniper_alley/choke_point/boss_room/race_track)
```

共 **48 个**。蓝图 T3D 注入：`inject_blueprint_t3d` 直接注入整张子图（BeginPlay→Print、Branch→双路打印等 7 个模板），不用逐节点 add→connect。

PIE 自动化闭环：`launch_pie` → `read_pie_log` → 有错就改 → 重跑。

## 验证

不用 UE、不用 API key，任何系统都能跑：

```bash
uv run --frozen python run_selfchecks.py            # 17 个模块 / 106 条断言
uv run --frozen python run_selfchecks.py mcp_server # MCP 层 / 13 条断言
uv run --frozen python -m cindra.demo --check        # demo 可复现 / 3 条断言
```

单个模块也能单独跑：

```bash
python -m cindra.docs_index          # 10/10
python -m cindra.project_index       # 5/5
python -m cindra.mock_ue             # 6/6
python -m cindra.verifier            # 9/9
python -m cindra.pcg_model           # 12/12
python -m cindra.tripo_pcg_bridge    # 6/6
python -m cindra.session             # 3/3
python -m cindra.asset_index         # 8/8
python -m cindra.camera_math         # 4/4
python -m cindra.cine_model          # 4/4
python -m cindra.imaging             # 3/3
python -m cindra.lighting_rigs       # 4/4
python -m cindra.mock_viewport       # 4/4
python -m cindra.blueprint_model     # 5/5
python -m cindra.t3d_templates       # 6/6
python -m cindra.pie_tools           # 8/8
python -m cindra.registry            # 9/9
python -m cindra.mcp_server --selfcheck  # 13/13
```

CI 在 **ubuntu + macos × py3.11 + py3.12** 四组矩阵上跑全部断言，另加 `ruff` + `pyright` + wheel 构建检查。

## 设计

### mock 先行

每个模块在内存里有 mock：场景是 dict，蓝图是图节点，PCG 是点云计算，视口是 PNG 渲染。mock 全绿 → 切 transport → 同一套代码在真 UE 里跑。

### 验证闭环

每次改场景前后拍快照，diff 对账。工具返回 ok 但引擎里没生效的静默失败会被抓出来，改写成 `VERIFY FAILED`，截图回喂给 agent，让它改。

### 确定性

任何随机都走 `md5(seed|salt)` 而不是 `random` —— 同一张图在任何机器上跑出同一片森林。`global_seed` 换掉，整张图重新长。

### 多模型

见 [COMMAND_RUNNERS.md](COMMAND_RUNNERS.md)。

## 文件

```
cindra/        44 个模块：mcp_server / registry / pcg_model / blueprint_model /
               scene_tools / verifier / pcg_verifier / mock_ue / transport / ...
ue_plugin/     注入到 UE 编辑器侧的 helper
check_ue.py    真 UE 连通性分阶段诊断（需 Windows + UE）
run_selfchecks.py  一条命令跑全模块
docs/          发帖文案
```

## 参与

见 [CONTRIBUTING.md](CONTRIBUTING.md) —— 验证命令、提交约定、领域约定（尤其是"参数要么真生效，要么别暴露"）。

安全问题见 [SECURITY.md](SECURITY.md)。变更记录见 [CHANGELOG.md](CHANGELOG.md)。

## License

[MIT](LICENSE)
