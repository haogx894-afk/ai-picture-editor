import { api } from '@/api/client'
import type { RunStatus } from '@/api/runs'

export type StepStatus =
  | 'pending'
  | 'waiting'
  | 'queued'
  | 'running'
  | 'succeeded'
  | 'failed'
  | 'canceled'

export type PlanStep = {
  id: string
  tool: string
  label: string
  depends_on: string[]
  run_id: string | null
  status: StepStatus
}

export type TurnActivity = {
  phase:
    | 'planning'
    | 'executing'
    | 'awaiting_confirmation'
    | 'completed'
    | 'failed'
    | 'canceled'
  message: string
  completed_steps: number
  total_steps: number
  current_step_id: string | null
}

export type Turn = {
  id: string
  resumed_from_id: string | null
  continuation_rounds: number
  auto_continue: boolean
  revision: number
  goal: string
  reply: string
  status: RunStatus
  error: string | null
  created_at: string
  steps: PlanStep[]
  activity: TurnActivity
  /** 仅前端乐观消息使用，服务端 Turn 不会返回该字段。 */
  optimistic?: boolean
}

export const agentApi = {
  turns: (sessionId: string) => api.get<Turn[]>(`/sessions/${sessionId}/messages`),
  send: (sessionId: string, text: string) =>
    api.post<Turn>(`/sessions/${sessionId}/messages`, { text }),
  confirm: (sessionId: string, turnId: string) =>
    api.post<Turn>(`/sessions/${sessionId}/messages/${turnId}/confirm`),
  cancel: (sessionId: string, turnId: string) =>
    api.post<Turn>(`/sessions/${sessionId}/messages/${turnId}/cancel`),
  retry: (sessionId: string, turnId: string) =>
    api.post<Turn>(`/sessions/${sessionId}/messages/${turnId}/retry`),
}
