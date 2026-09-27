<template>
  <div class="approval-page">
    <header class="page-header">
      <div>
        <h1>审批工作台</h1>
        <p>审批固定参数的 VPN 权限申请，并查看执行与恢复审计。</p>
      </div>
      <div class="header-actions">
        <a-select v-model:value="statusFilter" class="status-filter" @change="loadActions">
          <a-select-option value="pending">待审批</a-select-option>
          <a-select-option value="approved,rejected,expired">已处理</a-select-option>
          <a-select-option value="pending,approved,rejected,expired">全部</a-select-option>
        </a-select>
        <a-button :loading="listLoading" @click="loadActions">
          <RefreshCw :size="16" />
          刷新
        </a-button>
      </div>
    </header>

    <div class="workbench-grid">
      <section class="request-panel" aria-label="申请列表">
        <div v-if="listError" class="inline-error" role="alert">
          <AlertCircle :size="18" />
          <span>{{ listError }}</span>
          <a-button type="link" @click="loadActions">重试</a-button>
        </div>
        <a-spin :spinning="listLoading">
          <a-empty v-if="!actions.length && !listLoading" description="当前筛选下没有申请" />
          <button
            v-for="action in actions"
            :key="action.action_request_id"
            type="button"
            class="request-row"
            :class="{ selected: action.action_request_id === selectedId }"
            @click="selectAction(action.action_request_id)"
          >
            <div class="row-heading">
              <strong>{{ action.applicant_uid }}</strong>
              <span :class="['status-pill', `status-${action.status}`]">
                {{ statusLabel(action.status) }}
              </span>
            </div>
            <div class="row-summary">
              {{ scopeLabel(action.permission_scope) }} · 至 {{ action.valid_until }}
            </div>
            <div class="row-meta">目标用户 {{ action.target_user_uid }}</div>
          </button>
        </a-spin>
      </section>

      <section class="detail-panel" aria-label="申请详情">
        <a-spin :spinning="detailLoading">
          <a-empty v-if="!selectedAction && !detailLoading" description="选择一笔申请查看详情" />
          <template v-else-if="selectedAction">
            <div class="detail-heading">
              <div>
                <h2>VPN 权限申请</h2>
                <span :class="['status-pill', `status-${selectedAction.status}`]">
                  {{ statusLabel(selectedAction.status) }}
                </span>
              </div>
              <span :class="['execution-pill', `execution-${selectedAction.execution_status}`]">
                {{ executionLabel(selectedAction.execution_status) }}
              </span>
            </div>

            <div class="summary-grid">
              <div><span>申请人</span><strong>{{ selectedAction.applicant_uid }}</strong></div>
              <div><span>目标用户</span><strong>{{ selectedAction.target_user_uid }}</strong></div>
              <div><span>权限范围</span><strong>{{ scopeLabel(selectedAction.permission_scope) }}</strong></div>
              <div><span>有效期</span><strong>{{ selectedAction.valid_until }}</strong></div>
              <div v-if="selectedAction.decision_by_uid">
                <span>审批人</span><strong>{{ selectedAction.decision_by_uid }}</strong>
              </div>
              <div v-if="selectedAction.decision_reason">
                <span>审批原因</span><strong>{{ selectedAction.decision_reason }}</strong>
              </div>
            </div>

            <section class="detail-section">
              <h3>固定工具参数</h3>
              <p class="section-help">审批前后使用同一份快照；执行器按摘要重新校验。</p>
              <dl class="parameter-list">
                <template v-for="(value, key) in selectedAction.normalized_parameters" :key="key">
                  <dt>{{ parameterLabel(key) }}</dt>
                  <dd>{{ value }}</dd>
                </template>
              </dl>
              <div class="digest-block">
                <span>参数摘要</span>
                <code>{{ selectedAction.parameter_digest }}</code>
              </div>
            </section>

            <section class="detail-section">
              <h3>政策依据</h3>
              <div v-for="evidence in selectedAction.policy_evidence" :key="evidence.chunk_id" class="evidence-row">
                <FileText :size="17" />
                <div>
                  <strong>{{ evidence.citation }}</strong>
                  <p>{{ evidence.title || evidence.document_id }}</p>
                  <small>{{ locationLabel(evidence) }}</small>
                </div>
              </div>
            </section>

            <section v-if="selectedAction.execution_attempts?.length" class="detail-section">
              <h3>执行尝试</h3>
              <div v-for="attempt in selectedAction.execution_attempts" :key="attempt.attempt_no" class="timeline-row">
                <span class="timeline-dot"></span>
                <div>
                  <strong>#{{ attempt.attempt_no }} · {{ attemptLabel(attempt.status) }}</strong>
                  <p>
                    {{ formatTime(attempt.started_at) }}
                    <template v-if="attempt.recovery_reason"> · {{ attempt.recovery_reason }}</template>
                    <template v-if="attempt.superseded_by_attempt_no">
                      · 由 #{{ attempt.superseded_by_attempt_no }} 接管
                    </template>
                  </p>
                  <small v-if="attempt.external_reference_id">外部引用 {{ attempt.external_reference_id }}</small>
                </div>
              </div>
            </section>

            <section class="detail-section">
              <h3>审计时间线</h3>
              <div v-for="(event, index) in selectedAction.audit" :key="`${event.event_type}-${index}`" class="timeline-row">
                <span class="timeline-dot"></span>
                <div>
                  <strong>{{ auditLabel(event.event_type) }}</strong>
                  <p>{{ formatTime(event.created_at) }} · {{ event.actor_id }}</p>
                  <small v-if="event.details?.reason">
                    {{ event.details.reason }}
                  </small>
                  <small v-else-if="event.details?.reason_code">{{ event.details.reason_code }}</small>
                </div>
              </div>
            </section>

            <div v-if="selectedAction.status === 'pending'" class="decision-bar">
              <a-button danger :disabled="decisionBusy" @click="openReject">拒绝</a-button>
              <a-popconfirm
                title="确认按当前固定参数批准？"
                ok-text="批准"
                cancel-text="取消"
                :disabled="decisionBusy"
                @confirm="submitDecision('approved')"
              >
                <a-button type="primary" :loading="decisionBusy">批准申请</a-button>
              </a-popconfirm>
            </div>
          </template>
        </a-spin>
      </section>
    </div>

    <a-modal
      v-model:open="rejectOpen"
      title="拒绝 VPN 申请"
      ok-text="确认拒绝"
      cancel-text="取消"
      :confirm-loading="decisionBusy"
      @ok="submitDecision('rejected')"
    >
      <label class="reject-label" for="reject-reason">拒绝原因</label>
      <a-textarea
        id="reject-reason"
        v-model:value="rejectReason"
        :maxlength="2000"
        :rows="4"
        placeholder="说明缺少的材料或拒绝依据"
      />
    </a-modal>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import { AlertCircle, FileText, RefreshCw } from '@lucide/vue'
import { asterdeskActionApi } from '@/apis/asterdesk_action_api'

const actions = ref([])
const selectedId = ref('')
const selectedAction = ref(null)
const statusFilter = ref('pending')
const listLoading = ref(false)
const detailLoading = ref(false)
const decisionBusy = ref(false)
const listError = ref('')
const rejectOpen = ref(false)
const rejectReason = ref('')

const statusLabels = { pending: '待审批', approved: '已批准', rejected: '已拒绝', expired: '已过期' }
const executionLabels = {
  not_requested: '未执行',
  pending: '待投递',
  executing: '执行中',
  succeeded: '执行成功',
  unknown: '结果待确认',
  failed: '执行失败',
  rejected: '执行被拒绝'
}
const parameterLabels = {
  target_user_uid: '目标用户',
  target_system: '目标系统',
  permission_scope: '权限范围',
  valid_until: '有效期',
  business_reason: '业务理由',
  device_asset_id: '设备资产编号',
  manager_approval_reference: '经理确认单号'
}
const auditLabels = {
  'action.created': '申请已创建',
  'approval.approved': '审批已批准',
  'approval.rejected': '审批已拒绝',
  'approval.denied': '审批操作被拒绝',
  'dispatch.enqueued': '执行任务已投递',
  'dispatch.deferred': '投递失败，等待扫描补偿',
  'dispatch.recovered': '扫描已恢复投递',
  'execution.attempt.started': '执行 attempt 开始',
  'execution.attempt.superseded': '过期 attempt 已被接管',
  'execution.external.observed': '已观察到外部结果',
  'execution.succeeded': '外部结果已确认',
  'run.resume.created': 'Agent Run 已恢复'
}

const statusLabel = (value) => statusLabels[value] || value
const executionLabel = (value) => executionLabels[value] || value
const scopeLabel = (value) => ({ vpn_standard: '标准 VPN', vpn_privileged: '特权 VPN' })[value] || value
const parameterLabel = (value) => parameterLabels[value] || value
const auditLabel = (value) => auditLabels[value] || value
const attemptLabel = (value) =>
  ({ running: '运行中', succeeded: '已确认', unknown: '结果未知', superseded: '已被接管', rejected: '被拒绝', conflict: '冲突' })[value] || value
const formatTime = (value) => (value ? new Date(value).toLocaleString() : '—')
const locationLabel = (evidence) => {
  const location = evidence.location || {}
  const page = location.page_start ? `第 ${location.page_start} 页` : '无页码'
  const heading = evidence.heading_path?.length ? evidence.heading_path.join(' / ') : '正文'
  return `${page} · ${heading} · ${evidence.document_id} v${evidence.document_version}`
}

const loadActions = async () => {
  listLoading.value = true
  listError.value = ''
  try {
    const result = await asterdeskActionApi.list({ status: statusFilter.value })
    actions.value = result.items || []
    if (!actions.value.some((item) => item.action_request_id === selectedId.value)) {
      selectedId.value = actions.value[0]?.action_request_id || ''
    }
    if (selectedId.value) await loadDetail(selectedId.value)
    else selectedAction.value = null
  } catch {
    listError.value = '审批列表加载失败，请稍后重试。'
  } finally {
    listLoading.value = false
  }
}

const loadDetail = async (actionRequestId) => {
  detailLoading.value = true
  try {
    selectedAction.value = await asterdeskActionApi.detail(actionRequestId)
  } catch {
    selectedAction.value = null
    message.error('申请详情加载失败')
  } finally {
    detailLoading.value = false
  }
}

const selectAction = async (actionRequestId) => {
  selectedId.value = actionRequestId
  await loadDetail(actionRequestId)
}

const openReject = () => {
  rejectReason.value = ''
  rejectOpen.value = true
}

const submitDecision = async (decision) => {
  if (!selectedAction.value || decisionBusy.value) return
  if (decision === 'rejected' && !rejectReason.value.trim()) {
    message.warning('请填写拒绝原因')
    return
  }
  decisionBusy.value = true
  const actionRequestId = selectedAction.value.action_request_id
  try {
    await asterdeskActionApi.decide(actionRequestId, {
      decision,
      reason: decision === 'rejected' ? rejectReason.value.trim() : null,
      parameter_digest: selectedAction.value.parameter_digest
    })
    rejectOpen.value = false
    message.success(decision === 'approved' ? '申请已批准' : '申请已拒绝')
  } catch (error) {
    message.warning(
      error?.status === 409 ? '申请状态已变化，已回读最新结果' : '请求结果不确定，已回读服务端状态'
    )
  } finally {
    await loadDetail(actionRequestId)
    await loadActions()
    decisionBusy.value = false
  }
}

onMounted(loadActions)
</script>

<style scoped lang="less">
.approval-page {
  min-height: 100%;
  padding: 24px;
  background: var(--gray-10);
  color: var(--color-text);
}

.page-header,
.detail-heading,
.row-heading,
.decision-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.page-header {
  margin-bottom: 20px;

  h1 {
    margin: 0;
    font-size: 24px;
  }

  p {
    margin: 6px 0 0;
    color: var(--color-text-secondary);
  }
}

.header-actions {
  display: flex;
  gap: 8px;

  :deep(.ant-btn) {
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
}

.status-filter {
  width: 140px;
}

.workbench-grid {
  display: grid;
  grid-template-columns: minmax(260px, 360px) minmax(0, 1fr);
  gap: 16px;
  align-items: start;
}

.request-panel,
.detail-panel {
  background: var(--gray-0);
  border: 1px solid var(--gray-150);
  border-radius: 8px;
}

.request-panel {
  overflow: hidden;
}

.request-row {
  display: block;
  width: 100%;
  padding: 16px;
  border: 0;
  border-bottom: 1px solid var(--gray-100);
  background: transparent;
  color: inherit;
  text-align: left;
  cursor: pointer;

  &:hover,
  &:focus-visible {
    background: var(--gray-25);
  }

  &.selected {
    background: var(--main-10);
    box-shadow: inset 3px 0 0 var(--main-color);
  }
}

.row-summary {
  margin-top: 8px;
  font-size: 14px;
}

.row-meta,
.section-help,
.timeline-row p,
.evidence-row p {
  margin: 4px 0 0;
  color: var(--color-text-secondary);
  font-size: 13px;
}

.detail-panel {
  min-height: 420px;
  padding: 20px;
}

.detail-heading {
  padding-bottom: 16px;
  border-bottom: 1px solid var(--gray-100);

  h2 {
    display: inline-block;
    margin: 0 10px 0 0;
    font-size: 20px;
  }
}

.status-pill,
.execution-pill {
  display: inline-flex;
  padding: 3px 9px;
  border-radius: 999px;
  background: var(--gray-100);
  color: var(--gray-600);
  font-size: 12px;
  font-weight: 500;
}

.status-pending,
.execution-pending,
.execution-executing,
.execution-unknown {
  background: var(--color-warning-50);
  color: var(--color-warning-900);
}

.status-approved,
.execution-succeeded {
  background: var(--color-success-50);
  color: var(--color-success-700);
}

.status-rejected,
.status-expired,
.execution-failed,
.execution-rejected {
  background: var(--color-error-50);
  color: var(--color-error-700);
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin: 18px 0;

  div {
    padding: 12px;
    border: 1px solid var(--gray-100);
    border-radius: 6px;
    background: var(--gray-10);
  }

  span,
  strong {
    display: block;
  }

  span {
    margin-bottom: 4px;
    color: var(--color-text-secondary);
    font-size: 12px;
  }
}

.detail-section {
  padding: 18px 0;
  border-top: 1px solid var(--gray-100);

  h3 {
    margin: 0 0 10px;
    font-size: 16px;
  }
}

.parameter-list {
  display: grid;
  grid-template-columns: 150px minmax(0, 1fr);
  margin: 14px 0;

  dt,
  dd {
    margin: 0;
    padding: 8px 10px;
    border-bottom: 1px solid var(--gray-100);
  }

  dt {
    color: var(--color-text-secondary);
  }

  dd {
    overflow-wrap: anywhere;
  }
}

.digest-block {
  padding: 10px;
  border-radius: 6px;
  background: var(--gray-25);

  span {
    display: block;
    margin-bottom: 5px;
    color: var(--color-text-secondary);
    font-size: 12px;
  }

  code {
    overflow-wrap: anywhere;
    font-size: 12px;
  }
}

.evidence-row,
.timeline-row {
  display: flex;
  gap: 10px;
  padding: 9px 0;
}

.evidence-row small,
.timeline-row small {
  color: var(--color-text-tertiary);
}

.timeline-dot {
  width: 9px;
  height: 9px;
  margin-top: 6px;
  flex: 0 0 auto;
  border-radius: 50%;
  background: var(--main-color);
}

.decision-bar {
  position: sticky;
  bottom: 0;
  margin: 16px -20px -20px;
  padding: 14px 20px;
  border-top: 1px solid var(--gray-150);
  background: var(--gray-0);
  justify-content: flex-end;
}

.inline-error {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  color: var(--color-error-700);
}

.reject-label {
  display: block;
  margin-bottom: 8px;
  font-weight: 500;
}

@media (max-width: 900px) {
  .workbench-grid {
    grid-template-columns: 1fr;
  }

  .request-panel {
    max-height: 320px;
    overflow: auto;
  }
}

@media (max-width: 600px) {
  .approval-page {
    padding: 14px;
  }

  .page-header,
  .header-actions {
    align-items: stretch;
    flex-direction: column;
  }

  .status-filter {
    width: 100%;
  }

  .summary-grid {
    grid-template-columns: 1fr;
  }

  .parameter-list {
    grid-template-columns: 1fr;

    dt {
      border-bottom: 0;
      padding-bottom: 0;
    }
  }
}
</style>
