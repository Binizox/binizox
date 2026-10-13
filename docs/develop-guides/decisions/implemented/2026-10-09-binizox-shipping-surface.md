# Binizox 独立交付面收敛

状态：implemented
类型：simplification
Owner：backend/server/routers/__init__.py

## 问题

独立个人 Agent 不应继续发布早期企业 VPN 审批原型的路由、worker、页面、Skill、模拟服务和 schema bootstrap；但其中通用的文档解析与 Evidence 权限过滤能力仍是个人知识闭环的一部分。

## 决策

- 文档上传、解析、索引和检索由 `binizox.evidence` 持有，HTTP 边界是 `/api/binizox/evidence`。
- `binizox-personal-agent` 使用 `search_binizox_evidence` 和 `save_binizox_note`，并复用同一条 Agent Run。
- 早期 VPN/action API、action worker、审批页面、企业 Skills 和模拟服务不再注册或打包。
- schema bootstrap 不再新建旧 action 表，也不对迁入数据库执行 DROP。
- 新 Evidence 元数据写入 `binizox_evidence`；repository 仅为已迁入的数据读取旧键。
- 上游项目名只保留在 attribution、许可证、固定来源和明确迁移边界中。
- 个人 Tool Runner 对幂等键使用短租约和唯一 claim token：活跃调用返回
  `execution_in_progress`，过期调用才允许接管，旧 owner 不能结算新 owner 的记录。
- Tool Runner 与其他 workspace 写入者一样，必须等待 `storage-migrator` 成功后启动；
  已有文件只以 no-follow、非阻塞和定长读取核对，拒绝 FIFO、symlink 和超大冲突文件。

## 替代方案

- 只改显示名称：后台仍会恢复和消费不再使用的企业任务。
- 把 VPN 原型直接改名为个人工具：缺少真实个人消费者，且与现有用户确认笔记工具重复。
- 删除全部早期代码：会误删已被个人 Agent 使用的解析和 Evidence 能力。

## 后果

旧企业 API 不再兼容。迁入数据库可能仍包含历史 action 表和记录，但当前代码不会读取、执行或删除它们。完整 Docker E2E 仍取决于可用的 Linux Docker Engine；测试使用确定性 replay，不依赖外部模型额度。

## 验证

- 静态搜索证明 route、worker、Skill、Vue 与 service registry 不再注册旧产品面。
- Evidence/Skill 单元测试、parser 测试和 personal Tool Runner 测试通过。
- Tool Runner 负向测试覆盖同键并发、崩溃后过期接管、旧 claim 拒绝结算、FIFO
  非阻塞拒绝及大文件定长核对；Compose 契约覆盖其迁移 gate。
- repository 单测覆盖新元数据键和旧数据只读兼容；无权限文档过滤在 repository/service 边界执行。
- Evidence system-test 直接读取生产 Skill，并装配真实 Run 中断、批准/拒绝、恢复、HTTP Tool Runner
  与工作区文件事实；远端 workflow 成功前只声明测试已接线，不声明容器验收通过。
- `git diff --check`、Vue lint/unit/build、工程契约和 Compose config 作为提交前门禁。

旧能力不存在：当前产品不发布 VPN 审批接口、页面、worker、Skill、模拟系统或新建其业务表。

重新引入条件：只有出现经过定义、具有个人使用价值的真实外部操作，并完成独立幂等、安全和恢复设计后，才以 Binizox 工具契约重新实现。
