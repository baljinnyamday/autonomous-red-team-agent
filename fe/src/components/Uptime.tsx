import { useEffect, useState } from "react"

/** Format an elapsed millisecond span as H:MM:SS (or MM:SS under an hour). */
function format(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000))
  const s = total % 60
  const m = Math.floor(total / 60) % 60
  const h = Math.floor(total / 3600)
  const pad = (n: number) => String(n).padStart(2, "0")
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`
}

/** Live "how long it's been running" readout, ticking once a second. */
export function Uptime({ since }: { since: string | undefined }) {
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [])

  const elapsed = since ? now - new Date(since).getTime() : null

  return (
    <span className="font-mono text-sm tabular-nums text-foreground">
      {elapsed === null ? "—" : format(elapsed)}
    </span>
  )
}
