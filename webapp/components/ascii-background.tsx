'use client'

import { useEffect, useRef } from 'react'

const CHARS = '+-=*.:·#@%><=~^|/\\{}[]'

interface AsciiBackgroundProps {
  variant?: 'dark' | 'light'
}

export function AsciiBackground({ variant = 'dark' }: AsciiBackgroundProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    let animId: number
    let frame = 0

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const setup = () => {
      const dpr = window.devicePixelRatio || 1
      const rect = canvas.parentElement?.getBoundingClientRect()
      if (!rect) return
      canvas.width = rect.width * dpr
      canvas.height = rect.height * dpr
      canvas.style.width = `${rect.width}px`
      canvas.style.height = `${rect.height}px`
    }

    setup()

    const isLight = variant === 'light'

    const draw = () => {
      const dpr = window.devicePixelRatio || 1
      const rect = canvas.parentElement?.getBoundingClientRect()
      if (!rect) { animId = requestAnimationFrame(draw); return }

      const w = rect.width
      const h = rect.height

      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      ctx.clearRect(0, 0, w, h)

      const fontSize = isLight ? 13 : 14
      const charW = isLight ? 7.8 : 8.4
      const lineH = fontSize + (isLight ? 4 : 3)
      ctx.font = `${fontSize}px "SF Mono", "Fira Code", "Courier New", monospace`

      const cols = Math.ceil(w / charW) + 1
      const rows = Math.ceil(h / lineH) + 1
      // Light variant animates slower for subtlety
      const speed = isLight ? 0.003 : 0.005
      const t = frame * speed

      for (let y = 0; y < rows; y++) {
        for (let x = 0; x < cols; x++) {
          const w1 = Math.sin(x * 0.035 + t * 1.1) * Math.cos(y * 0.02 + t * 0.6)
          const w2 = Math.sin((x + y) * 0.015 + t * 1.5) * 0.6
          const w3 = Math.cos(x * 0.06 - t * 0.35) * Math.sin(y * 0.04 + t * 0.2)
          const w4 = Math.sin(x * 0.012 + y * 0.018 + t * 0.9) * 0.4

          const rowStream = Math.sin(y * 0.3 + t * 2) * 0.15

          const combined = (w1 + w2 + w3 + w4) * 0.22 + rowStream

          let alpha: number
          if (isLight) {
            // Very faint for light backgrounds
            alpha = Math.max(0, combined * 0.18 + 0.015)
            // Even more aggressive threshold so fewer chars render
            if (alpha < 0.03) continue
            // Cap alpha so nothing gets too dark
            alpha = Math.min(alpha, 0.09)
          } else {
            alpha = Math.max(0, combined * 0.35 + 0.03)
            if (alpha < 0.025) continue
          }

          const seed = Math.sin(x * 7.1 + y * 13.3 + Math.floor(t * 1.5) * 0.3)
          const charIdx = Math.abs(Math.floor(seed * 100)) % CHARS.length

          if (isLight) {
            // Grey on white — faint with subtle warmth
            ctx.fillStyle = `rgba(160, 160, 170, ${alpha})`
          } else {
            const brightness = 120 + alpha * 80
            ctx.fillStyle = `rgba(${brightness}, ${brightness + 8}, ${brightness + 20}, ${alpha})`
          }

          ctx.fillText(CHARS[charIdx], x * charW, y * lineH + fontSize)
        }
      }

      frame++
      animId = requestAnimationFrame(draw)
    }

    draw()
    window.addEventListener('resize', setup)
    return () => {
      cancelAnimationFrame(animId)
      window.removeEventListener('resize', setup)
    }
  }, [variant])

  return (
    <canvas
      ref={canvasRef}
      className="absolute inset-0 w-full h-full pointer-events-none"
    />
  )
}
