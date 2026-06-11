"""Cindra-clone: 让 Claude 通过自然语言操控 UE5 场景 (CindraChat 闭环).

模块结构:
  ue_helper   — 在引擎里执行的 cnd_*() 助手 (真 UE,用真 unreal API)
  scene_tools — Claude 的场景工具 schema + 把工具调用翻成 cnd_*() Python
  transport   — 抽象执行通道: 真 UE 远程执行 / Mac 本地 mock
  mock_ue     — Mac 上的内存场景, 实现同一套 cnd_*()
  agent       — Claude agent loop (tool use + 缓存 + analyze-before-acting)
  cli         — 命令行对话入口
"""

__version__ = "0.1.0"
