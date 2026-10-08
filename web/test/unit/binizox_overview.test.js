import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import test from 'node:test'

import {
  getIntegrationPresentation,
  getToolRunnerPresentation
} from '../../src/utils/binizoxStatus.js'

const readSource = (relativePath) => fs.readFile(new URL(relativePath, import.meta.url), 'utf8')

test('Binizox 集成状态对未知值采用保守展示', () => {
  assert.deepEqual(getIntegrationPresentation('active'), { label: '已运行', tone: 'success' })
  assert.deepEqual(getIntegrationPresentation('candidate'), { label: '候选', tone: 'warning' })
  assert.deepEqual(getIntegrationPresentation('unexpected'), {
    label: '状态未确认',
    tone: 'neutral'
  })
})

test('工具服务只有明确 ok 才显示为可用', () => {
  assert.equal(getToolRunnerPresentation('ok').tone, 'success')
  assert.equal(getToolRunnerPresentation('unavailable').tone, 'warning')
  assert.equal(getToolRunnerPresentation('unexpected').tone, 'neutral')
})

test('总览通过 FastAPI API 模块读取状态且不直连工具服务', async () => {
  const apiSource = await readSource('../../src/apis/binizox_api.js')
  const viewSource = await readSource('../../src/views/BinizoxOverviewView.vue')

  assert.match(apiSource, /\/api\/binizox\/info/)
  assert.match(apiSource, /\/api\/binizox\/tool-runner\/health/)
  assert.doesNotMatch(apiSource, /8091|BINIZOX_TOOL_RUNNER_URL/)
  assert.match(viewSource, /errorMessage/)
  assert.match(viewSource, /@click="loadOverview"/)
  assert.match(viewSource, /v-else-if="!integrations\.length"/)
})

test('Binizox 总览进入登录后 shipping 路由和侧栏导航', async () => {
  const routerSource = await readSource('../../src/router/index.js')
  const layoutSource = await readSource('../../src/layouts/AppLayout.vue')

  assert.match(routerSource, /path: '\/binizox'/)
  assert.match(routerSource, /name: 'BinizoxOverview'/)
  assert.match(routerSource, /requiresAuth: true/)
  assert.match(layoutSource, /name: 'Binizox 总览'/)
  assert.match(layoutSource, /path: '\/binizox'/)
})
