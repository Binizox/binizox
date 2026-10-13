# Binizox 个人能力装配与总览

状态：proposed
类型：feature
Owner：backend/package/binizox/agents/skills/buildin/__init__.py

## 问题

Binizox 已经实现个人知识检索、受确认保护的笔记写入和独立工具服务，但 `binizox-personal-agent` 目录没有注册到内置 Skill 清单，启动同步不会创建该 Skill，模型因而无法沿预期入口获得两个依赖工具。登录后的界面也没有能够说明这些能力是否可用的产品入口，用户只能从聊天页猜测接线状态，无法区分真实运行的上游能力、已准备适配器和仍停留在研究阶段的候选项。

## 提案

把 `binizox-personal-agent` 注册为内置 Skill，并明确绑定 `search_binizox_evidence` 与 `save_binizox_note`，使现有 Skill 同步和按需工具门控真正装配它。检索工具把模型给出的知识库 ID 与当前 Agent 已启用且用户可见的范围求交集；参数留空时使用这份服务端范围。增加一个所有登录用户可访问的 Binizox 总览页；页面通过前端 API 模块读取后端拥有的产品能力清单和工具服务健康状态，展示个人 Agent 的主流程、真实集成状态、下一步入口及可恢复的 loading、empty 和 error 状态。侧栏增加明确导航入口，并使用仓库内 SVG 标识与 Binizox 默认信息配置强化产品身份，但不改变 Yuxi 的 AgentRun、知识库、审批中间件或旧 VPN 工作台语义。

后端继续作为上游集成状态和工具服务健康的事实 Owner；浏览器不读取工具服务内部地址，也不自行推断集成是否完成。

## 替代方案

- 只修改标题和登录页文案：改动更小，但用户仍不能检查个人能力的真实接线状态。
- 把旧 `/approvals` 页面直接改成 Binizox 工作台：会混淆 VPN 业务审批和 LangGraph 工具确认两种不同语义，并增加不必要的迁移风险。
- 新建另一套个人 Agent 后端：会产生第二套 Run 和状态体系，不符合继续使用 Yuxi 主链路的目标。

## 验收标准

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 内置同步能够创建 Binizox Skill 并绑定两个工具 | 只有目录和提示词，shipping Skill 清单没有注册 | `backend/package/binizox/agents/skills/buildin/__init__.py` | 后端契约测试 | 删除 Skill spec 后测试变红 | Passed |
| 检索不能越过当前 Agent 的知识库范围 | 模型提交任意可猜测 ID 扩大检索范围 | `backend/package/binizox/personal/search_scope.py` | 后端正向与负向 unit | 请求不可见 ID 时结果为空 | Passed |
| 登录用户能从侧栏进入 Binizox 总览 | 路由存在但未进入 shipping 导航 | `web/src/router/index.js`、`web/src/layouts/AppLayout.vue` | Vue router/unit 测试与真实页面检查 | 删除导航项后测试变红 | Passed |
| 页面只展示后端声明的真实集成范围 | 前端硬编码把候选描述为已集成 | `backend/package/binizox/personal/integrations.py`、`web/src/apis/binizox_api.js` | 后端契约测试与前端状态映射 unit | 未知状态必须以保守文案展示 | Passed |
| 工具服务不可用时页面仍可恢复 | 请求失败导致白屏或把不可用显示为正常 | `web/src/views/BinizoxOverviewView.vue` | 前端组件/unit 测试 | 模拟 API rejection 后显示错误和重试入口 | Inspected |
| 浏览器不接触工具服务内部地址 | 前端直接访问 8091 或显示内部 URL | `backend/server/routers/binizox_router.py` | 代码搜索、前端 API 测试 | 搜索禁止出现工具服务直连地址 | Passed |
| 新页面遵循现有主题和响应式约束 | 固定浅色、溢出或不可操作 | 页面 LESS 与真实 DOM | lint、build、浅/深色及窄屏截图 | 375px 检查长文本与操作入口 | Not run |

## 风险

- Docker Desktop 不可用时无法完成 Compose 全栈和真实页面验证，必须把该范围记录为 `Not run`，不能以构建结果替代。
- 上游状态属于开发快照事实；如果提交发生变化，必须先更新后端固定清单和对应测试，不能在页面另存一份版本。
- 总览页只提供观察和导航，不替代聊天中的 LangGraph 工具确认，也不把旧 VPN 审批工作台重新包装成个人工具审批。
