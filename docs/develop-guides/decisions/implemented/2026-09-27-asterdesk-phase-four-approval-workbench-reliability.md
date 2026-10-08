# AsterDesk 审批工作台与运行可靠性

状态：implemented
类型：feature
Owner：backend/package/yuxi/services/asterdesk_action_worker.py

## 问题

VPN 操作在外部成功、本地终态提交前中断时会留下长期 `running` attempt，无法仅凭业务数据库解释谁接管、哪次执行观察到外部结果。Docker 冷启动时 worker 可能在 PostgreSQL WAL recovery 结束前完成一次失败启动，开发热重载父进程继续存活但不再消费。审批提交后 Redis 短暂不可用时，持久执行意图虽然可由周期扫描恢复，但 API、审计和用户界面不能清楚展示 deferred 与恢复结果。审批人也缺少可用的工作台入口。

## 决策

1. business schema 升为 v4。execution attempt 新增外部结果观察时间、接管原因和 `superseded_by_attempt_no`；过期 lease 被新 worker 接管时，旧 attempt 原子结算为 `superseded`，新 attempt 记录接管来源。外部响应在 action 终态前单独落审计，使故障注入后的每次状态可解释。
2. worker 启动对 PostgreSQL 暂不可用错误采用总时长受限、单次退避有上限的重试；schema 不兼容和安全配置错误继续快速失败。恢复期间不发布 worker 健康租约，数据库可用后自动初始化并开始消费。
3. 保留 PostgreSQL 持久意图加周期扫描的补偿机制。审批事务先提交；直接 Redis 投递失败时写 `dispatch.deferred` 审计并返回可回读的已接受结果，扫描在固定周期内重新投递并写恢复审计。若实测出现不可界定遗漏，再改为 transactional outbox。
4. 审批策略由独立服务函数拥有：申请人不能自批，只有同租户 `admin/superadmin` 可审批，普通用户与跨租户管理员拒绝，申请有效期已到时申请原子转为 `expired`。现有管理员角色无需数据迁移。
5. 增加同租户过滤的审批列表 API。Vue 工作台显示待审批列表、固定参数、摘要、Evidence、执行状态、attempt 和审计，批准/拒绝后始终回读服务端状态；超时或 409 也回读详情，不做乐观终态。
6. Phase 4 使用独立 Compose project、端口和状态目录验证；不迁移或删除前三阶段数据卷。

## 替代方案

- 立即增加 transactional outbox：可靠性更强，但在现有 30 秒扫描能够从 PostgreSQL 意图自动恢复前会增加表、dispatcher 与运维面。本阶段先用故障注入测量扫描边界，再决定是否升级。
- 只靠 Compose `depends_on`：Docker daemon 冷重启不会重新执行 Compose 创建顺序，无法覆盖 WAL recovery 窗口。
- 前端直接重试审批 POST：请求可能已经提交，会增加并发噪声；工作台使用参数摘要幂等决定并回读最终事实。
- 复用 superadmin 跨租户能力：不符合业务审批的租户隔离；superadmin 保留审批角色兼容，但也必须处于申请租户。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 故障恢复后不存在长期 running attempt | 旧 attempt 未结算或无法关联接管者 | action repository/worker 与 PostgreSQL | Phase 4 故障注入 E2E 后查询 attempts/audit | 外部成功后在 action 终态前中断 | Pass：`#1 superseded -> #2`、`#2 succeeded`；running=0，外部 grant 仅一项 |
| 冷启动无需人工重启 worker | 一次连接失败使 ARQ 子进程永久退出 | run_worker startup 与 worker health lease | 真实隔离 PostgreSQL crash recovery 时间线、日志与消费结果 | worker 早于 PostgreSQL ready 启动 | Pass：第 23 次、63.274 秒恢复连接，容器 RestartCount=0，grant 8→8 |
| Redis 投递失败后自动处理 | 审批已提交但任务永久遗漏 | ActionRequest pending 意图与 reconciliation | 注入 enqueue failure，测量至 succeeded/resumed | 审批事务后拒绝直接 enqueue | Pass：5.092 秒写 `dispatch.recovered`，19.654 秒完成执行与 Run 恢复 |
| 审批权限在后端闭合 | 自批、普通用户或跨租户可改变状态 | approval policy/service 与行锁 | 两租户真实 HTTP/E2E 权限矩阵 | 四类越权审批 | Pass：自批、普通用户、跨租户均拒绝；并发决定仅一个生效 |
| Vue 能完成批准和拒绝并显示同一快照 | UI 乐观状态或参数漂移 | web API、ApprovalWorkbenchView 与后端详情 | lint/unit/build、真实浏览器 DOM 和数据库回读 | 重复点击、409、超时后回读 | Pass：真实浏览器批准一笔并执行成功、拒绝一笔且原因回显；模拟授权数 8→9，拒绝申请无 grant |
| 前三阶段关键链路不回归 | 新迁移或 worker 修改破坏旧功能 | 现有 E2E 与隔离 Compose | Phase 1/2/3 关键 E2E | 无权 Evidence、版本与幂等重放 | Pass：Phase 1 `21.82s`、Phase 2 `39.14s`、Phase 3 `174.24s`；Phase 4 `215.71s` |

## 后果

- 扫描补偿的恢复上限由配置周期、Redis 可用性和执行时间共同决定，不等同于 exactly-once；外部副作用仍依赖幂等键和 GET-before-POST。
- 外部结果观察审计在 action 终态前提交，必须保持参数摘要和外部引用最小化，不能记录政策正文或凭据。
- worker 启动重试只覆盖连接暂不可用；schema 版本错误必须快速失败，避免旧代码消费新 schema。
- 审批列表按租户和角色过滤，前端路由守卫只改善体验，不能替代服务端策略。
