# Contributing to Genesis Protocol

感谢你对 Genesis Protocol 的关注！我们欢迎社区贡献。

## 开发环境

```bash
# 克隆仓库
git clone https://github.com/0xCaptain888/genesis-protocol.git
cd genesis-protocol

# Python 环境（无外部依赖）
python3 -m pytest tests/ -v

# Solidity（需要 Foundry）
cd contracts && forge build && forge test -vv
```

## 贡献流程

1. **Fork** 本仓库
2. 创建功能分支: `git checkout -b feature/your-feature`
3. 编写代码并添加测试
4. 确保所有测试通过: `python3 -m pytest tests/ -v && cd contracts && forge test`
5. 提交: `git commit -m "feat: 描述你的改动"`
6. 推送并创建 Pull Request

## Commit 规范

- `feat:` 新功能
- `fix:` 修复 Bug
- `docs:` 文档改动
- `test:` 测试改动
- `refactor:` 重构

## 代码规范

- **Python**: flake8 (max-line-length=120)
- **Solidity**: 0.8.26, via_ir=true, optimizer_runs=200
- **前端**: 单文件 HTML，Tailwind CSS

## 安全提醒

- 不要提交 `.env` 或私钥
- 所有新功能默认 `DRY_RUN=True`
- 合约变更必须有对应测试

## 许可证

MIT License
