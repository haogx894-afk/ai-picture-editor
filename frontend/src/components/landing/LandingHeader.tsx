import { Link } from 'react-router-dom'

import BrandMark from '@/components/BrandMark'
import ContactSupport from '@/components/ContactSupport'
import { ThemeToggle } from '@/components/ThemeProvider'

export default function LandingHeader({ account }: { account: string | null }) {
  return (
    <header className="border-line/70 bg-canvas/80 sticky top-0 z-10 border-b backdrop-blur">
      <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-3.5">
        <Link to="/" aria-label="AI 修图智能体首页">
          <BrandMark size="sm">
            <span className="text-ink text-sm font-semibold">AI 修图智能体</span>
          </BrandMark>
        </Link>

        <div className="flex items-center gap-3">
          <ThemeToggle />
          <ContactSupport compact />
          {account ? (
            <Link
              to="/create"
              className="motion-button motion-button--soft min-h-9 px-3 text-xs"
            >
              {account} · 进入工作台
            </Link>
          ) : (
            <Link to="/auth" className="motion-button motion-button--ghost min-h-9 px-3 text-sm">
              登录
            </Link>
          )}
        </div>
      </div>
    </header>
  )
}
