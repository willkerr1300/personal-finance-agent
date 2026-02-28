"use client"

import { useEffect, useState } from "react"

interface Alert {
  id: string
  alert_type: "schedule_change" | "price_drop" | "cancellation" | string
  message: string
  details?: Record<string, unknown>
  is_read: boolean
  created_at: string
}

interface Props {
  tripId: string
}

function AlertIcon({ type }: { type: string }) {
  if (type === "price_drop") {
    return (
      <svg className="w-4 h-4 shrink-0 mt-0.5 text-emerald-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
      </svg>
    )
  }
  return (
    <svg className="w-4 h-4 shrink-0 mt-0.5 text-amber-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
    </svg>
  )
}

export function TripAlerts({ tripId }: Props) {
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [dismissed, setDismissed] = useState<Set<string>>(new Set())

  useEffect(() => {
    async function fetchAlerts() {
      try {
        const res = await fetch(`/api/trips/${tripId}/alerts`)
        if (res.ok) {
          const data: Alert[] = await res.json()
          setAlerts(data)
        }
      } catch {
        // silently ignore
      }
    }

    fetchAlerts()
    // Re-poll every 5 minutes for new alerts
    const id = setInterval(fetchAlerts, 5 * 60 * 1000)
    return () => clearInterval(id)
  }, [tripId])

  async function dismiss(alertId: string) {
    setDismissed((prev) => new Set([...prev, alertId]))
    try {
      await fetch(`/api/trips/${tripId}/alerts/${alertId}/read`, { method: "POST" })
    } catch {
      // best-effort
    }
  }

  const visible = alerts.filter((a) => !dismissed.has(a.id))
  if (visible.length === 0) return null

  return (
    <div className="mb-6 space-y-3">
      {visible.map((alert) => {
        const isPriceDrop = alert.alert_type === "price_drop"
        return (
          <div
            key={alert.id}
            className={`rounded-xl border px-4 py-3 flex items-start gap-3 ${
              isPriceDrop
                ? "bg-emerald-50 border-emerald-200"
                : "bg-amber-50 border-amber-200"
            }`}
          >
            <AlertIcon type={alert.alert_type} />
            <div className="flex-1 min-w-0">
              <p className={`text-sm leading-snug ${isPriceDrop ? "text-emerald-800" : "text-amber-800"}`}>
                {alert.message}
              </p>
              <p className="text-xs text-zinc-400 mt-1">
                {new Date(alert.created_at).toLocaleString()}
              </p>
            </div>
            <button
              onClick={() => dismiss(alert.id)}
              className={`text-xs font-medium shrink-0 ${
                isPriceDrop ? "text-emerald-600 hover:text-emerald-800" : "text-amber-600 hover:text-amber-800"
              }`}
            >
              Dismiss
            </button>
          </div>
        )
      })}
    </div>
  )
}
