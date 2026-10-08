<template>
  <main class="binizox-overview">
    <section class="overview-header" aria-labelledby="binizox-title">
      <div class="brand-block">
        <img src="/favicon.svg" alt="" class="brand-mark" />
        <div>
          <p class="eyebrow">LOCAL-FIRST PERSONAL AGENT</p>
          <h1 id="binizox-title">Binizox 个人 Agent</h1>
          <p class="intro">
            在一条可恢复的 Agent Run 中连接个人知识、来源证据、操作确认和本地工具。
          </p>
        </div>
      </div>
      <div class="header-actions">
        <RouterLink to="/agent" class="primary-action lucide-icon-btn">
          <MessageSquareText :size="17" />
          开始对话
        </RouterLink>
        <RouterLink to="/workspace" class="secondary-action lucide-icon-btn">
          <HardDrive :size="17" />
          查看个人空间
        </RouterLink>
      </div>
    </section>

    <a-alert
      v-if="errorMessage"
      class="overview-error"
      type="error"
      show-icon
      :message="errorMessage"
      description="请确认 API 已启动后重试。已有对话和文件不会受本页加载失败影响。"
    >
      <template #action>
        <button type="button" class="retry-button lucide-icon-btn" @click="loadOverview">
          <RefreshCw :size="15" />
          重试
        </button>
      </template>
    </a-alert>

    <section class="runtime-section" aria-labelledby="runtime-title">
      <div class="section-heading">
        <div>
          <h2 id="runtime-title">运行链路</h2>
          <p>状态来自 Binizox FastAPI；数据库和 Run 终态仍由 Yuxi 主链持有。</p>
        </div>
        <button
          type="button"
          class="refresh-button lucide-icon-btn"
          :disabled="loading"
          @click="loadOverview"
        >
          <RefreshCw :size="16" :class="{ spinning: loading }" />
          刷新状态
        </button>
      </div>

      <div class="runtime-card">
        <div class="runtime-status">
          <span class="status-dot" :class="`tone-${toolRunnerPresentation.tone}`"></span>
          <div>
            <strong>{{ toolRunnerPresentation.label }}</strong>
            <span>写入笔记前由现有 LangGraph 确认流程展示固定参数。</span>
          </div>
        </div>
        <span v-if="productInfo?.version" class="version-tag">{{ productInfo.version }}</span>
      </div>

      <ol class="flow-list" aria-label="Binizox 个人 Agent 主流程">
        <li v-for="step in flowSteps" :key="step.title" class="flow-step">
          <component :is="step.icon" :size="19" />
          <div>
            <strong>{{ step.title }}</strong>
            <span>{{ step.description }}</span>
          </div>
          <ArrowRight class="flow-arrow" :size="16" aria-hidden="true" />
        </li>
      </ol>
    </section>

    <section class="integration-section" aria-labelledby="integration-title">
      <div class="section-heading">
        <div>
          <h2 id="integration-title">上游能力边界</h2>
          <p>只有真正进入当前运行链路的源码或服务才标记为“已运行”。</p>
        </div>
      </div>

      <div v-if="loading && !integrations.length" class="loading-state">
        <a-spin />
        <span>正在读取集成状态…</span>
      </div>
      <div v-else-if="!integrations.length" class="empty-state">
        <Boxes :size="28" />
        <strong>尚未读取到集成清单</strong>
        <span>启动 Binizox API 后刷新本页。</span>
      </div>
      <div v-else class="integration-grid">
        <article v-for="integration in integrations" :key="integration.name" class="integration-card">
          <div class="integration-card-header">
            <div>
              <h3>{{ integration.name }}</h3>
              <p>{{ integration.role }}</p>
            </div>
            <span
              class="state-tag"
              :class="`tone-${getIntegrationPresentation(integration.state).tone}`"
            >
              {{ getIntegrationPresentation(integration.state).label }}
            </span>
          </div>
          <p class="integration-boundary">{{ integration.boundary }}</p>
          <dl class="integration-meta">
            <div>
              <dt>许可证</dt>
              <dd>{{ integration.license }}</dd>
            </div>
            <div>
              <dt>固定版本</dt>
              <dd :title="integration.commit">{{ shortCommit(integration.commit) }}</dd>
            </div>
          </dl>
        </article>
      </div>
    </section>

    <section class="usage-note" aria-labelledby="usage-title">
      <ShieldCheck :size="22" />
      <div>
        <h2 id="usage-title">当前最小可用方式</h2>
        <p>
          为 Agent 启用 <code>binizox-personal-agent</code> Skill，完成文档入库和索引后提问；要求保存结果时，
          <code>save_binizox_note</code> 会先等待你的确认，再调用独立工具服务写入 Markdown。
        </p>
      </div>
    </section>
  </main>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import {
  ArrowRight,
  Boxes,
  Database,
  FilePenLine,
  HardDrive,
  MessageSquareText,
  RefreshCw,
  Search,
  ShieldCheck
} from '@lucide/vue'

import { binizoxApi } from '@/apis/binizox_api'
import { getIntegrationPresentation, getToolRunnerPresentation } from '@/utils/binizoxStatus'

const productInfo = ref(null)
const toolRunnerHealth = ref({ status: 'unknown' })
const loading = ref(false)
const errorMessage = ref('')

const integrations = computed(() =>
  Array.isArray(productInfo.value?.integrations) ? productInfo.value.integrations : []
)
const toolRunnerPresentation = computed(() =>
  getToolRunnerPresentation(toolRunnerHealth.value?.status)
)

const flowSteps = [
  { title: '文档入库', description: 'PDF / DOCX 解析并保留位置', icon: Database },
  { title: '证据检索', description: '只返回当前用户可见 Evidence', icon: Search },
  { title: '带来源回答', description: '引用本次 Run 的真实检索结果', icon: MessageSquareText },
  { title: '确认后执行', description: '幂等写入个人 Markdown 笔记', icon: FilePenLine }
]

const shortCommit = (commit) => (typeof commit === 'string' ? commit.slice(0, 12) : '未记录')

const loadOverview = async () => {
  if (loading.value) return
  loading.value = true
  errorMessage.value = ''

  try {
    const [info, health] = await Promise.all([
      binizoxApi.getInfo(),
      binizoxApi.getToolRunnerHealth()
    ])
    productInfo.value = info
    toolRunnerHealth.value = health
  } catch (error) {
    errorMessage.value = error?.message || '无法加载 Binizox 状态'
  } finally {
    loading.value = false
  }
}

onMounted(loadOverview)
</script>

<style lang="less" scoped>
.binizox-overview {
  width: 100%;
  max-width: 1240px;
  margin: 0 auto;
  padding: 32px;
  color: var(--color-text);
}

.overview-header,
.runtime-card,
.integration-card,
.usage-note {
  background: var(--gray-0);
  border: 1px solid var(--gray-150);
  border-radius: 8px;
}

.overview-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  padding: 24px;
}

.brand-block {
  display: flex;
  align-items: center;
  gap: 18px;
  min-width: 0;
}

.brand-mark {
  width: 56px;
  height: 56px;
  flex: 0 0 56px;
}

.eyebrow {
  margin: 0 0 4px;
  color: var(--main-700);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.08em;
}

h1,
h2,
h3,
p {
  margin: 0;
}

h1 {
  font-size: 24px;
  font-weight: 600;
}

h2 {
  font-size: 18px;
  font-weight: 600;
}

h3 {
  font-size: 16px;
  font-weight: 600;
}

.intro,
.section-heading p,
.integration-card-header p,
.usage-note p {
  color: var(--color-text-secondary);
}

.intro {
  margin-top: 4px;
  max-width: 660px;
  font-size: 14px;
}

.header-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.primary-action,
.secondary-action,
.retry-button,
.refresh-button {
  min-height: 38px;
  padding: 0 14px;
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
}

.primary-action {
  color: var(--gray-0);
  background: var(--main-color);
  border: 1px solid var(--main-color);
}

.secondary-action,
.refresh-button,
.retry-button {
  color: var(--color-text);
  background: var(--gray-0);
  border: 1px solid var(--gray-200);
}

.primary-action:hover {
  color: var(--gray-0);
  background: var(--main-600);
}

.secondary-action:hover,
.refresh-button:hover:not(:disabled),
.retry-button:hover {
  color: var(--main-700);
  border-color: var(--main-500);
  background: var(--main-30);
}

.refresh-button:disabled {
  color: var(--gray-400);
  cursor: not-allowed;
}

.overview-error,
.runtime-section,
.integration-section,
.usage-note {
  margin-top: 24px;
}

.section-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 12px;
}

.section-heading p {
  margin-top: 3px;
  font-size: 13px;
}

.runtime-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 18px;
}

.runtime-status {
  display: flex;
  align-items: center;
  gap: 12px;
}

.runtime-status div {
  display: flex;
  flex-direction: column;
}

.runtime-status span:not(.status-dot) {
  color: var(--color-text-secondary);
  font-size: 13px;
}

.status-dot {
  width: 10px;
  height: 10px;
  flex: 0 0 10px;
  border-radius: 999px;
}

.version-tag,
.state-tag {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 0 9px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 500;
}

.version-tag,
.tone-neutral {
  color: var(--gray-600);
  background: var(--gray-100);
}

.tone-success {
  color: var(--color-success-700);
  background: var(--color-success-50);
}

.status-dot.tone-success {
  background: var(--color-success-500);
}

.tone-info {
  color: var(--color-info-700);
  background: var(--color-info-50);
}

.tone-warning {
  color: var(--color-warning-900);
  background: var(--color-warning-50);
}

.status-dot.tone-warning {
  background: var(--color-warning-500);
}

.status-dot.tone-neutral {
  background: var(--gray-400);
}

.flow-list {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin: 12px 0 0;
  padding: 0;
  list-style: none;
}

.flow-step {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  padding: 14px;
  color: var(--main-700);
  background: var(--main-30);
  border: 1px solid var(--main-50);
  border-radius: 8px;
}

.flow-step div {
  display: flex;
  flex: 1;
  min-width: 0;
  flex-direction: column;
}

.flow-step strong {
  color: var(--color-text);
  font-size: 14px;
}

.flow-step span {
  color: var(--color-text-secondary);
  font-size: 12px;
}

.flow-arrow {
  flex: 0 0 auto;
  color: var(--gray-400);
}

.flow-step:last-child .flow-arrow {
  display: none;
}

.integration-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.integration-card {
  display: flex;
  min-width: 0;
  flex-direction: column;
  padding: 18px;
}

.integration-card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.integration-card-header p {
  margin-top: 2px;
  font-size: 12px;
}

.integration-boundary {
  flex: 1;
  margin-top: 14px;
  color: var(--color-text-secondary);
  font-size: 13px;
}

.integration-meta {
  display: flex;
  gap: 20px;
  margin: 16px 0 0;
  padding-top: 12px;
  border-top: 1px solid var(--gray-150);
}

.integration-meta div {
  min-width: 0;
}

.integration-meta dt {
  color: var(--color-text-tertiary);
  font-size: 11px;
}

.integration-meta dd {
  margin: 1px 0 0;
  overflow: hidden;
  color: var(--color-text-secondary);
  font-family: monospace;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.loading-state,
.empty-state {
  display: flex;
  min-height: 180px;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  gap: 8px;
  color: var(--color-text-secondary);
  background: var(--gray-10);
  border: 1px dashed var(--gray-200);
  border-radius: 8px;
}

.usage-note {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  padding: 18px;
  color: var(--main-700);
}

.usage-note h2 {
  color: var(--color-text);
  font-size: 16px;
}

.usage-note p {
  margin-top: 4px;
  font-size: 13px;
}

code {
  padding: 1px 4px;
  color: var(--main-700);
  background: var(--main-30);
  border-radius: 4px;
}

.spinning {
  animation: spin 0.9s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 960px) {
  .overview-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .flow-list,
  .integration-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .binizox-overview {
    padding: 20px 16px;
  }

  .overview-header {
    padding: 18px;
  }

  .brand-block {
    align-items: flex-start;
  }

  .brand-mark {
    width: 44px;
    height: 44px;
    flex-basis: 44px;
  }

  .header-actions,
  .primary-action,
  .secondary-action {
    width: 100%;
  }

  .primary-action,
  .secondary-action {
    justify-content: center;
  }

  .section-heading,
  .runtime-card {
    align-items: flex-start;
    flex-direction: column;
  }

  .flow-list,
  .integration-grid {
    grid-template-columns: 1fr;
  }

  .flow-arrow {
    display: none;
  }
}
</style>
