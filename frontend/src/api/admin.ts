import type { User, UserPlan, UserStatus } from '@/api/auth'
import { api } from '@/api/client'

export type AdminUserPatch = {
  status?: UserStatus
  plan?: UserPlan
  agent_input_limit?: number
  agent_output_limit?: number
  edit_limit?: number
}

export const adminApi = {
  users: (status?: UserStatus) =>
    api.get<User[]>(`/admin/users${status ? `?status=${status}` : ''}`),
  updateUser: (id: string, body: AdminUserPatch) => api.patch<User>(`/admin/users/${id}`, body),
}
