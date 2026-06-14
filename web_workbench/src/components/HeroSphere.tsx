import { useEffect, useRef } from 'react'

type Particle = {
  x: number
  y: number
  z: number
  drift: number
}

const labels = [
  { label: '需求', labelEn: 'Intent' },
  { label: '模型', labelEn: 'Model IR' },
  { label: '门禁', labelEn: 'Gates' },
  { label: '生成', labelEn: 'Codegen' },
  { label: '构建', labelEn: 'Build' },
  { label: '产物', labelEn: 'Artifacts' },
]

function makeParticles(count: number): Particle[] {
  const particles: Particle[] = []
  const golden = Math.PI * (3 - Math.sqrt(5))

  for (let index = 0; index < count; index += 1) {
    const y = 1 - (index / (count - 1)) * 2
    const radius = Math.sqrt(1 - y * y)
    const theta = golden * index
    particles.push({
      x: Math.cos(theta) * radius,
      y,
      z: Math.sin(theta) * radius,
      drift: (index % 37) / 37,
    })
  }

  return particles
}

export default function HeroSphere({ variant = 'hero' }: { variant?: 'hero' | 'intro' }) {
  const backCanvas = useRef<HTMLCanvasElement | null>(null)
  const frontCanvas = useRef<HTMLCanvasElement | null>(null)
  const wrap = useRef<HTMLDivElement | null>(null)
  const pointer = useRef({ x: 0, y: 0, active: false })

  useEffect(() => {
    const container = wrap.current
    const back = backCanvas.current
    const front = frontCanvas.current
    if (!container || !back || !front) {
      return undefined
    }

    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const backContext = back.getContext('2d')
    const frontContext = front.getContext('2d')
    if (!backContext || !frontContext) {
      return undefined
    }

    let frame = 0
    let width = 0
    let height = 0
    let dpr = 1
    let particles = makeParticles(900)

    const resize = () => {
      const box = container.getBoundingClientRect()
      width = Math.max(260, box.width)
      height = Math.max(260, box.height)
      dpr = Math.min(window.devicePixelRatio || 1, 2)
      for (const canvas of [back, front]) {
        canvas.width = Math.floor(width * dpr)
        canvas.height = Math.floor(height * dpr)
        canvas.style.width = `${width}px`
        canvas.style.height = `${height}px`
      }
      backContext.setTransform(dpr, 0, 0, dpr, 0, 0)
      frontContext.setTransform(dpr, 0, 0, dpr, 0, 0)
      particles = makeParticles(width < 520 ? 560 : 1200)
    }

    const drawRing = (context: CanvasRenderingContext2D, radius: number, squash: number) => {
      context.beginPath()
      context.ellipse(width / 2, height / 2, radius, radius * squash, 0, 0, Math.PI * 2)
      context.stroke()
    }

    const render = (time: number) => {
      backContext.clearRect(0, 0, width, height)
      frontContext.clearRect(0, 0, width, height)
      const baseRadius = Math.min(width, height) * 0.34
      const centerX = width / 2
      const centerY = height / 2
      const intro = variant === 'intro' || reduced ? 1 : Math.min(1, time / 1200)
      const spin = reduced ? 0.72 : time * 0.00022
      const tiltX = pointer.current.active ? pointer.current.y * 0.26 : -0.1
      const tiltY = pointer.current.active ? pointer.current.x * 0.3 : 0.2

      for (const context of [backContext, frontContext]) {
        context.lineWidth = 1
        context.strokeStyle = 'rgba(23, 22, 20, 0.12)'
        drawRing(context, baseRadius * intro, 0.34)
        drawRing(context, baseRadius * 0.72 * intro, 0.82)
      }

      for (const particle of particles) {
        const angle = spin + particle.drift * 0.08
        const sinY = Math.sin(angle + tiltY)
        const cosY = Math.cos(angle + tiltY)
        const sinX = Math.sin(tiltX)
        const cosX = Math.cos(tiltX)

        let x = particle.x * cosY - particle.z * sinY
        let z = particle.x * sinY + particle.z * cosY
        const y = particle.y * cosX - z * sinX
        z = particle.y * sinX + z * cosX

        const dx = x - pointer.current.x * 0.22
        const dy = y - pointer.current.y * 0.22
        const distance = Math.sqrt(dx * dx + dy * dy)
        if (pointer.current.active && distance < 0.36) {
          const push = (0.36 - distance) * 0.18
          x += dx * push
        }

        const perspective = 1.48 / (1.85 + z)
        const screenX = centerX + x * baseRadius * perspective * intro
        const screenY = centerY + y * baseRadius * perspective * intro
        const alpha = z > 0 ? 0.76 : 0.24
        const size = (z > 0 ? 1.6 : 1.05) * perspective
        const context = z > 0 ? frontContext : backContext

        context.beginPath()
        context.fillStyle = z > 0 ? `rgba(185, 65, 56, ${alpha})` : `rgba(23, 22, 20, ${alpha})`
        context.arc(screenX, screenY, Math.max(0.7, size), 0, Math.PI * 2)
        context.fill()
      }

      if (!reduced) {
        frame = window.requestAnimationFrame(render)
      }
    }

    const updatePointer = (event: PointerEvent) => {
      const box = container.getBoundingClientRect()
      pointer.current = {
        x: ((event.clientX - box.left) / box.width - 0.5) * 2,
        y: ((event.clientY - box.top) / box.height - 0.5) * 2,
        active: true,
      }
    }

    const clearPointer = () => {
      pointer.current.active = false
    }

    const resizeObserver = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(resize) : null

    resize()
    resizeObserver?.observe(container)
    window.addEventListener('resize', resize)
    container.addEventListener('pointermove', updatePointer)
    container.addEventListener('pointerleave', clearPointer)
    frame = window.requestAnimationFrame(render)

    return () => {
      window.cancelAnimationFrame(frame)
      resizeObserver?.disconnect()
      window.removeEventListener('resize', resize)
      container.removeEventListener('pointermove', updatePointer)
      container.removeEventListener('pointerleave', clearPointer)
    }
  }, [variant])

  return (
    <div className={`hero-sphere hero-sphere-${variant}`} ref={wrap} aria-hidden="true">
      <canvas ref={backCanvas} />
      <canvas ref={frontCanvas} />
      {labels.map((item, index) => (
        <span className={`sphere-label sphere-label-${index + 1}`} key={item.label}>
          <strong>{item.label}</strong>
          <small>{item.labelEn}</small>
        </span>
      ))}
    </div>
  )
}
