import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import type { User, UserPlan, UserStatus } from '@/api/auth'
import { adminApi, type AdminUserPatch } from '@/api/admin'
import BrandMark from '@/components/BrandMark'
import ContactSupport from '@/components/ContactSupport'
import { errorMessage } from '@/hooks/useAuth'

const STATUS_LABELS: Record<UserStatus, string> = {
  pending: '待审核',
  approved: '已通过',
  rejected: '已拒绝',
  suspended: '已暂停',
}
const PLAN_LABELS: Record<UserPlan, string> = { free: '免费', vip: 'VIP', svip: 'SVIP' }
const USERS_KEY = ['admin', 'users']

export default function AdminPage() {
  const [filter, setFilter] = useState<UserStatus | 'all'>('pending')
  const queryClient = useQueryClient()
  const query = useQuery({
    queryKey: [...USERS_KEY, filter],
    queryFn: () => adminApi.users(filter === 'all' ? undefined : filter),
  })
  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: AdminUserPatch }) => adminApi.updateUser(id, body),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: USERS_KEY }),
  })

  const users = useMemo(() => query.data ?? [], [query.data])
  const patch = (user: User, body: AdminUserPatch) => update.mutate({ id: user.id, body })

  return (
    <div className="min-h-screen px-6 py-8 md:px-10">
      <header className="mx-auto flex max-w-6xl items-center justify-between">
        <Link to="/create" aria-label="返回工作台"><BrandMark size="sm"><span className="text-ink text-sm font-semibold">AI 修图智能体 · 管理</span></BrandMark></Link>
        <ContactSupport compact />
      </header>

      <main className="mx-auto mt-10 max-w-6xl">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-brand-strong text-xs font-semibold tracking-[0.2em] uppercase">Admin console</p>
            <h1 className="text-ink mt-2 text-3xl font-semibold tracking-tight">用户管理</h1>
            <p className="text-muted mt-2 text-sm">审核注册申请、调整套餐与使用额度。</p>
          </div>
          <select value={filter} onChange={(event) => setFilter(event.target.value as UserStatus | 'all')} className="border-line bg-paper text-ink rounded-control border px-3 py-2 text-sm">
            <option value="pending">待审核</option>
            <option value="approved">已通过</option>
            <option value="rejected">已拒绝</option>
            <option value="suspended">已暂停</option>
            <option value="all">全部用户</option>
          </select>
        </div>

        {query.isPending ? <p className="text-muted mt-8 text-sm">加载中…</p> : query.isError ? <p className="text-danger mt-8 text-sm">{errorMessage(query.error)}</p> : (
          <div className="border-line bg-paper shadow-panel mt-8 overflow-x-auto rounded-[20px] border">
            <table className="w-full min-w-[980px] text-left text-sm">
              <thead className="border-line text-muted border-b text-xs"><tr><th className="px-5 py-4">用户</th><th className="px-5 py-4">状态</th><th className="px-5 py-4">套餐</th><th className="px-5 py-4">Agent 输入</th><th className="px-5 py-4">Agent 输出</th><th className="px-5 py-4">修图次数</th></tr></thead>
              <tbody>
                {users.map((user) => <UserRow key={user.id} user={user} busy={update.isPending} onPatch={patch} />)}
              </tbody>
            </table>
            {users.length === 0 && <p className="text-muted px-5 py-10 text-center text-sm">当前筛选没有用户。</p>}
          </div>
        )}
      </main>
    </div>
  )
}

function UserRow({ user, busy, onPatch }: { user: User; busy: boolean; onPatch: (user: User, body: AdminUserPatch) => void }) {
  const [input, setInput] = useState(String(user.agent_input_limit))
  const [output, setOutput] = useState(String(user.agent_output_limit))
  const [edit, setEdit] = useState(String(user.edit_limit))
  const saveNumber = (field: keyof AdminUserPatch, value: string) => {
    const parsed = Math.max(0, Number.parseInt(value, 10) || 0)
    onPatch(user, { [field]: parsed })
  }
  return (
    <tr className="border-line border-b last:border-0">
      <td className="text-ink px-5 py-4 font-medium">{user.username}<span className="text-muted mt-1 block text-xs">{user.is_admin ? '唯一管理员' : '注册用户'}</span></td>
      <td className="px-5 py-4"><select disabled={busy || user.is_admin} value={user.status} onChange={(event) => onPatch(user, { status: event.target.value as UserStatus })} className="border-line bg-paper text-ink rounded-control border px-2 py-1.5 text-xs"><option value="pending">{STATUS_LABELS.pending}</option><option value="approved">{STATUS_LABELS.approved}</option><option value="rejected">{STATUS_LABELS.rejected}</option><option value="suspended">{STATUS_LABELS.suspended}</option></select></td>
      <td className="px-5 py-4"><select disabled={busy || user.is_admin} value={user.plan} onChange={(event) => onPatch(user, { plan: event.target.value as UserPlan })} className="border-line bg-paper text-ink rounded-control border px-2 py-1.5 text-xs"><option value="free">{PLAN_LABELS.free}</option><option value="vip">{PLAN_LABELS.vip}</option><option value="svip">{PLAN_LABELS.svip}</option></select></td>
      <QuotaCell used={user.agent_input_used} value={input} setValue={setInput} onBlur={() => saveNumber('agent_input_limit', input)} />
      <QuotaCell used={user.agent_output_used} value={output} setValue={setOutput} onBlur={() => saveNumber('agent_output_limit', output)} />
      <QuotaCell used={user.edit_used} value={edit} setValue={setEdit} onBlur={() => saveNumber('edit_limit', edit)} />
    </tr>
  )
}

function QuotaCell({ used, value, setValue, onBlur }: { used: number; value: string; setValue: (value: string) => void; onBlur: () => void }) {
  return <td className="px-5 py-4"><div className="flex items-center gap-2"><span className="text-muted text-xs">{used}/</span><input type="number" min="0" value={value} onChange={(event) => setValue(event.target.value)} onBlur={onBlur} className="border-line bg-paper text-ink rounded-control w-20 border px-2 py-1.5 text-xs" /></div></td>
}
