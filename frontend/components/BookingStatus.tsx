"use client"

import { useEffect, useRef, useState } from "react"
import Link from "next/link"

interface AgentLog {
  step: string
  action: string
  result: string
  error_message?: string
  created_at: string
}

interface Booking {
  id: string
  type: "flight" | "hotel" | string
  status: "pending" | "in_progress" | "confirmed" | "failed" | "unsupported" | string
  confirmation_number?: string
  logs: AgentLog[]
}

interface Props {
  tripId: string
  initialStatus: string
}

const TERMINAL = new Set(["confirmed", "failed", "unsupported"])

function isAllDone(bookings: Booking[]) {
  return bookings.length > 0 && bookings.every((b) => TERMINAL.has(b.status))
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    pending:     "bg-zinc-100 text-zinc-500",
    in_progress: "bg-blue-50 text-blue-700",
    confirmed:   "bg-green-50 text-green-700",
    failed:      "bg-red-50 text-red-600",
    unsupported: "bg-amber-50 text-amber-700",
  }
  const label: Record<string, string> = {
    pending:     "Pending",
    in_progress: "In progress…",
    confirmed:   "Confirmed",
    failed:      "Failed",
    unsupported: "Not supported",
  }
  return (
    <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${map[status] ?? "bg-zinc-100 text-zinc-500"}`}>
      {label[status] ?? status}
    </span>
  )
}

function Spinner() {
  return (
    <div className="w-4 h-4 border-2 border-blue-600 border-t-transparent rounded-full animate-spin shrink-0" />
  )
}

function LogTimeline({ logs }: { logs: AgentLog[] }) {
  if (!logs.length) return null

  return (
    <ol className="mt-3 space-y-1.5 border-l-2 border-zinc-100 pl-4">
      {logs.map((log, i) => (
        <li key={i} className="relative">
          <span
            className={`absolute -left-[1.31rem] top-1.5 w-2 h-2 rounded-full border-2 border-white ${
              log.result === "error"
                ? "bg-red-500"
                : log.result === "success"
                ? "bg-green-500"
                : "bg-blue-400"
            }`}
          />
          <p className={`text-xs leading-relaxed ${
            log.result === "error" ? "text-red-600" : "text-zinc-600"
          }`}>
            {log.action}
          </p>
          {log.error_message && (
            <p className="text-xs text-red-500 mt-0.5">{log.error_message}</p>
          )}
        </li>
      ))}
    </ol>
  )
}

export function BookingStatus({ tripId, initialStatus }: Props) {
  const [bookings, setBookings] = useState<Booking[]>([])
  const [loading, setLoading] = useState(false)
  const [bookError, setBookError] = useState<string | null>(null)
  const [started, setStarted] = useState(
    // If the trip is already in a booking state, start polling immediately
    ["booking", "confirmed", "booking_failed"].includes(initialStatus)
  )
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Fetch current booking state
  async function fetchBookings() {
    try {
      const res = await fetch(`/api/trips/${tripId}/bookings`)
      if (res.ok) {
        const data: Booking[] = await res.json()
        setBookings(data)
        return data
      }
    } catch {
      // silently ignore poll errors
    }
    return []
  }

  // Start the booking agent
  async function triggerBooking() {
    setBookError(null)
    setLoading(true)
    try {
      const res = await fetch(`/api/trips/${tripId}/book`, { method: "POST" })
      const data = await res.json()
      if (!res.ok) {
        setBookError(data.detail ?? "Failed to start booking")
        return
      }
      setStarted(true)
    } catch {
      setBookError("Network error — please try again")
    } finally {
      setLoading(false)
    }
  }

  // Set up polling once booking is started
  useEffect(() => {
    if (!started) return

    // Fetch immediately
    fetchBookings().then((data) => {
      if (isAllDone(data)) return
      // Then poll every 3 s until all bookings reach a terminal state
      pollingRef.current = setInterval(async () => {
        const latest = await fetchBookings()
        if (isAllDone(latest)) {
          if (pollingRef.current) clearInterval(pollingRef.current)
        }
      }, 3_000)
    })

    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [started, tripId])

  // ---- Render: "Book this trip" button (trip is approved, not yet booking) ----
  if (!started) {
    return (
      <div className="rounded-2xl border border-zinc-200 bg-white p-6 shadow-sm">
        <h2 className="text-base font-semibold text-zinc-900 mb-1">Ready to book</h2>
        <p className="text-sm text-zinc-500 mb-5">
          The agent will navigate to the airline and hotel sites and complete your
          bookings using your saved profile and a single-use virtual card.
          Make sure your{" "}
          <Link href="/profile" className="underline underline-offset-2 hover:text-zinc-900">
            profile
          </Link>{" "}
          has your first name, last name, and any loyalty numbers filled in.
          Supported carriers: United, Delta, American, Southwest.
        </p>
        {bookError && (
          <p className="text-sm text-red-600 mb-3">{bookError}</p>
        )}
        <button
          onClick={triggerBooking}
          disabled={loading}
          className="rounded-xl bg-zinc-900 px-6 py-3 text-sm font-medium text-white hover:bg-zinc-700 transition-colors disabled:opacity-40"
        >
          {loading ? "Starting…" : "Book this trip"}
        </button>
      </div>
    )
  }

  // ---- Render: booking in progress or complete ----
  const allDone = isAllDone(bookings)
  const allConfirmed = allDone && bookings.every((b) => b.status === "confirmed")
  const anyFailed = bookings.some((b) => b.status === "failed" || b.status === "unsupported")

  return (
    <div className="rounded-2xl border border-zinc-200 bg-white shadow-sm overflow-hidden">
      {/* Header */}
      <div className={`px-6 py-4 border-b border-zinc-100 flex items-center gap-3 ${
        allConfirmed ? "bg-green-50" : anyFailed ? "bg-red-50" : "bg-white"
      }`}>
        {!allDone && <Spinner />}
        <div>
          <h2 className="text-base font-semibold text-zinc-900">
            {allConfirmed
              ? "Booking confirmed"
              : anyFailed && allDone
              ? "Booking partially failed"
              : "Booking in progress…"}
          </h2>
          <p className="text-xs text-zinc-500 mt-0.5">
            {allDone
              ? "The agent has finished. Check your email for confirmation details."
              : "The agent is working — this page updates automatically."}
          </p>
        </div>
      </div>

      {/* Per-booking panels */}
      <div className="divide-y divide-zinc-100">
        {bookings.length === 0 ? (
          <div className="px-6 py-8 text-center text-sm text-zinc-400">
            Starting up the booking agent…
          </div>
        ) : (
          bookings.map((booking) => (
            <div key={booking.id} className="px-6 py-5">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-zinc-900 capitalize">
                    {booking.type}
                  </span>
                  {booking.status === "in_progress" && <Spinner />}
                </div>
                <StatusBadge status={booking.status} />
              </div>

              {booking.confirmation_number && (
                <div className="mb-3 rounded-lg bg-green-50 border border-green-100 px-4 py-2.5">
                  <p className="text-xs text-green-700 font-medium">Confirmation number</p>
                  <p className="text-lg font-bold text-green-900 tracking-widest mt-0.5">
                    {booking.confirmation_number}
                  </p>
                </div>
              )}

              {booking.status === "unsupported" && (
                <p className="text-xs text-amber-700 bg-amber-50 rounded-lg px-4 py-2.5">
                  Automated booking is not yet supported for this carrier or hotel. You can
                  book manually using the itinerary details above.
                </p>
              )}

              <LogTimeline logs={booking.logs} />
            </div>
          ))
        )}
      </div>
    </div>
  )
}
