import { apiGet } from './base'

/**
 * Binizox 产品状态接口。
 * 工具服务只能由 FastAPI 代理访问，浏览器不会读取或拼接其内部地址。
 */
export const binizoxApi = {
  getInfo: () => apiGet('/api/binizox/info'),
  getToolRunnerHealth: () => apiGet('/api/binizox/tool-runner/health')
}
