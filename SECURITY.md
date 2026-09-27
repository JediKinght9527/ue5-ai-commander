# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| 0.3.x   | ✅        |

## Reporting a vulnerability

请不要在公开 Issue 里提交漏洞细节。用 GitHub 私下报告：

- **Security → Report a vulnerability**（仓库右侧栏）：https://github.com/JediKinght9527/ue5-ai-commander/security/advisories/new

请尽量包含：

- 受影响版本与运行方式（mock / 真 UE / 哪个平台）
- 最小复现步骤
- 影响面：是否会执行任意代码、读写工作区文件、泄露 API key
- 你已经试过的缓解方案

## 安全相关的设计约束

这个项目会**代替你在 UE 编辑器里执行代码**，所以下面几条是硬约束，改动时不要破坏：

- **不静默执行**。所有工具调用都经 MCP 显式触发，没有隐藏的自动执行路径。
- **不联网**。除 MCP 客户端本身（stdio）外，代码不发起任何网络请求；依赖外部服务需要用户显式配置。
- **API key 不落盘**。`anthropic` 的 key 只从环境变量读，不写进 session 文件、不进日志。
- **session 文件只存对话**。`save_session` 存的是消息与工具结果，不含凭据。
- **Windows 侧同样成立**。`ue_plugin` / `check_ue.py` 跑在引擎的 Python 环境里，约束一致。

## 已经在防的坑

- `lint` 作业强制 ruff + pyright，`zip(strict=...)` 显式声明，长度不等会直接报错而不是静默截断。
- 快照为 `None` 时校验降级成空 dict 并继续，不会把 `None` 当 dict 用。
- CI 在 ubuntu + macos × py3.11 + py3.12 四组矩阵上跑全模块自检。

发现安全问题不会因为"看起来只是个小 bug"而被忽略；如果服务本身默认边界不安全，也请直接报告。
