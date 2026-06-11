# HANDOFF —— 给在这台机器上协助的 AI agent (codex/claude 等)

> 你正在协助验证 **Cindra (灰星)** 这个项目。本文件让你无需翻完整历史就能接手。
> 先读这一页, 再看 `README.md`、`WINDOWS_SETUP_5.5.md`、`CINDRA_ASSETS_TRIPO_PLAN.md`。

## 这是什么
Cindra = 自然语言操控 UE5 的 AI 工具, 四大功能 (Chat改场景 / Docs问答 / Code写C++ /
Blueprint改蓝图), 共用一套 agent loop + **mock/real 双后端**: 没装 UE 的 Mac 上用 mock
离线验证逻辑, 装了 UE5 的 Windows 上换 transport 接真引擎 (agent/工具层不动)。

## 当前环境与目标
- **这台机器 = Windows + UE 5.5**。目标: 把"真 UE 闭环"跑通 —— 打一句中文 → UE5 视口里真的生成/变换场景。
- 代码刚从 GitHub 拉下来 (`https://github.com/JediKinght9527/cindra`)。
- 协作方式: **你 (Windows agent) 动手跑命令**; 卡在 UE 侧报错时, 把 UE 编辑器 **Output Log**
  的 Python traceback 贴出来, 由 Mac 上的 Claude 改 `ue_helper.py` (它有完整上下文)。
  改完会 push, 你 `git pull` 再试。

## 验证分三层 (从易到难, 按顺序)

### 第 1 层: 离线自检 (不需要 UE, 不需要任何 API key, 不需要联网)
先确认基线全绿:
```powershell
python -m pip install -r requirements.txt
python -m cindra.docs_index      # 期望: 检索质量 10/10 top-1 命中
python -m cindra.project_index   # 期望: 5/5 top-1 命中
python -m cindra.mock_ue         # 期望: 场景自检 4/4 通过, 末尾打印"地震后俯视图"
```
这三个全过 = 代码逻辑没问题, 可以进第 2 层。任一不过, 先报出来。

### 第 2 层: 真 UE 管道诊断 (需要 UE5 开着, 不需要 API key)
**一次性准备** (只做一次, 详见 `WINDOWS_SETUP_5.5.md`):
- UE5: Edit→Plugins 启用 **Python Editor Script Plugin**;
  Project Settings→Plugins→Python 勾 **Enable Remote Execution** (端点默认 239.0.0.1:6766); 重启编辑器。
- ⚠️ 5.5 已知坑: **确保有一个可见视口** (别把 Viewport 标签藏起来), 否则 spawn 会崩。
- 设 PYTHONPATH 指到引擎自带 remote_execution:
  ```powershell
  $env:PYTHONPATH = "C:\Program Files\Epic Games\UE_5.5\Engine\Plugins\Experimental\PythonScriptPlugin\Content\Python"
  ```

**跑诊断** (UE5 开着、关卡加载、视口可见):
```powershell
python check_ue.py
```
它把 Python↔UE 管道切成 5 阶, 卡哪阶就报哪阶:
- 台阶 1/2/3 (import / 发现节点 / 远程执行 1+1): 多是环境配置, 脚本会打印怎么修。
- 台阶 4/5 (注入 cnd_*() helper / 真调 unreal API spawn): **这是要改代码的地方** ——
  去 UE 的 **Window→Output Log** 抓 Python traceback, 整段贴出来给 Mac 的 Claude。
- 全过 = 它已在视口放了一个 cube, 可进第 3 层。

### 第 3 层: 真 agent 闭环 + 新功能 (需要 ANTHROPIC_API_KEY)
```powershell
$env:ANTHROPIC_API_KEY = "sk-ant-..."
chcp 65001                                   # 中文不乱码

# 基础场景生成
python -m cindra.cli --backend ue --once "生成5个cube排成一排, 中间放个球当主角"

# 新功能: 场景级语义编辑 (重点验证这个 —— 刚加的)
python -m cindra.cli --backend ue --once "先生成9个cube排成3x3网格"
python -m cindra.cli --backend ue --once "让场景里的东西像被地震砸过一样"
```
每句打完切回 UE 视口看 Actor 是否真的出现/变换。Ctrl+Z 应能撤销 (每步包了 transaction)。

## 这次新增了什么 (你重点要验的)
**场景级语义编辑** (commit 09f2b81), 在 mock 上已 4/4 通过, 现在要在真 UE 上验证:
- 新引擎原语 `cnd_set_transform(name, location?, rotation?, scale?)` —— 一次改位置/旋转/缩放
  (老的 cnd_move 只能平移)。mock 和真 UE (`ue_helper.py`) 都已实现。
- 新工具 `arrange_scene(style, intensity, prefix?)` —— style ∈ earthquake/scatter/topple/tidy/explode。
  它读回全场 Actor → 按风格算每个新 transform → 批量 cnd_set_transform。纯编排, 引擎不需要"懂地震"。

⚠️ **`ue_helper.py` 的真 UE 代码从未在真引擎跑过** (Mac 上没 UE)。第一次跑 `cnd_set_transform` /
`cnd_spawn` 很可能要按 5.5 实际报错微调。已查证这些 API 在 5.5 用法正确 (set_actor_location/
set_actor_rotation/set_actor_scale3d + ScopedEditorTransaction), 但仍以真实 Output Log 为准。

## 已知坑速查
| 现象 | 处理 |
|---|---|
| 台阶 1 `No module named remote_execution` | PYTHONPATH 路径不对, 搜 remote_execution.py 确认实际位置 |
| 台阶 2 没发现 UE 节点 | 编辑器没开 / 没勾 Remote Execution 没重启 / 防火墙拦 UDP 多播 |
| 台阶 4/5 unreal API 报错 | 抓 Output Log traceback, 交给 Mac 的 Claude 改 ue_helper.py |
| spawn 时编辑器崩 | 5.5 视口 bug, 确保有可见视口 |
| Ctrl+Z 有条目但不真撤销 | ue_helper 改对象前需加 actor.modify(), 报出来让 Claude 加 |
| 中文乱码 | chcp 65001 |

## 你 (Windows agent) 的边界
- 可以做: 跑上面所有命令、读 Output Log、按脚本提示修环境配置、改 ue_helper.py 后本地试。
- 改 ue_helper.py 真 UE 逻辑时, 建议先把报错和你的改法同步出来 (Mac 的 Claude 有四大功能
  整体上下文, 避免改歪了破坏 mock/real 对称性)。
- 验证完把结果 (哪层过了 / 哪里卡了 + 报错) 汇总, 方便回传给 Mac 协同。
