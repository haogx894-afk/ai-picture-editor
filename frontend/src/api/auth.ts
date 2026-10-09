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

export const authApi = {
  register: (body: Credentials) => api.post<User>('/auth/register', body),
  login: (body: Credentials) => api.post<User>('/auth/login', body),
  logout: () => api.post<void>('/auth/logout'),
  me: () => api.get<User>('/auth/me'),
}
