import { lazy, Suspense, useRef, useState } from 'react'

import PromptComposer from './PromptComposer'
import { useTheme } from '@/hooks/useTheme'

const MicroSlats = lazy(() => import('@/components/MicroSlats'))

const SCENARIOS = [
  {
    label: '商品主图',
    prompt: '把这件商品放在纯白背景上，居中构图，柔和顶光，边缘干净，输出 1:1 主图。',
  },
  {
    label: '场景氛围图',
    prompt: '把商品放到温暖的木质桌面场景，侧逆光、浅景深，保留商品原有材质与颜色。',
  },
  {
    label: '模特上身',
    prompt: '生成模特手持该商品的半身展示图，简洁室内背景、自然光，商品细节清晰可辨。',
  },
  {
    label: '促销海报',
    prompt: '做一张大促海报：主标题「新品首发」，副标题「限时 8 折」，突出商品，右侧留出文字区。',
  },
  {
    label: '多尺寸物料',
    prompt: '基于这张商品图输出一套投放物料，包含 1:1、4:5、9:16 三个尺寸，主体不被裁切。',
  },
]

const FACTS = ['无需设计经验', '支持 JPG / PNG / WebP', '1:1 / 4:5 / 9:16 一次导出']

export default function LandingHero({
  initialPrompt,
  submitLabel,
  onStart,
}: {
  initialPrompt: string
  submitLabel: string
  onStart: (prompt: string) => void
}) {
  const [prompt, setPrompt] = useState(initialPrompt)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const { theme } = useTheme()
  const dark = theme === 'dark'

  const pick = (text: string) => {
    setPrompt(text)
    inputRef.current?.focus()
  }

  return (
    <section className={`landing-hero relative isolate min-h-[680px] overflow-hidden ${dark ? 'bg-[#120f17]' : 'bg-[#f2eef8]'}`}>
      <div className="absolute inset-0 z-0 opacity-90" aria-hidden>
        <Suspense fallback={<div className="size-full bg-[#120f17]" />}>
          <MicroSlats
            preset="swell"
            color={dark ? '#A855F7' : '#8b5cc7'}
            glintColor="#ffffff"
            backgroundColor={dark ? '#120f17' : '#f2eef8'}
            slatWidth={10}
            slatHeight={25}
            gap={3}
            roundness={0.75}
            interactive
            cursorStrength={1}
            cursorSize={40}
            swirl={0}
            trail={1.4}
            lean={0}
            intro
            scale={1.5}
            speed={0.6}
            direction={250}
            chop={0.55}
            stretch={0}
            glint={0.7}
            contrast={1.25}
            perspective={0.55}
            fog={0.55}
            introDuration={1.5}
            paused={false}
          />
        </Suspense>
      </div>
      <div
        className={`pointer-events-none absolute inset-0 z-[1] ${
          dark
            ? 'bg-[linear-gradient(90deg,rgba(18,15,23,0.94)_0%,rgba(18,15,23,0.58)_42%,rgba(18,15,23,0.18)_100%)]'
            : 'bg-[linear-gradient(90deg,rgba(242,238,248,0.94)_0%,rgba(242,238,248,0.58)_42%,rgba(242,238,248,0.16)_100%)]'
        }`}
        aria-hidden
      />

      <div className="relative z-10 mx-auto grid max-w-6xl gap-12 px-6 py-20 lg:grid-cols-[1.05fr_0.95fr] lg:items-center lg:gap-20 lg:px-10 lg:py-28">
        <div>
          <p
          className={`animate-rise inline-flex items-center gap-2 rounded-full border px-3.5 py-1.5 text-xs backdrop-blur ${dark ? 'border-white/20 bg-white/10 text-white/75' : 'border-[#6a4d8d]/20 bg-white/45 text-[#4e3764]'}`}
          style={{ animationDelay: '40ms' }}
          >
          <span className="bg-accent size-1.5 rounded-full shadow-[0_0_12px_rgba(232,255,119,0.8)]" aria-hidden />
          面向电商运营与内容创作者
          </p>

          <h1
          className={`animate-rise mt-6 max-w-xl text-[2.5rem] leading-[1.05] font-semibold tracking-[-0.045em] text-balance sm:text-[3.8rem] lg:text-[5.3rem] ${dark ? 'text-white' : 'text-[#241e2d]'}`}
          style={{ animationDelay: '120ms' }}
          >
          一句话，
          <br />
          交付
          <span className="relative mx-1 whitespace-nowrap">
            {/* CJK 字身占满字框，高亮块需覆盖整个字高才像马克笔而非删除线 */}
            <span
              className="bg-brand/80 absolute inset-x-[-7px] top-[14%] bottom-[8%] -skew-x-6 rounded-[3px] shadow-[0_0_36px_rgba(168,85,247,0.6)]"
              aria-hidden
            />
            <span className={`relative ${dark ? 'text-white' : 'text-[#241e2d]'}`}>可上架</span>
          </span>
          <br />
          的商品物料
          </h1>

          <p
          className={`animate-rise mt-6 max-w-xl leading-relaxed ${dark ? 'text-white/70' : 'text-[#574b62]'}`}
          style={{ animationDelay: '200ms' }}
          >
          描述需求即可从零生成，也可上传商品图继续编辑。抠图、换背景、局部精修、扩图、图层拆分与多尺寸导出，全部由智能体自动编排。
          </p>
        </div>

        <div>
          <div className="animate-rise max-w-3xl" style={{ animationDelay: '280ms' }}>
          <PromptComposer
            value={prompt}
            onChange={setPrompt}
            onSubmit={() => onStart(prompt)}
            onAttach={() => onStart(prompt)}
            submitLabel={submitLabel}
            placeholder="描述你想要的商品图，例：把这双跑鞋放到清晨的城市街道，侧逆光，输出 1:1 主图与 9:16 竖版…"
            inputRef={inputRef}
          />
          </div>

          <div
          className="animate-rise mt-5 flex flex-wrap gap-2"
          style={{ animationDelay: '360ms' }}
        >
          {SCENARIOS.map((scenario) => (
            <button
              key={scenario.label}
              type="button"
              onClick={() => pick(scenario.prompt)}
              className={`hover:border-brand focus-visible:ring-brand/60 rounded-full border px-3.5 py-1.5 text-xs transition-[border-color,color,box-shadow] focus-visible:ring-2 focus-visible:outline-none ${dark ? 'border-white/20 bg-white/10 text-white/70 hover:text-white' : 'border-[#6a4d8d]/20 bg-white/50 text-[#574b62] hover:text-[#4e3764]'}`}
            >
              {scenario.label}
            </button>
          ))}
          </div>

          <ul
          className={`animate-rise mt-10 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs ${dark ? 'text-white/50' : 'text-[#6d6079]'}`}
          style={{ animationDelay: '440ms' }}
        >
          {FACTS.map((fact) => (
            <li key={fact} className="flex items-center gap-1.5">
              <span className="bg-brand size-1 rounded-full" aria-hidden />
              {fact}
            </li>
          ))}
          </ul>
        </div>
      </div>
    </section>
  )
}
