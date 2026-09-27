# Contributing to ue5-ai-commander

感谢参与。这个项目优先保证**可复算、可自检、不把失败伪装成成功**。

## 开发环境

需要 Python 3.11+ 和 [uv](https://docs.astral.sh/uv/)。

```bash
uv sync --frozen --extra dev
uv run --frozen python run_selfchecks.py      # 全模块自检
```

启动本地服务（MCP stdio server）：

```bash
uv run --frozen python -m cindra.mcp_server
```

## 验证是这个项目的核心

改任何东西之前先跑一遍，改完再跑一遍：

```bash
uv run --frozen python run_selfchecks.py            # 17 个模块
uv run --frozen python run_selfchecks.py mcp_server # MCP 层
uv run --frozen python -m cindra.demo --check        # demo 可复现
uv run --frozen ruff check cindra/                   # lint
uv run --frozen pyright                              # 类型
```

**不需要 UE、不需要 API key** —— mock 后端能在任何机器上跑全链路。
这也是本项目的核心主张：先在 mock 上验证，再切 transport 驱动真引擎。

## 提交约定

- 一类变更一个提交，提交信息说明**行为**变化而不是罗列文件。
- 不提交 API key、真实工程路径、UE 工程文件、session 产物。
- 修 bug 必须带回归断言；断言要能**单独复现**该 bug（`assert a != b, "换 X 必须改变结果"` 这类）。
- 指标/公式/参数语义变更，必须在提交信息里说明**旧行为 → 新行为**。
- UI 参数或工具 schema 变更，同步更新 README（README 里的数字是断言出来的，不是手写的）。

## 领域约定

- **mock 与真引擎必须共用同一套逻辑**，只允许 transport 不同。任何"在 mock 里特判"的写法都要在提交信息里说明理由。
- **校验要读回真实状态**。`verifier` / `pcg_verifier` 的存在意义就是抓"工具说 ok 但引擎没生效"的静默失败，不要把它简化成直接返回 ok。
- **确定性优先**。任何随机都必须来自 `_hash_float(seed_str, salt)` 这类稳定哈希，不许用 `random` 模块 —— 否则换台机器结果就变。
- **参数要么真生效，要么别暴露**。见过 `global_seed` 和 `frequency` 读了不用的情况：参数在 schema 里躺着，用户以为它有用。暴露的参数必须能在自检里断言出来。
- 工具名、input schema、输出格式是**对外契约**。改这些要在提交信息里显式标注，并说明迁移方式。

## 报告 bug 时带上

- 你是 mock 后端还是真 UE？哪个平台？
- `python -m cindra.<模块>` 的输出
- 最小复现：几个节点的 PCG 图、哪句话、期望什么
