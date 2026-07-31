[![en](https://img.shields.io/badge/lang-English-blue)](README.en.md)

# cindra — 和 UE5 说话

**cindra** 是一个用自然语言操控 Unreal Engine 5 的命令行工具。

说出来，UE5 就做。不用翻菜单、不用手拖节点、不用背 API。

---

## 五个模块

| 模块 | 一句话干嘛 | 实战用法 |
|------|-----------|----------|
| **Chat** | 改场景 | "生成 10 棵树围成圈，中间放块石头" |
| **Docs** | 查引擎 | "Actor 和 Pawn 什么区别？" |
| **Code** | 写 C++ | "给角色加一段冲刺逻辑" |
| **Blueprint** | 搭蓝图 | "BeginPlay 时在屏幕上打印一行字" |
| **PCG** 🆕 | 程序生成 | "这块地形上，只在平坦的地方撒橡树，斜坡别长" |

---

## 怎么跑

```bash
git clone https://github.com/JediKinght9527/cindra.git
cd cindra
pip install -r requirements.txt

# 自检（不用 UE，不用 API key，Mac/Win/Linux 都能跑）
python -m cindra.docs_index          # 知识库检索 10/10
python -m cindra.project_index       # 符号抽取 5/5
python -m cindra.mock_ue             # 场景操作 4/4
python -m cindra.verifier            # 验证闭环 9/9
python -m cindra.pcg_model           # PCG 图模型 10/10
python -m cindra.tripo_pcg_bridge    # Tripo 桥接 6/6

# 配好 API key 就能用
export ANTHROPIC_API_KEY=sk-ant-...

# 五句话体验五个模块
python -m cindra.cli --mode chat      --once "生成5个cube排一排"
python -m cindra.cli --mode docs      --once "UE 里 Actor 和 Pawn 的区别"
python -m cindra.cli --mode code      --once "给角色加冲刺技能"
python -m cindra.cli --mode blueprint --once "BeginPlay 时打印 hello"
python -m cindra.cli --mode pcg       --once "在500x500的区域里随机撒橡树，别太密"
```

PCG 模块跑完会在终端画一张 ASCII 俯视图，让你看到树撒在哪了。

---

## 怎么接真 UE5

在装了 UE5 的 Windows 上跑时加 `--backend ue`：

```powershell
$env:PYTHONPATH = "C:\Program Files\Epic Games\UE_5.7\Engine\Plugins\Experimental\PythonScriptPlugin\Content\Python"
$env:ANTHROPIC_API_KEY = "sk-ant-..."
python -m cindra.cli --backend ue --once "生成5个cube排成一排"
```

需要开 UE5 编辑器 + Python Remote Execution。详细的接法在 `WINDOWS_SETUP.md`。

### 模型配置

默认仍走 Anthropic:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

也可以切到 OpenAI-compatible 接口:

```bash
# DeepSeek
export CINDRA_MODEL_PROVIDER=deepseek
export DEEPSEEK_API_KEY=sk-...
# 可选: export CINDRA_MODEL=deepseek-v4-flash

# GLM / Z.AI
export CINDRA_MODEL_PROVIDER=glm
export ZAI_API_KEY=...
# 可选: export CINDRA_MODEL=glm-5.1

# OpenAI / Codex 账号可用模型
export CINDRA_MODEL_PROVIDER=openai
export OPENAI_API_KEY=sk-...
export CINDRA_MODEL=<你的模型 id>
```

常用 provider 预设:

| Provider | `CINDRA_MODEL_PROVIDER` | Key 环境变量 | 默认 base URL | 默认模型 |
|---|---|---|---|---|
| OpenAI / Codex | `openai` 或 `codex` | `OPENAI_API_KEY` | `https://api.openai.com/v1` | 必须设置 `CINDRA_MODEL` |
| DeepSeek | `deepseek` | `DEEPSEEK_API_KEY` | `https://api.deepseek.com` | `deepseek-v4-flash` |
| GLM / Z.AI | `glm` | `ZAI_API_KEY` / `GLM_API_KEY` | `https://api.z.ai/api/paas/v4` | `glm-5.1` |
| OpenRouter | `openrouter` | `OPENROUTER_API_KEY` | `https://openrouter.ai/api/v1` | `anthropic/claude-sonnet-4.5` |
| SiliconFlow | `siliconflow` | `SILICONFLOW_API_KEY` | `https://api.siliconflow.cn/v1` | `Qwen/Qwen3-Coder-480B-A35B-Instruct` |
| Moonshot / Kimi | `moonshot` 或 `kimi` | `MOONSHOT_API_KEY` | `https://api.moonshot.cn/v1` | `kimi-k2-0711-preview` |
| DashScope / Qwen | `dashscope` 或 `qwen` | `DASHSCOPE_API_KEY` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-max` |
| Volcengine Ark / Doubao | `ark` 或 `doubao` | `ARK_API_KEY` | `https://ark.cn-beijing.volces.com/api/v3` | `doubao-seed-1-6` |

高级用法: `CINDRA_API_KEY` / `CINDRA_BASE_URL` / `CINDRA_MODEL` 可覆盖任意 OpenAI-compatible 提供商。

### 在 UE 里可视化使用

仓库带一个源码版 UE Editor 插件:

```text
ue_plugin/CindraEditorPanel
```

安装方式:把 `ue_plugin/CindraEditorPanel` 复制到你的 UE 工程 `Plugins/CindraEditorPanel`, 重新打开工程并允许编译。插件会自动打开 `Cindra` 面板, 也可从 `Window > Cindra` 或 `Tools > Cindra` 打开。

插件默认读取这些环境变量:

```powershell
$env:CINDRA_PROJECT_ROOT = "C:\path\to\cindra"
$env:CINDRA_PYTHON_EXE = "C:\path\to\cindra\.venv\Scripts\python.exe"
$env:CINDRA_UE_PYTHONPATH = "D:\UE_5.5\Engine\Plugins\Experimental\PythonScriptPlugin\Content\Python"
$env:CINDRA_MODEL_PROVIDER = "glm"
$env:CINDRA_MODEL = "glm-5.1"
$env:BIGMODEL_API_KEY = "..."
```

`CINDRA_PROJECT_ROOT` / `CINDRA_PYTHON_EXE` 不设时, 插件会尝试从 UE 工程相邻目录推断。Run 会异步启动 Python, 避免阻塞 UE 主线程导致 Remote Execution 发现不到当前编辑器。每次运行的 prompt 和 stdout/stderr 会写到工程的 `Saved/Cindra` 目录。

先确保第 2 层 `python check_ue.py` 已经 5 阶全过, UE 编辑器开着、关卡加载、视口可见。然后在同一个 PowerShell 里设置模型和 UE 路径:

```powershell
$env:PYTHONPATH = "D:\UE_5.5\Engine\Plugins\Experimental\PythonScriptPlugin\Content\Python"

# 任选一个模型 provider, 例如 DeepSeek:
$env:CINDRA_MODEL_PROVIDER = "deepseek"
$env:DEEPSEEK_API_KEY = "sk-..."

python -m cindra.cli --backend ue --once "生成5个cube排成一排, 中间放个球当主角"
python -m cindra.cli --backend ue --once "先生成9个cube排成3x3网格"
python -m cindra.cli --backend ue --once "让场景里的东西像被地震砸过一样"
```

每条命令结束后切回 UE 视口看 Actor 是否出现/变换。交互式连续操作用:

```powershell
python -m cindra.cli --backend ue
```

可用 `/scene` 读回当前场景, `/reset` 清空 agent 对话, `/quit` 退出。

---

## 设计思路

### mock 先行

不需要开着 UE 才能跑。每个模块在本地内存里有个 mock——改场景就是改内存里的 actor hash、搭蓝图就是内存里的图节点、跑 PCG 就是内存里的点云计算。mock 跑通了，把 transport 切到 RemoteExecTransport，同样的代码在真 UE 里执行。

### 做一步、看一步、不对就改

每次在引擎里动手后：
- 前后拍场景快照，diff 自动对账——"你告诉我 spawn 了个 cube？我数数场景里是不是真多了一个。"抓的就是那种"工具返回 ok 但屏幕没变化"的闷屁。
- 截图回喂给 AI 看——AI 自己会看视口，不用人来判断"对不对"。
- 改坏了能 undo——每个操作包了 editor transaction，Ctrl+Z 和 undo 工具都能用。

### 手和眼，不是嘴

UE 5.7 自带的 AI 助手能回答问题、给代码。cindra 的目标不一样：帮你直接动手。建图、撒点、生成模型、看结果、修正——一轮跑完。PCG 这块尤其明显：官方助手能告诉你 PCG 怎么用，cindra 能直接帮你建 PCG 图并跑出来。

---

## 文件速览

```
cindra/
├── cli.py              命令行入口
├── base_agent.py       共享的对话骨架
├── agent.py            场景操作 agent（+验证闭环）
├── scene_tools.py      场景工具
├── mock_ue.py          本地内存场景（mock 后端）
├── transport.py         真 UE / mock 双通道
├── ue_helper.py         引擎里跑的 Python 代码
├── verifier.py          硬校验层（前后快照 diff）
│
├── docs_*.py           文档问答（检索 + agent + 工具）
├── code_*.py           写 C++（代码索引 + agent + 工具 + 示例工程）
├── blueprint_*.py      搭蓝图（图模型 + agent + 工具 + transport）
│
├── pcg_model.py         PCG 图模型 + 执行引擎 🆕
├── pcg_tools.py         PCG 工具定义 🆕
├── pcg_agent.py         PCG agent（+验证闭环钩子）🆕
├── pcg_verifier.py      PCG 校验层 🆕
├── ue_pcg_helper.py     PCG 真 UE 端 🆕
└── tripo_pcg_bridge.py  Tripo3D 桥接（文生 3D → PCG spawn）🆕
```

---

## 许可

MIT
