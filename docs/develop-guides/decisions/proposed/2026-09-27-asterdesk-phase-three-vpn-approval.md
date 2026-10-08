# AsterDesk VPN 审批、执行与恢复边界

状态：proposed
类型：architecture
Owner：backend/package/yuxi/services/asterdesk_action_service.py

## 问题

第三阶段需要让 Agent 生成 VPN 申请并等待独立审批人决定，在批准后由 worker 调用外部系统；重复投递、外部成功后本地崩溃和 API/worker 重启都不能重复授权。现有 Yuxi 已有 PostgreSQL AgentRun、LangGraph checkpoint、`interrupted` 终态和 resume Run，不能另建一套脱离 Run 的 Agent 生命周期。

## 提案

1. `request_vpn_access` 工具先把规范化参数、摘要和当前用户可见的 Evidence 固化为 `ActionRequest`，再调用 LangGraph `interrupt`。原 Run 由现有 worker 固化为 `interrupted/human_approval_required`。
2. 审批事实使用独立表和行锁。申请人不能自批；审批人必须是同租户 admin 或 superadmin。`pending` 只允许一次原子转为 `approved` 或 `rejected`。
3. 批准事务同时写入 approval、`execution_status=pending` 和审计事件；ARQ 通知在提交后发送。周期 reconciliation 扫描持久 pending/unknown 意图，避免 commit 后 enqueue 前崩溃造成丢失。
4. VPN 模拟器是独立 FastAPI + SQLite 服务。worker 只能经 `VpnToolAdapter` 调用；adapter 在副作用前重新读取 approval、参数摘要、租户和审批角色。
5. 外部幂等键由 ActionRequest ID 和参数摘要确定。worker 每次先按 business request ID 查询；POST 超时或连接中断后再次查询，无法判定时保存 `unknown`，不直接当失败重做。
6. 外部结果成为确定终态后，worker 使用原 interrupted Run 创建标准 Yuxi resume Run。恢复后的工具只读取持久 ActionRequest/ToolResult，最终 Message、Run、checkpoint 和 SSE 继续由现有链路持有。
7. 第三阶段 schema 升为 business v3，只在独立 `asterdesk-phase3` 数据目录验证。第一、二阶段卷不迁移、不删除。

## 替代方案

- 不让审批 API 直接调用 VPN 服务：这会绕过 worker、重试和执行审计。
- 不使用现有通用文件/命令 HumanInTheLoopMiddleware 作为业务审批事实：它只保存 checkpoint 中断，不能表达审批角色、固定参数、外部幂等和审计。
- 不把 ActionRequest 当第二套 Agent 任务：它是 Run 关联的业务副作用状态，Agent 生命周期仍由原 Run 与 resume Run 表达。

## 验收标准

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 迁移与并发审批在真实 PostgreSQL 上闭合 | 只验证进程内状态或重复保存决定 | business schema 与 action repository | Phase 3 迁移和并发审批 integration | 并发批准与拒绝 | Inspected |
| AgentRun 能暂停、审批后执行并恢复 | 绕过 worker 或另建任务状态 | action service、worker 与 Run repository | FastAPI、Redis、worker、LangGraph、SQLite 模拟器 E2E | 拒绝、自批、无权限审批 | Inspected |
| 重复投递与外部成功后中断不重复授权 | 只断言本地调用次数 | VPN adapter、模拟器幂等记录与 attempt 审计 | 九场景故障注入及数据库回读 | 外部成功、本地终态提交前中断 | Inspected |

上述三项的“Inspected”表示本次仅核对了历史 Phase 3 记录与代码，未在当前 Binizox 本地环境重跑该故障注入 E2E。

## 风险

- 外部系统只能提供 at-least-once 调用边界；确定结果依赖固定幂等键和执行前后的结果查询。
- ActionRequest 是 Run 关联的业务副作用状态，后续修改不得把它扩展成第二套 Agent 生命周期。
- 历史验收结果不能替代当前分支回归；修改审批、worker 或迁移后必须重新运行对应 integration 与 E2E。
