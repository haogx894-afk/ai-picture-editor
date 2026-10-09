import { useState } from 'react'

// Use the bundled QR image by default; deployments can override it with a URL.
const QR_URL = (import.meta.env.VITE_CONTACT_QQ_QR_URL as string | undefined) || '/qq-qr.jpg'

export default function ContactSupport({ compact = false }: { compact?: boolean }) {
  const [open, setOpen] = useState(false)

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className={compact ? 'text-muted hover:text-brand-strong text-xs transition-colors' : 'motion-button motion-button--ghost min-h-9 px-3 text-sm'}
      >
        联系客服
      </button>
      {open && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/45 px-6" role="presentation" onClick={() => setOpen(false)}>
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="contact-support-title"
            className="border-line bg-paper shadow-panel w-full max-w-sm rounded-[24px] border p-6 text-center"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-center justify-between gap-4 text-left">
              <div>
                <h2 id="contact-support-title" className="text-ink text-lg font-semibold">联系客服</h2>
                <p className="text-muted mt-1 text-xs">添加 QQ，获取人工帮助</p>
              </div>
              <button type="button" onClick={() => setOpen(false)} className="text-muted hover:text-ink text-xl" aria-label="关闭">×</button>
            </div>
            {QR_URL ? (
              <img src={QR_URL} alt="QQ 联系二维码" className="mx-auto mt-6 size-56 rounded-2xl object-contain" />
            ) : (
              <div className="border-line bg-soft text-muted mx-auto mt-6 grid size-56 place-items-center rounded-2xl border p-6 text-sm leading-relaxed">
                管理员尚未配置 QQ 二维码
              </div>
            )}
            <p className="text-ink mt-5 text-sm font-medium">请扫码添加微信，备注“AI 修图”</p>
            <p className="text-muted mt-1 text-xs">工作时间内会尽快回复你的问题</p>
          </section>
        </div>
      )}
    </>
  )
}
