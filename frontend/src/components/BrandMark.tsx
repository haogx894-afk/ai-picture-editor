import type { ReactNode } from 'react'

const GLYPH_SIZE = {
  sm: 'size-8 rounded-[9px]',
  md: 'size-10 rounded-[12px]',
} as const

/** 织像 AI 品牌标识，落地页、登录页、工作台与管理台共用。 */
export default function BrandMark({
  size = 'md',
  className = '',
  children,
}: {
  size?: keyof typeof GLYPH_SIZE
  className?: string
  children?: ReactNode
}) {
  return (
    <span className={`inline-flex items-center gap-2.5 ${className}`}>
      <span
        className={`grid shrink-0 place-items-center overflow-hidden ${GLYPH_SIZE[size]}`}
        aria-hidden
      >
        <img src="/retouchloom-mark.png" alt="" className="size-full object-contain" />
      </span>
      {children}
    </span>
  )
}
