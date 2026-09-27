# Changelog

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## Unreleased

### Fixed

- **PIE 自动化从死功能变成真功能**：`launch_pie` / `stop_pie` / `read_pie_log` 早就实现、CI 也在测，但既没进 MCP 注册表也没进 CLI —— MCP 客户端根本调不到，README 却把它们当正式工具写着。现在注册为 `module=pie`，mock 走 `MockPIESession`，真 UE 走 console command。
- **`global_seed` 真的生效了**：此前 `execute()` 读了它就没人用，且 `landscape_input` 默认 seed 写死 42、采样点只哈希节点 id，换 `global_seed` 整个图纹丝不动。现在地形与采样点都由它派生。
- **`density_noise.frequency` 真的生效了**：此前噪声是纯哈希，没有频率概念。改成按空间网格生成，可调空间频率。
- **CLI 的 `/graph` 不再崩**：原本 `print("\n" + list_graph())`，而 `list_graph()` 返回 dict，一敲就 TypeError。改用 `render_stats()`。
- **`list_actors` 描述与行为对齐**：旧代码 dict 赋值重复键，`cine_tools` 的描述覆盖了 `scene_tools` 的，但 dispatch 又按名字路由回 `scene_tools`。现在以先注册者为准，冲突显式记录。
- **快照为 `None` 不再引发 TypeError**：`verifier` / `pcg_verifier` 直接下标访问可能为 None 的快照，报错还跟"校验失败"毫无关系。统一降级成空 dict。
- **`base_agent.tool_counts` 不再丢弃统计**：这个 dict 建了却从不累加，"agent 到底调了什么、调了几次"这个调试信息直接没了。现在累加到 `last_tool_counts`。

### Added

- 工具注册表 `cindra/registry.py`：`ToolSpec` + `ToolRegistry`，schema 与 handler 登记在同一处；新增 `unwired()` / `conflicts` 让"漏接线"和"同名冲突"在自检里立刻暴露。
- `run_selfchecks.py`：一条命令跑全 17 个模块，失败退出码非 0。
- 打包配置 `pyproject.toml`：发行名 `ue5-ai-commander`，import 名保持 `cindra`。
- 静态检查：`ruff`（E,F,W,I,B,UP,C4,SIM）与 `pyright` basic，两者均已全清。
- CI 拆成三个作业：`selfcheck`（4 组矩阵跑全模块）、`lint`（ruff + pyright）、`build`（wheel + twine check）。action 依赖按 commit SHA 固定。

### Changed

- `dispatch_tool` 从 ~110 行的 `if name == ...` 链退化为 4 行查表（`mcp_server.py` 净减 288 行）。
- 4 个 PCG filter 分支不再依赖"同名 `keep` 闭包遮蔽"，统一改为 `pred` 赋值。
- `camera_math` 新增 `as_vec3`：把任意 3 元序列收敛成 `Vec3`，长度不对时明确报错而不是静默截断。
- `zip` 调用全部显式声明 `strict=`：长度应相等的用 `True`（不等即 bug），滑窗配对用 `False`。
- 断言总数 103 → 121。

## 0.3.0

- 初始版本：9 个模块域（chat / docs / code / blueprint / pcg / cine / lighting / asset / blockout）、43 个 MCP 工具、mock/真引擎双后端、PCG 程序化生成、蓝图图、C++ 生成、引擎 RAG 问答、运镜、布光。
