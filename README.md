[![en](https://img.shields.io/badge/lang-English-blue)](README.en.md)

# cindra — 和 UE5 说话

说出来，UE5 就做。不用翻菜单。不用拖节点。

Claude Code / Cursor 里直接对话，或命令行 `--once`。没装 UE 也能跑（mock 后端），上 Windows 接真引擎只换传输层。

---

## 30 秒上手

```bash
git clone https://github.com/JediKinght9527/cindra.git && cd cindra && pip install -r requirements.txt

# A) Claude Code (MCP) — 直接说你要什么
# 在 claude settings.json 的 mcpServers 里加:
#   "cindra": {"command": "python", "args": ["-m", "cindra.mcp_server"]}
> 生成5棵树围成一圈, 中间放块石头
> 在这片地形上只在平坦区域撒橡树, 斜坡别长树
> BeginPlay 时在屏幕上打印 hello

# B) 命令行 — 五个模块, 五句命令
export ANTHROPIC_API_KEY=sk-ant-...
python -m cindra.cli --mode chat      --once "生成5个cube排一排"
python -m cindra.cli --mode docs      --once "Actor 和 Pawn 什么区别"
python -m cindra.cli --mode code      --once "给角色加一段冲刺逻辑"
python -m cindra.cli --mode blueprint --once "BeginPlay 时打印 hello"
python -m cindra.cli --mode pcg       --once "在500x500区域里撒橡树, 别太密"
```

PCG 模块跑完会画一张 ASCII 俯视图，树撒在哪一目了然。

---

## 五个模块

| 模块 | 干什么 | 一句话 |
|------|--------|--------|
| **Chat** | 改场景 | "生成 10 棵树围成圈，中间放块石头" |
| **Docs** | 查引擎 | "Actor 和 Pawn 什么区别？" |
| **Code** | 写 C++ | "给角色加一段冲刺逻辑" |
| **Blueprint** | 搭蓝图 | "BeginPlay 时在屏幕上打印一行字" |
| **PCG** | 程序生成 | "这块地形上，只在平坦的地方撒橡树，斜坡别长" |

五个模块共用一套 agent 骨架 + mock/real 双后端。mock 在 Mac 上离线验证，上 Windows 接真 UE5 只换 transport，agent 和工具层不动。

---

## 自检（不用 UE，不用 key，任何系统）

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
python -m cindra.mcp_server --selfcheck  # 8/8, 43 个工具
```

**103 条断言，全部通过。** 15 个模块，9 个工具域。

---

## 怎么做的

### mock 先行

写代码、跑测试都不需要开着 UE。每个模块本地内存里有个 mock：场景是 actor 字典，蓝图是节点和连线，PCG 是点云计算，视口是确定性 PNG 渲染。mock 全绿 → 切 transport → 同一套代码在真 UE 里跑。

### 做一步、看一步、不对就改

每次改完场景：前后拍快照，diff 自动对账（"你说 spawn 了个 cube，我数数场景里是不是真多了一个"）。工具返回 ok 但引擎里没生效的静默失败会被抓出来，改写成 `VERIFY FAILED` 回喂给 agent。截图也能回喂。改坏了 undo。

### 43 个 MCP 工具，9 个领域

Chat(10) · Docs(2) · Code(2) · Blueprint(11) · PCG(9) · 运镜(8) · 灯光(1) · 资产(2) · 灰盒(5模板) · PIE(3)

蓝图 T3D 注入：常见模式 (事件→打印、分支→双路打印、比较→分支、延迟打印) 封装成模板，一句 `inject_blueprint_t3d` 建好整张子图，不用逐个 add→connect。

PIE 自动化：`launch_pie` → 模拟输入 → `read_pie_log` → 有错就改 → 重跑。agent 自己测自己的产出。

### 10+ 模型提供商

Anthropic · OpenAI · DeepSeek · GLM/Z.AI · OpenRouter · SiliconFlow · Moonshot/Kimi · DashScope/Qwen · 火山 Ark/Doubao · 任何 OpenAI 兼容接口

---

## 接真 UE5

Windows + UE 5.7 编辑器开着 + Python Remote Execution 开启：

```powershell
$env:PYTHONPATH = "C:\Program Files\Epic Games\UE_5.7\Engine\Plugins\Experimental\PythonScriptPlugin\Content\Python"
$env:ANTHROPIC_API_KEY = "sk-ant-..."
python -m cindra.cli --backend ue --once "生成5个cube排成一排"

# 或用 MCP: 传参数 _backend: "ue"
```

详细配置见 `WINDOWS_SETUP.md`。第一次跑用 `check_ue.py` 诊断管道。

---

## 文件地图

```
cindra/
├── cli.py              命令行入口
├── mcp_server.py       43 个 MCP 工具, 9 个领域
├── base_agent.py       共享对话骨架 (pre/post 钩子 + 图片回喂)
├── agent.py            场景 agent (+ 验证闭环)
├── verifier.py          硬校验层 (快照 diff, 零 token)
├── scene_tools.py       场景工具定义 + 派发
├── mock_ue.py           内存场景后端 (+ 相机 + undo)
├── transport.py         mock/真机双通道
├── ue_helper.py         引擎侧 Python (remote exec)
├── blockout_builder.py  确定性灰盒模板 (5 种玩法)
├── scene_intent.py      常用中文指令快速路径
├── session.py           会话持久化
├── model_provider.py    10+ 模型提供商适配
├── asset_index.py       工程资产检索 (BM25)
│
├── docs_*.py            文档问答 (索引 + agent + 工具)
├── code_*.py            写 C++ (工程索引 + agent + 工具 + 示例工程)
├── blueprint_*.py       搭蓝图 (图模型 + agent + 工具 + transport)
├── t3d_templates.py     蓝图 T3D 注入 (7 个模板)
│
├── pcg_model.py         PCG 图模型 + 执行引擎 (19 种节点)
├── pcg_tools.py         PCG 工具定义
├── pcg_agent.py         PCG agent (+ 验证钩子)
├── pcg_verifier.py      PCG 校验层
├── ue_pcg_helper.py     PCG 引擎侧 helper
├── tripo_pcg_bridge.py  Tripo3D 文生3D → PCG spawn
│
├── pie_tools.py         PIE 自动化 (启动/停止/读日志)
├── cine_*.py            运镜模式 (agent + 模型 + 工具 + transport)
├── lighting_rigs.py     风格化布光 (5 种风格)
├── camera_math.py       3D 相机数学 (环绕/推拉/升降/飞掠)
├── mock_viewport.py     确定性 PNG 视口渲染
├── imaging.py           纯标准库 PNG 编码
├── command_bus.py       可移植 CLI runner 桥
└── __init__.py
```

---

## 和同类比

Cindra 的路线：AI 应该**动手**，不是只回答问题。

| 能力 | cindra | 同类 UE AI 工具 |
|------|--------|----------------|
| mock 后端 (不用 UE 就能跑) | 有 | 没有 |
| 验证闭环 (快照 diff, 零 token) | 有 | 没有 (LLM 看截图) |
| 自然语言驱动 PCG 图 | 有 (19 种节点) | 没有 (只能告诉你 PCG 怎么用) |
| 文生3D → 自动导入 → PCG 散布 | 有 (Tripo 桥) | 没有 |
| PIE 自动化自测 | 有 | 没有 |
| 双后端透明切换 | 有 | 没有 |
| MCP 工具数 | 43 | 不等 |
| 蓝图 T3D 注入 | 7 个模板 | 不等 |

---

## 许可

MIT
