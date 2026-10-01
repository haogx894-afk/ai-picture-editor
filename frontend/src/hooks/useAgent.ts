import { useEffect, useRef } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { agentApi, type Turn } from '@/api/agent'
import { isTerminal } from '@/api/runs'

const turnsKey = (sessionId: string) => ['session', sessionId, 'messages']

function useRefreshTurn(sessionId: string) {
  const queryClient = useQueryClient()
  return () => {
    void queryClient.invalidateQueries({ queryKey: turnsKey(sessionId) })
    void queryClient.invalidateQueries({ queryKey: ['session', sessionId] })
    void queryClient.invalidateQueries({ queryKey: ['session', sessionId, 'history'] })
  }
}

export function useTurns(sessionId: string) {
  const queryClient = useQueryClient()
  const query = useQuery({
    queryKey: turnsKey(sessionId),
    queryFn: () => agentApi.turns(sessionId),
    // 第一步 SSE 结束时下一步可能还没写进计划，整轮 running 时接着拉，避免卡片停在「等待中」
    refetchInterval: (current) => {
      const latest = current.state.data?.at(-1)
      return latest?.status === 'running' && !latest?.optimistic ? 800 : false
    },
  })

  const latest = query.data?.at(-1)?.status
  const previous = useRef(latest)
  useEffect(() => {
    const wasRunning = previous.current === 'running'
    previous.current = latest
    if (!wasRunning || !latest || !isTerminal(latest)) return
    void queryClient.invalidateQueries({ queryKey: ['session', sessionId] })
    void queryClient.invalidateQueries({ queryKey: ['session', sessionId, 'history'] })
  }, [latest, sessionId, queryClient])

  useEffect(() => {
    previous.current = undefined
  }, [sessionId])

  return query
}

export function useSendMessage(sessionId: string) {
  const queryClient = useQueryClient()
  const refresh = useRefreshTurn(sessionId)
  return useMutation({
    mutationFn: (text: string) => agentApi.send(sessionId, text),
    onMutate: async (text) => {
      await queryClient.cancelQueries({ queryKey: turnsKey(sessionId) })
      const previous = queryClient.getQueryData<Turn[]>(turnsKey(sessionId))
      const optimistic: Turn = {
        id: `optimistic-${crypto.randomUUID()}`,
        resumed_from_id: null,
        continuation_rounds: 0,
        auto_continue: false,
        revision: 0,
        goal: text,
        reply: '',
        status: 'running',
        error: null,
        created_at: new Date().toISOString(),
        steps: [],
        activity: {
          phase: 'planning',
          message: '正在理解你的要求并制定执行计划…',
          completed_steps: 0,
          total_steps: 0,
          current_step_id: null,
        },
        optimistic: true,
      }
      queryClient.setQueryData<Turn[]>(turnsKey(sessionId), (turns = []) => [...turns, optimistic])
      return {
        optimisticId: optimistic.id,
        previous,
      }
    },
    onSuccess: (turn, _text, context) => {
      queryClient.setQueryData<Turn[]>(turnsKey(sessionId), (turns = []) =>
        turns.map((item) => (item.id === context?.optimisticId ? turn : item)),
      )
    },
    onError: (_error, _text, context) => {
      if (!context) return
      if (context.previous === undefined) {
        queryClient.removeQueries({ queryKey: turnsKey(sessionId), exact: true })
      } else {
        queryClient.setQueryData(turnsKey(sessionId), context.previous)
      }
    },
    onSettled: refresh,
  })
}

export function usePlanActions(sessionId: string) {
  const refresh = useRefreshTurn(sessionId)
  const confirm = useMutation({
    mutationFn: (turnId: string) => agentApi.confirm(sessionId, turnId),
    onSuccess: refresh,
  })
  const cancel = useMutation({
    mutationFn: (turnId: string) => agentApi.cancel(sessionId, turnId),
    onSuccess: refresh,
  })
  const retry = useMutation({
    mutationFn: (turnId: string) => agentApi.retry(sessionId, turnId),
    onSuccess: refresh,
  })
  return {
    confirm: (turnId: string) => confirm.mutate(turnId),
    cancel: (turnId: string) => cancel.mutate(turnId),
    retry: (turnId: string) => retry.mutate(turnId),
    busy: confirm.isPending || cancel.isPending || retry.isPending,
  }
}
