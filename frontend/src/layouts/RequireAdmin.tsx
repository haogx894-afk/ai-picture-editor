import { Navigate, Outlet } from 'react-router-dom'

import { useCurrentUser } from '@/hooks/useAuth'

export default function RequireAdmin() {
  const { user, isLoading } = useCurrentUser()
  if (isLoading) return <div className="text-muted flex h-screen items-center justify-center text-sm">加载中…</div>
  return user?.is_admin ? <Outlet /> : <Navigate to="/" replace />
}
