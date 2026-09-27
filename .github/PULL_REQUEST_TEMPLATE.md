## Summary

<!-- 改了什么行为, 不是罗列文件 -->

Closes #

## Type

- [ ] Bug fix
- [ ] 新工具 / 新能力
- [ ] 对外契约变化（工具名 / input schema / 返回结构）
- [ ] 文档 / 内部重构

## 验证

- [ ] `uv run --frozen python run_selfchecks.py` 通过
- [ ] `uv run --frozen python run_selfchecks.py mcp_server` 通过
- [ ] `uv run --frozen python -m cindra.demo --check` 通过
- [ ] `uv run --frozen ruff check cindra/` 通过
- [ ] `uv run --frozen pyright` 通过
- [ ] 改 bug 的带上了能单独复现该 bug 的回归断言

## 确定性

- [ ] 没有引入 `random`（随机必须走 `_hash_float(seed, salt)`）
- [ ] 同一输入跑两次结果一致

## 对外契约

<!-- 没有改动就写"无"；有改动写清 旧 → 新 与迁移方式 -->
