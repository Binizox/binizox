# Binizox 本地验收记录

验收日期：2026-10-13

仓库：`D:\Download\Binizox`

分支：`codex/binizox-mvp`

## 范围

本轮完成独立 Binizox 命名空间、个人 Evidence/Skill/笔记工具链、旧企业 VPN 原型退出运行面、文档与 GitHub 仓库入口收敛。真实上游的名称、commit、许可证与版权声明仍保留；研究快照、运行目录、环境文件和数据库字节不进入 Git。

原阶段数据以非破坏方式保存在 Git 忽略目录。当前 schema bootstrap 不再新建旧 action 表，也不执行 DROP。

## 已通过

| 验证 | 命令 | 结果 |
|---|---|---|
| Evidence、Skill、个人集成及 replay 契约单测 | `python -m pytest backend/test/unit/evidence backend/test/unit/binizox -q` | 22 passed；replay 直接读取生产 Skill，并覆盖检索与个人笔记工具调用 |
| Parser sidecar | 在 `services/parser-sidecar` 执行 `python -m pytest test -q` | 2 passed |
| Personal Tool Runner | `python -m pytest services/personal-tool-runner/test -q` | 13 passed，2 skipped；覆盖至少 32 字符且不得复用其他安全密钥的内部凭据、用户隔离、同键并发、过期租约接管、旧 claim 拒绝结算、路径逃逸和有界读取；Windows 无 symlink/FIFO，Linux CI 保留两个负向用例 |
| Windows 本地文件边界 | `pytest test_paths.py test_filesystem.py test_workdir.py` 及 Project/Memory 相关单测 | 14 passed、6 个 POSIX/symlink 用例 skipped；Project/Memory 29 passed；原生 Windows 可导入并使用逐级拒绝 symlink 的本地路径，Linux 生产仍使用 `dir_fd + O_NOFOLLOW` |
| Compose 文件消费者边界 | `pytest ...test_docker_compose_service_boundaries.py -k "not ...POSIX-only..."` | 32 passed，2 deselected；两个仅适用于 POSIX shell 的既有用例未在 Windows 计入通过；开发与生产 Tool Runner 均受 storage-migrator 成功门控 |
| Binizox CLI | `python -m pytest packages/binizox-cli/tests -q` | 110 passed，1 skipped；Windows 无 POSIX mode 位，不能用 `0600` 断言 NTFS ACL |
| Vue lint | `corepack pnpm@11.24.0 --dir web lint:check` | passed |
| Vue unit | `corepack pnpm@11.24.0 --dir web test:unit` | 168 passed |
| Vue production build | `corepack pnpm@11.24.0 --dir web build` | passed；只有既有大 chunk 警告 |
| 文档依赖与 build | `corepack pnpm@11.24.0 --dir docs install --frozen-lockfile`、`build` | passed；VitePress/Rolldown 输出非阻断兼容警告 |
| 工程契约 | `python scripts/verify_engineering_contracts.py` | passed：59 decisions / 5 workflows / 4 AGENTS / 112 docs / 27 routers / 260 web sources |
| 工程契约负向测试 | `python -m unittest scripts.test_verify_engineering_contracts` | 61 passed，1 skipped；Windows 无符号链接权限 |
| Python 语法 | `python -m compileall` 覆盖 backend/server/CLI/parser/tool runner | passed |
| Python 包与第三方许可证 | 分别构建 backend、CLI、Personal Tool Runner wheel 并读取 zip 内容 | passed；三个 wheel 都含 Binizox `LICENSE` 与保留 Yuxi MIT 版权的 `THIRD_PARTY_NOTICES.md`；DeerFlow NOTICE 与 MIT 全文继续随 backend wheel 分发 |
| Compose 展开 | 分别对开发、Binizox override 与生产 Compose 执行 `docker compose config --quiet` | 三组退出码均为 0；生产检查临时复用被忽略的本地环境文件，检查后立即删除临时副本 |
| 旧环境凭据迁移 | `pwsh -NoProfile -File scripts/test_migrate_binizox_local_state.ps1`，并对真实迁移执行重跑 | 隔离测试证明 token 缺失/复用时生成 32 字节随机值、不输出 secret、重复迁移保持 token 和数据；真实旧数据目录均为 `target-not-empty`，未覆盖 |
| Git whitespace | `git diff --check` | passed |
| 运行时旧命名扫描 | 搜索旧 import、API、worker、Skill、Vue 与服务注册 | 仅迁移脚本和 repository 旧数据读取键保留 |

## 调用链审查

1. FastAPI 认证用户创建 Agent Run，请求和 Run 先写 PostgreSQL。
2. 提交后派发服务把可执行 Run 投递到 Redis/ARQ；Redis 不是业务终态。
3. worker 只注册 `process_agent_run`，领取后执行 LangGraph，并把 checkpoint、输出和终态写回 PostgreSQL。
4. SSE 从 Run 事件流展示过程，断线后按游标恢复；最终结果仍从持久化 Run/result 读取。
5. `search_binizox_evidence` 从 Run 身份得到用户和租户，先限制当前 Agent 可见知识库，再由 repository 过滤 `active` 文档和文档 ACL。
6. Agent 只收到过滤后的 Evidence；citation 绑定文档 ID、版本、页码/块位置和 chunk ID。
7. `save_binizox_note` 在 Human-in-the-loop 确认后，通过带内部凭据的 HTTP adapter 调用独立 Tool Runner；调用绑定用户、Run 与 tool call，固定幂等键避免重复写入。
8. Tool Runner 原子取得短租约和唯一 claim token；同键活跃请求返回 `execution_in_progress`，只有过期租约可接管，失去 claim 的旧执行者不能写终态。已有文件只做 no-follow、非阻塞、定长二进制核对。
9. Ubuntu system-test 已装配完整验收：Agent 先产生固定笔记参数并进入 `human_approval_required`，批准分支恢复 Run、查询 Tool Runner 持久执行记录并核对实际文件字节；拒绝分支核对无执行记录且无文件副作用。该流程已进入 CI，但本机因 Docker Engine 不可用尚未产生容器级通过结果。

静态审查和目标测试没有发现字段断裂。`SearchRequest.user_id/tenant_id` 在服务端派生，sidecar 不能改写已授权文档身份，未完成或已 superseded 的文档不会进入检索候选。LITE 模式不导入或公布 Evidence 路由、工具与 Skill。

## 未完成的动态验证

Docker Desktop Linux Engine 未运行：连接 `npipe:////./pipe/dockerDesktopLinuxEngine` 失败。因此没有在本机执行本轮最终容器冷启动、真实 PostgreSQL/Redis/MinIO、API + worker + LangGraph + SSE 端到端。GitHub Ubuntu system-test 已配置确定性 OpenAI-compatible replay，不依赖真实模型额度，并会验证 Evidence ACL、Agent 引用、HITL 批准/拒绝以及 Tool Runner 文件事实；在远端工作流实际成功前，这些容器场景仍记为待验证。`docker compose config --quiet` 只能证明配置可解析，不能证明容器健康。

本机 `wsl.exe` 未安装可启动的 Linux 发行版，因此 FIFO、symlink 与 POSIX mode/dir_fd 文件系统负向测试只完成了代码接线并交给 GitHub Ubuntu workflow，当前本机结果为 skipped，不能计入通过。Windows 本地分支已验证普通文件读写、原子替换、目录扫描和项目路径；它不替代 Linux 生产路径的 no-follow 测试。

Conda 镜像一度读取超时，完整锁文件同步未完成；目标测试通过环境内 pip 补齐所需依赖。依赖完整服务器导入图的 LITE 单测因此未在本机完成，新增边界将由 GitHub system-tests 的 Linux 完整环境验证。正式复现建议在网络稳定后再次执行 `scripts/conda-bootstrap.ps1 -InstallPlatform`。

`save_binizox_note` 的 citation 由 Skill 和工具参数约束，尚未在服务端强制绑定“本 Run 返回的 Evidence ID”；这是当前最小版明确限制。

## 最终本机验证

```powershell
Set-Location D:\Download\Binizox
.\scripts\conda-bootstrap.ps1 -InstallPlatform
Copy-Item .env.binizox.example .env.binizox.local
# 填写真实模型与基础设施参数，不要提交本地环境文件。

.\scripts\dev-infra-up.ps1
.\scripts\dev-parser.ps1
.\scripts\dev-tool-runner.ps1
.\scripts\dev-api.ps1
.\scripts\dev-worker.ps1
.\scripts\dev-web.ps1
.\scripts\dev-smoke.ps1
```

上传 `examples/evidence/personal-reference-v1.docx`，启用 `binizox-personal-agent` 后提问并要求保存笔记。预期回答引用实际 Evidence；写入前出现工具确认，批准后在个人工作区生成 Markdown，拒绝时无文件副作用。
