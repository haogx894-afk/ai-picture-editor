import { useLayoutEffect, useMemo, useState, type ReactNode } from 'react'

import { useTheme } from '@/hooks/useTheme'
import { ThemeContext, type Theme } from '@/lib/themeContext'

function readTheme(): Theme {
  if (typeof window === 'undefined') return 'dark'
  const stored = window.localStorage.getItem('ai-retouch-theme')
  return stored === 'light' ? 'light' : 'dark'
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(readTheme)

  useLayoutEffect(() => {
    document.documentElement.dataset.theme = theme
    document.documentElement.style.colorScheme = theme
    window.localStorage.setItem('ai-retouch-theme', theme)
  }, [theme])

  const value = useMemo(
    () => ({
      theme,
      setTheme,
      toggleTheme: () => setTheme((current) => (current === 'dark' ? 'light' : 'dark')),
    }),
    [theme],
  )

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function ThemeToggle() {
  const { theme, toggleTheme } = useTheme()
  const isDark = theme === 'dark'

  return (
    <button
      type="button"
      onClick={toggleTheme}
      aria-label={isDark ? '切换到白天主题' : '切换到暗黑主题'}
      title={isDark ? '切换到白天主题' : '切换到暗黑主题'}
      className="theme-toggle"
    >
      <span className="theme-toggle__track" aria-hidden="true">
        <span className="theme-toggle__thumb">{isDark ? '☾' : '☼'}</span>
      </span>
      <span className="sr-only">{isDark ? '暗黑主题' : '白天主题'}</span>
    </button>
  )
}
