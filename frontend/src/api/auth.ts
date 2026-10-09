import { api } from '@/api/client'

export type UserStatus = 'pending' | 'approved' | 'rejected' | 'suspended'
export type UserPlan = 'free' | 'vip' | 'svip'
export type User = {
  id: string
  username: string
  status: UserStatus
  is_admin: boolean
  plan: UserPlan
  agent_input_limit: number
  agent_input_used: number
  agent_output_limit: number
  agent_output_used: number
  edit_limit: number
  edit_used: number
}
export type Credentials = { username: string; password: string }

type ApiUser = {
  id: string
  username: string
  status?: UserStatus
  is_admin?: boolean
  plan?: UserPlan
  agent_input_limit?: number
  agent_input_used?: number
  agent_output_limit?: number
  agent_output_used?: number
  edit_limit?: number
  edit_used?: number
}

/** 兼容历史镜像只返回 id/username 的认证响应。 */
function normalizeUser(user: ApiUser): User {
  return {
    id: user.id,
    username: user.username,
    status: user.status ?? 'approved',
    is_admin: user.is_admin ?? false,
    plan: user.plan ?? 'free',
    agent_input_limit: user.agent_input_limit ?? 0,
    agent_input_used: user.agent_input_used ?? 0,
    agent_output_limit: user.agent_output_limit ?? 0,
    agent_output_used: user.agent_output_used ?? 0,
    edit_limit: user.edit_limit ?? 0,
    edit_used: user.edit_used ?? 0,
  }
}

export const authApi = {
  register: (body: Credentials) => api.post<ApiUser>('/auth/register', body).then(normalizeUser),
  login: (body: Credentials) => api.post<ApiUser>('/auth/login', body).then(normalizeUser),
  logout: () => api.post<void>('/auth/logout'),
  me: () => api.get<ApiUser>('/auth/me').then(normalizeUser),
}
