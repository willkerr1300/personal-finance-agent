"use client"

import { useState, FormEvent } from "react"
import { useRouter } from "next/navigation"

export function TripRequestForm() {
  const router = useRouter()
  const [request, setRequest] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!request.trim()) return

    setLoading(true)
    setError(null)

    try {
      const res = await fetch("/api/trips", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ raw_request: request }),
      })

      const data = await res.json()

      if (!res.ok) {
        setError(data.detail ?? "Something went wrong. Please try again.")
        return
      }

      router.push(`/trips/${data.id}`)
    } catch {
      setError("Network error — is the backend running?")
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <textarea
        value={request}
        onChange={(e) => setRequest(e.target.value)}
        placeholder='Try: "Fly me to Tokyo in October, 10 days, under $3,000, hotel near Shinjuku"'
        rows={3}
        disabled={loading}
        className="w-full rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-3 text-sm text-zinc-800 placeholder-zinc-400 focus:outline-none focus:ring-2 focus:ring-zinc-900 disabled:opacity-50 resize-none"
      />

      {error && (
        <p className="text-sm text-red-500">{error}</p>
      )}

      <button
        type="submit"
        disabled={loading || !request.trim()}
        className="rounded-xl bg-zinc-900 px-6 py-2.5 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
      >
        {loading ? "Searching…" : "Search trips"}
      </button>

      {loading && (
        <p className="text-xs text-zinc-400">
          Parsing your request and searching flights + hotels — this takes a few seconds.
        </p>
      )}
    </form>
  )
}
