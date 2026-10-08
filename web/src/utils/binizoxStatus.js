const INTEGRATION_PRESENTATIONS = Object.freeze({
  active: Object.freeze({ label: '已运行', tone: 'success' }),
  adapter_ready: Object.freeze({ label: '适配完成', tone: 'info' }),
  candidate: Object.freeze({ label: '候选', tone: 'warning' }),
  reference: Object.freeze({ label: '架构参考', tone: 'neutral' })
})

const UNKNOWN_PRESENTATION = Object.freeze({ label: '状态未确认', tone: 'neutral' })

export function getIntegrationPresentation(state) {
  return INTEGRATION_PRESENTATIONS[state] || UNKNOWN_PRESENTATION
}

export function getToolRunnerPresentation(status) {
  if (status === 'ok') return { label: '个人工具服务可用', tone: 'success' }
  if (status === 'unavailable') return { label: '个人工具服务未连接', tone: 'warning' }
  return { label: '个人工具服务状态未知', tone: 'neutral' }
}
