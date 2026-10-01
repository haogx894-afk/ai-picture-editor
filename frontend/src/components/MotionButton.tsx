import type { ButtonHTMLAttributes, ReactNode } from 'react'

type MotionButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  children: ReactNode
  tone?: 'solid' | 'soft' | 'ghost'
}

/** 一次点击即可完成的轻量微交互；FuseButton 保留给有明确完成态的主行动。 */
export default function MotionButton({ children, tone = 'solid', className = '', ...props }: MotionButtonProps) {
  return (
    <button
      {...props}
      className={`motion-button motion-button--${tone} ${className}`.trim()}
    >
      <span className="motion-button__label">{children}</span>
      <span className="motion-button__shine" aria-hidden="true" />
    </button>
  )
}
