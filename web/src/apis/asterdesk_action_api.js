import { apiAdminGet, apiAdminPost } from './base'

export const asterdeskActionApi = {
  list: ({ status = 'pending', limit = 50, offset = 0 } = {}) => {
    const query = new URLSearchParams({ status, limit: String(limit), offset: String(offset) })
    return apiAdminGet(`/api/asterdesk/actions?${query.toString()}`)
  },

  detail: (actionRequestId) =>
    apiAdminGet(`/api/asterdesk/actions/${encodeURIComponent(actionRequestId)}`),

  decide: (actionRequestId, decision) =>
    apiAdminPost(
      `/api/asterdesk/actions/${encodeURIComponent(actionRequestId)}/decision`,
      decision
    )
}
