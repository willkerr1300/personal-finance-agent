"use client"

import { useState } from "react"

interface ModifyResult {
  success: boolean
  modification_type: string
  message: string
  updated_details?: Record<string, unknown> | null
}

interface Props {
  tripId: string
}

const EXAMPLES = [
  "Extend my hotel by 2 nights",
  "Upgrade to business class",
  "Upgrade my room to a suite",
  "Shorten my hotel stay by 1 night",
]

export function ModifyTrip({ tripId }: Props) {
  const [request, setRequest] = useState("")
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<ModifyResult | null>(null)
  const [open, setOpen] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!request.trim()) return
    setLoading(true)
    setResult(null)
    try {
      const res = await fetch(`/api/trips/${tripId}/modify`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ request: request.trim() }),
      })
      const data = await res.json()
      if (!res.ok) {
        setResult({ success: false, modification_type: "error", message: data.detail ?? "Request failed" })
      } else {
        setResult(data as ModifyResult)
        if (data.success) setRequest("")
      }
    } catch {
      setResult({ success: false, modification_type: "error", message: "Network error — please try again." })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="rounded-2xl border border-zinc-200 bg-white shadow-sm overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full px-6 py-4 flex items-center justify-between text-left"
      >
        <div>
          <h2 className="text-base font-semibold text-zinc-900">Modify this trip</h2>
          <p className="text-xs text-zinc-500 mt-0.5">Extend your hotel, upgrade your seat, or change your room.</p>
        </div>
        <svg
          className={`w-4 h-4 text-zinc-400 transition-transform ${open ? "rotate-180" : ""}`}
          fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {open && (
        <div className="px-6 pb-6 border-t border-zinc-100">
          {/* Examples */}
          <div className="mt-4 flex flex-wrap gap-2 mb-4">
            {EXAMPLES.map((ex) => (
              <button
                key={ex}
                onClick={() => setRequest(ex)}
                className="rounded-full border border-zinc-200 px-3 py-1 text-xs text-zinc-600 hover:border-zinc-400 hover:text-zinc-900 transition-colors"
              >
                {ex}
              </button>
            ))}
          </div>

          <form onSubmit={submit} className="space-y-3">
            <textarea
              value={request}
              onChange={(e) => setRequest(e.target.value)}
              placeholder='Describe the change, e.g. "Extend my hotel by 2 nights"'
              rows={2}
              className="w-full rounded-xl border border-zinc-200 px-4 py-3 text-sm text-zinc-900 placeholder:text-zinc-400 focus:outline-none focus:ring-2 focus:ring-zinc-900 resize-none"
            />
            <button
              type="submit"
              disabled={loading || !request.trim()}
              className="rounded-xl bg-zinc-900 px-5 py-2.5 text-sm font-medium text-white hover:bg-zinc-700 transition-colors disabled:opacity-40"
            >
              {loading ? "Applying…" : "Apply change"}
            </button>
          </form>

          {result && (
            <div className={`mt-4 rounded-xl px-4 py-3 text-sm ${
              result.success
                ? "bg-green-50 border border-green-200 text-green-800"
                : "bg-red-50 border border-red-200 text-red-700"
            }`}>
              {result.message}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
