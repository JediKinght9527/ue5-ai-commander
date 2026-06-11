# Cindra (灰星) —— 自然语言操控 UE5 的 AI 工具

> Cindra = **cinder**(灰烬) + **astra**(星)。用一句话(中文/英文)操控 Unreal Engine 5:
> 改场景、写 C++、问 UE、搭蓝图。Claude agent 拆解意图 → 调工具 → 在引擎里真正执行,
> 操作后读回状态自检,而非"自信地以为成了"。

## 四大功能

| 功能 | 干什么 | 一句话举例 |
|---|---|---|
| **CindraChat** | 改场景 | "生成 10 个 cube 排成网格,再放个球当主角" |
| **CindraDocs** | UE 问答 (RAG) | "Actor 和 Pawn 有什么区别?" |
| **CindraCode** | 写符合工程规范的 C++ | "给角色加一个冲刺技能" |
| **CindraBlueprint** | 搭蓝图事件图 | "BeginPlay 时打印 hello" |

四块**共用同一套 agent loop 骨架 + mock/real 双后端**:在没装 UE 的 Mac 上离线验证逻辑
(确定性自检全绿),原样搬到装了 UE5 的 Windows 接真引擎——接真引擎只换 transport,
agent 与工具层不动。

## 现状

- ✅ 四大功能 mock 验证全部通过 (docs 检索 10/10、project 符号 5/5、blueprint 建图、chat 网格)
- 🚧 真 UE5 闭环:在 Windows + UE5.5 上机联调中 —— 见 [`WINDOWS_SETUP_5.5.md`](WINDOWS_SETUP_5.5.md)
- 🔜 接 Tripo3D 文字生成真实 3D 模型 (补"只能放基础形状"的短板) —— 方案见 [`CINDRA_ASSETS_TRIPO_PLAN.md`](CINDRA_ASSETS_TRIPO_PLAN.md)

## 快速开始

```bash
git clone https://github.com/JediKinght9527/cindra.git
cd cindra
python3 -m pip install -r requirements.txt

# 1) 离线自检 (无需 UE / 无需 API key / 无需联网) —— 先确认基线全绿
python3 -m cindra.docs_index       # 知识库检索 10/10 top-1
python3 -m cindra.project_index    # 工程符号 5/5 top-1

# 2) 跑四大功能 (需模型 API key;默认 mock 后端,Mac 上即可)
export ANTHROPIC_API_KEY=sk-ant-...
python3 -m cindra.cli                                   # CindraChat (默认)
python3 -m cindra.cli --mode docs  --once "Actor 和 Pawn 区别"
python3 -m cindra.cli --mode code  --once "给角色加冲刺技能"
python3 -m cindra.cli --mode blueprint --once "BeginPlay 时打印 hello"

# 3) 接真 UE5 (在 Windows 上,编辑器开着) —— 先跑诊断,再跑闭环
python check_ue.py                                      # 5 阶管道诊断
python -m cindra.cli --backend ue --once "生成5个cube排成一排"
```

CLI 开关: `--mode chat|docs|code|blueprint` · `--backend mock|ue` · `--index lexical|embed` · `--project DIR`

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

## 1. CindraChat —— 自然语言操控 UE5 场景

用自然语言描述想要的场景 → Claude agent 调用工具 → 真正在 UE5 引擎里
spawn / 删除 / 移动 Actor。这是整套 Cindra 的第一块,后续三块复用这里的
agent + transport 骨架。

## 它是怎么工作的

```
你: "在场景里生成 10 个 cube 排成网格, 再放一个球当主角"
        │
        ▼
[Claude Opus 4.8 agent]  —— analyze before acting, 拆成工具调用
        │  spawn_grid(cube, 10) / spawn_actor(sphere, "hero")
        ▼
[scene_tools 派发]  —— 每个工具映射到一个 cnd_*() 引擎函数
        │
        ▼
[transport]  ── mock ──►  内存场景 (Mac, 无需 UE, 还能 ASCII 俯视图)
             └─ ue   ──►  UE Python Remote Execution ──► 真引擎
```

关键设计: **agent 生成的工具调用与后端无关**。同一套 `cnd_spawn/move/...`
既能打到 Mac 内存 mock, 也能打到真 UE —— 你在 Mac 上验证逻辑, 原样搬到 Windows
接真引擎。

## 在 Mac 上跑通 (现在就能, 不需要 UE)

```bash
cd /Users/marco/cindra
python3 -m pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...

# 交互模式 (mock 后端)
python3 -m cindra.cli

# 或单次执行
python3 -m cindra.cli --once "生成10个cube排成网格,再放个球在[500,0,0]"
```

交互命令: `/scene` 看当前场景俯视图, `/reset` 清空对话, `/quit` 退出。

mock 后端把场景画成 ASCII 俯视图, 让你不开 UE 也能"看见"agent 干了什么:
```
+----------------+
|   C  C  C      |
|   C  C  C      |
|   C  C  C   S  |
+----------------+
俯视图 (10 个: cube, sphere)
```

## 搬到 Windows 接真 UE5

最小闭环里 mock 已经证明整条链路对。接真引擎只换 transport, agent 不动。

### 1. 在 UE5 里开启 Python Remote Execution
- 装 **Python Editor Script Plugin** (Edit → Plugins → 搜 Python)。
- **Project Settings → Plugins → Python**:
  - 勾 **Enable Remote Execution**
  - 记下 Multicast Group Endpoint (默认 `239.0.0.1:6766`)
- 重启编辑器。

### 2. 让本机能 import `remote_execution`
UE 自带这个模块, 路径类似:
```
<UE安装>/Engine/Plugins/Experimental/PythonScriptPlugin/Content/Python/remote_execution.py
```
把它所在目录加到 `PYTHONPATH`, 或直接 `pip install` 一个兼容实现。

### 3. 跑 ue 后端
```powershell
$env:ANTHROPIC_API_KEY="sk-ant-..."
python -m cindra.cli --backend ue
```
编辑器开着时, `RemoteExecTransport` 会自动发现引擎节点, 首次注入 `cnd_*()`
助手 (见 `ue_helper.py`), 之后每条指令发一行函数调用并把返回 JSON 带回 agent。

### 已经处理好的两个硬卡点 (对应你之前 MCP_BRIDGE.md)
- **Game Thread**: `cnd_*()` 用 `unreal.ScopedEditorTransaction` 包裹, 走编辑器
  子系统 API, 在引擎主线程执行。
- **撤销/事务**: 每个操作一个 transaction, Ctrl+Z 干净回退。
- **验证闭环**: `list_actors` 让 agent 操作后读回状态自检, 而非"自信地以为成了"。

## 文件
```
cindra/
├── agent.py        Claude agent loop (Opus 4.8, 自适应思考, prompt 缓存)
├── scene_tools.py  Claude 工具 schema + 工具调用 -> cnd_*() 派发
├── transport.py    MockTransport / RemoteExecTransport
├── ue_helper.py    引擎侧 cnd_*() 源码 (真 unreal API)
├── mock_ue.py      Mac 内存场景 (同一套 cnd_*() + ASCII 渲染)
└── cli.py          命令行入口
```

---

# CindraDocs —— UE 问答 RAG (第二块, 已完成)

问 UE5 相关问题 → 检索本地知识库 → Claude 带着检索到的片段作答, 并标注引用。
**复用 CindraChat 的骨架**: 同样的手写 agent loop, agent 调 `search_docs` 读回
真实片段再作答 —— 和 CindraChat 调 `list_actors` 读回状态自检是同一个闭环思路,
都强制"基于真实证据", 不让模型凭记忆瞎编 UE API。

## 它是怎么工作的

```
你: "UE 里 Actor 和 Pawn 有什么区别?"
        │
        ▼
[复用的 Claude agent loop]  —— 复杂问题先拆, 再决定检索什么
        │  search_docs(query="Actor vs Pawn")
        ▼
[docs_tools 派发]  —— search_docs / list_topics
        │
        ▼
[DocsIndex]  ── lexical ──►  BM25 关键词检索 (Mac, 零依赖/离线/确定性, 默认)
             └─ embed   ──►  向量检索 (有 key 的机器, 生产质量)
        │
        ▼
agent 拿到 top-k 片段 + 来源 → 综合作答, 末尾标 [来源: 文件#标题]
```

和 transport 一样是**双后端**: `LexicalIndex` 在这台 Mac 上离线就能跑、能确定性
验证检索质量; 接生产时换 `EmbeddingIndex`, 上层 agent/工具不动。

## 在 Mac 上跑通

```bash
# 检索质量离线自检 (无需 UE / 无需 API key / 无需联网)
python3 -m cindra.docs_index        # 10/10 top-1 命中

# 问答 (需 ANTHROPIC_API_KEY)
export ANTHROPIC_API_KEY=sk-ant-...
python3 -m cindra.cli --mode docs                      # 交互
python3 -m cindra.cli --mode docs --once "Actor 和 Pawn 区别"
```

交互命令: `/topics` 看知识库覆盖哪些主题, `/reset` 清空对话, `/quit` 退出。

## 加你自己的文档

往 `cindra/docs_corpus/` 丢 `.md` 文件即可, 按 `#`/`##` 标题自动切块、可被检索
和引用。换 `--index embed` 切到向量检索 (需配 embedding 提供者)。

## 文件 (CindraDocs 部分)
```
cindra/
├── docs_corpus/*.md   自带的一小份 UE 知识库 (10 篇核心主题)
├── docs_index.py      切块 + LexicalIndex(BM25) / EmbeddingIndex(向量)
├── docs_tools.py      search_docs / list_topics 工具 schema + 派发
└── docs_agent.py      CindraDocsAgent (复用 agent.py 的 loop 结构)
```

---

# CindraCode —— 生成符合工程规范的 UE C++ (第三块, 已完成)

描述要实现的功能 → agent **先索引工程已有符号** (类/父类/UFUNCTION/UPROPERTY、
命名约定) → 生成与现有代码一致的 UE C++。这块是 Cindra 的**护城河**:不是凭空写
C++, 而是"项目索引器当上下文", 产出贴合你这套工程的写法。

## 它是怎么工作的

```
你: "给角色加一个冲刺技能"
        │
        ▼
[复用的 Claude agent loop]  —— 写代码前先研究工程
        │  search_project("角色 character 移动") / list_symbols()
        ▼
[code_tools 派发]  —— search_project / list_symbols
        │
        ▼
[ProjectIndex]  扫 .h/.cpp 正则抽符号 → 复用 docs 的 LexicalIndex(BM25) 检索
        │
        ▼
agent 知道工程有 ACindraCharacter(继承 ACharacter)、UCindraHealthComponent…
→ 生成的代码沿用 'Cindra' 前缀和组件/委托约定, 而不是另起一套
```

和 CindraDocs 同构:docs 索引知识库文档, code 索引工程符号, **共用同一个
LexicalIndex**。离线、纯标准库、确定性。

## 在 Mac 上跑通

```bash
# 工程符号提取 + 检索质量离线自检 (无需 UE / key / 联网)
python3 -m cindra.project_index     # 5/5 top-1 命中, 并打印抽到的符号

# 生成代码 (需 ANTHROPIC_API_KEY)
export ANTHROPIC_API_KEY=sk-ant-...
python3 -m cindra.cli --mode code                          # 索引自带示例工程
python3 -m cindra.cli --mode code --once "给角色加冲刺技能"
python3 -m cindra.cli --mode code --project /path/to/UEProject   # 索引你的真工程
```

交互命令: `/symbols` 看工程已索引的符号, `/reset` 清空对话, `/quit` 退出。

## 自带示例工程
`cindra/sample_project/` 是一个小而典型的 UE C++ 工程 (Character / 生命值组件 /
GameMode / USTRUCT / UENUM / 委托 / Enhanced Input), 让没装 UE 的机器也能验证
索引器。换 `--project` 指向你的真工程即可索引真实代码 (这些 .h/.cpp 引用 UE
引擎头文件, 本机不编译, 只作索引语料)。

## 文件 (CindraCode 部分)
```
cindra/
├── sample_project/    自带示例 UE C++ 工程 (索引验证语料)
├── project_index.py   正则抽 UCLASS/USTRUCT/UENUM/UFUNCTION/UPROPERTY + 检索
├── code_tools.py      search_project / list_symbols 工具 schema + 派发
└── code_agent.py      CindraCodeAgent (复用 agent.py 的 loop 结构)
```

---

# CindraBlueprint —— 自然语言搭蓝图事件图 (第四块, 已完成)

描述要的逻辑 → agent 在蓝图事件图里**加节点、加变量、连引脚**实现它。这是四
功能里**最难、最具护城河**的一块:真正操作 BlueprintGraph 需要 UE C++ 编辑器
插件 (UEdGraph/UK2Node/UEdGraphPin)。沿用 CindraChat 验证过的策略——做一个
**mock 内存图模型**离线跑通整条链路, 真引擎侧用同一套工具接口接入。

## 它是怎么工作的

```
你: "Tick 时, 如果 DeltaSeconds 大于阈值就打印一句话"
        │
        ▼
[复用的 Claude agent loop]  —— 先 list_node_types 看引脚, 规划再连线
        │  add_node(Event_Tick) / add_node(Branch) / connect_pins(...)
        ▼
[blueprint_tools 派发]  —— add_node/add_variable/connect_pins/list_graph/...
        │
        ▼
[transport]  ── mock ──►  内存蓝图图 (Mac, 带连线合法性校验 + 文本渲染)
             └─ ue   ──►  UE C++ 插件操作真 BlueprintGraph (Windows)
        │
        ▼
agent 用 list_graph 读回真实图结构自检, 确认连对了
```

**连线合法性校验**和真 UE 的 `UEdGraphSchema::TryCreateConnection` 一一对应:
只能 output→input、exec 接 exec / data 接同类型 data、一个输入引脚只能连一条、
exec 输出只能连一条。mock 在 Mac 上就能把这些规则跑出来。

## 在 Mac 上跑通

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python3 -m cindra.cli --mode blueprint                       # mock 内存图 (默认)
python3 -m cindra.cli --mode blueprint --once "BeginPlay 时打印 hello"
```

交互命令: `/graph` 看当前事件图 (节点/连线/变量, exec 用 `=>`、data 用 `->`),
`/reset` 清空对话, `/quit` 退出。

## 搬到 Windows 接真 UE 蓝图

真后端要写一个 **C++ 编辑器插件**操作 BlueprintGraph, Python 远程执行只是触发
入口。详细接法和卡点 (GameThread 调度、FScopedTransaction 事务、CompileBlueprint
重编、标脏保存、list_graph 验证闭环) 写在 `blueprint_transport.UE_BP_HELPER_NOTE`。
实现后 `UEBlueprintTransport` 与 mock 对外完全一致, agent/工具不动。

## 文件 (CindraBlueprint 部分)
```
cindra/
├── blueprint_model.py      mock 内存图: 节点/引脚/连线 + 合法性校验 + 文本渲染
├── blueprint_transport.py  Mock/UE 双后端 + UE 侧 C++ 插件接法说明
├── blueprint_tools.py      add_node/connect_pins/list_graph/... 工具 schema + 派发
└── blueprint_agent.py      CindraBlueprintAgent (复用 agent.py 的 loop 结构)
```

---

## Cindra 四大功能 —— 全部完成 ✅
- **CindraChat** (改场景): 自然语言 spawn/move/删除 Actor
- **CindraDocs** (UE 问答): RAG 检索本地知识库, 带引用作答
- **CindraCode** (写 C++): 项目索引器当上下文, 生成符合工程规范的 UE C++
- **CindraBlueprint** (改蓝图): 自然语言搭事件图节点和连线

四块共用同一套 agent loop 骨架 + mock/real 双后端模式: 在 Mac 上离线验证逻辑,
原样搬到装了 UE 的 Windows 接真引擎。
