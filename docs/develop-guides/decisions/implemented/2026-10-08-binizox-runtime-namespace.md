# Binizox 运行时命名空间

状态：implemented
类型：architecture
Owner：backend/package/pyproject.toml

## 问题

产品名已经是 Binizox，但 Python 包、CLI、环境变量、镜像、容器入口和缓存键若继续使用旧项目名，会形成两套互相矛盾的运行事实。

## 决策

Binizox 自有运行时只使用以下命名空间：Python 包 `binizox`，CLI 分发包 `binizox-cli`、import `binizox_cli`、命令 `binizox`，环境变量 `BINIZOX_*`，用户配置 `~/.binizox/config.toml`，容器、镜像和运行目录使用 `binizox-*`。

不提供旧 Python 包或旧环境变量的隐式运行分支。旧本地状态通过显式、非破坏性的迁移脚本转换。根 `LICENSE` 只标识 Binizox；真实上游项目名、URL、commit、版权声明与完整 MIT 条款保留在 `THIRD_PARTY_NOTICES.md`、wheel 许可证目录及复用记录中。

Linux 生产文件边界继续使用 `dir_fd + O_NOFOLLOW`。原生 Windows Conda 开发没有这些常量和系统调用，因此只在该平台使用逐级拒绝 symlink 的可移植路径；不能以 Windows 测试替代 Linux 安全测试。

## 替代方案

- 只更换前端文案：无法解决 import、部署和排障仍暴露旧命名的问题。
- 长期保留旧包别名：会让每条调用链永久承担两套配置契约。
- 重写主工程：会丢失已经验证的 Run、worker、SSE、知识库和 Skill 能力。

## 后果

旧命令和导入路径不兼容；迁移后的 JWT 需要重新登录。迁入数据库里的旧 API Key 仅在认证边界保留验证兼容，新 Key 只签发 `bzkey_` 前缀。

## 验证

- `python -m compileall` 通过，运行时代码不存在 `yuxi.*` import。
- Binizox Evidence/个人能力单元测试通过；CLI 110 项通过，Windows 专属 POSIX mode 断言按平台跳过。
- Compose、Vue 和文档只引用 Binizox 自有命名；上游事实仍指向真实来源。
- Windows 可导入并运行 Workspace 普通文件路径；POSIX 安全分支由 Ubuntu workflow 验证。
- backend、CLI 和 Personal Tool Runner wheel 都携带 Binizox LICENSE 与上游 notices。

旧能力不存在：shipping 代码不再创建旧包、旧 CLI、旧环境变量或旧容器标识。

重新引入条件：只有存在明确外部消费者、迁移窗口和删除日期时，才能增加边界明确的兼容适配器。
