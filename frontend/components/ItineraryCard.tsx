"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"

interface FlightSegment {
  from: string
  departs: string
  to: string
  arrives: string
  flight: string
  carrier: string
}

interface Flight {
  id: string
  price_usd: number
  cabin: string
  outbound_stops: number
  outbound_duration: string
  carrier: string
  segments: FlightSegment[]
}

interface Hotel {
  hotel_id: string
  name: string
  rating: string
  price_total_usd: number
  check_in: string
  check_out: string
  room_type: string
  beds: number
}

interface ItineraryOption {
  label: string
  description: string
  flight: Flight
  hotel: Hotel
  total_usd: number
  within_budget: boolean
}

interface Props {
  option: ItineraryOption
  optionIndex: number
  tripId: string
  approved: boolean
}

function formatDate(iso: string) {
  if (!iso) return "—"
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  })
}

function formatTime(iso: string) {
  if (!iso) return "—"
  return new Date(iso).toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  })
}

function formatDuration(iso: string) {
  if (!iso) return ""
  const m = iso.match(/PT(?:(\d+)H)?(?:(\d+)M)?/)
  if (!m) return iso
  const h = m[1] ? `${m[1]}h` : ""
  const min = m[2] ? ` ${m[2]}m` : ""
  return `${h}${min}`.trim()
}

function StarsRating({ rating }: { rating: string }) {
  const n = parseInt(rating, 10) || 0
  return (
    <span className="text-amber-400 text-xs">
      {"★".repeat(n)}{"☆".repeat(Math.max(0, 5 - n))}
    </span>
  )
}

export function ItineraryCard({ option, optionIndex, tripId, approved }: Props) {
  const router = useRouter()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const outboundSeg = option.flight.segments[0]
  const stopLabel = option.flight.outbound_stops === 0
    ? "Nonstop"
    : `${option.flight.outbound_stops} stop${option.flight.outbound_stops > 1 ? "s" : ""}`

  async function handleApprove() {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`/api/trips/${tripId}/approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ option_index: optionIndex }),
      })
      if (!res.ok) {
        const d = await res.json()
        setError(d.detail ?? "Approval failed")
        return
      }
      router.refresh()
    } catch {
      setError("Network error")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className={`rounded-2xl border bg-white shadow-sm flex flex-col ${
      approved ? "border-zinc-900 ring-2 ring-zinc-900" : "border-zinc-200"
    }`}>
      {/* Header */}
      <div className="px-6 pt-5 pb-4 border-b border-zinc-100">
        <div className="flex items-center justify-between">
          <div>
            <span className="text-xs font-semibold uppercase tracking-widest text-zinc-400">
              {option.label}
            </span>
            <p className="text-xs text-zinc-500 mt-0.5">{option.description}</p>
          </div>
          <div className="text-right">
            <p className="text-2xl font-bold text-zinc-900">
              ${option.total_usd.toLocaleString()}
            </p>
            <p className="text-xs text-zinc-400">total est.</p>
          </div>
        </div>
        {!option.within_budget && (
          <p className="mt-2 text-xs text-amber-600 font-medium">Over your stated budget</p>
        )}
      </div>

      {/* Flight */}
      <div className="px-6 py-4 border-b border-zinc-100">
        <p className="text-xs font-semibold uppercase tracking-widest text-zinc-400 mb-2">Flight</p>
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-semibold text-zinc-900">
              {outboundSeg?.from} → {outboundSeg?.to}
            </p>
            <p className="text-xs text-zinc-500 mt-0.5">
              {formatTime(outboundSeg?.departs)} · {stopLabel}
              {option.flight.outbound_duration
                ? ` · ${formatDuration(option.flight.outbound_duration)}`
                : ""}
            </p>
            <p className="text-xs text-zinc-400 mt-0.5">
              {option.flight.carrier} · {option.flight.cabin}
            </p>
          </div>
          <p className="text-sm font-semibold text-zinc-900">
            ${option.flight.price_usd.toLocaleString()}
          </p>
        </div>
      </div>

      {/* Hotel */}
      <div className="px-6 py-4 flex-1">
        <p className="text-xs font-semibold uppercase tracking-widest text-zinc-400 mb-2">Hotel</p>
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-semibold text-zinc-900">{option.hotel.name}</p>
            <div className="flex items-center gap-1 mt-0.5">
              <StarsRating rating={option.hotel.rating} />
            </div>
            <p className="text-xs text-zinc-500 mt-0.5">
              {formatDate(option.hotel.check_in)} – {formatDate(option.hotel.check_out)}
            </p>
            <p className="text-xs text-zinc-400 mt-0.5">
              {option.hotel.room_type?.replace(/_/g, " ").toLowerCase() || "Standard room"}
            </p>
          </div>
          <p className="text-sm font-semibold text-zinc-900">
            ${option.hotel.price_total_usd.toLocaleString()}
          </p>
        </div>
      </div>

      {/* CTA */}
      <div className="px-6 pb-5">
        {error && <p className="text-xs text-red-500 mb-2">{error}</p>}
        {approved ? (
          <div className="rounded-xl bg-zinc-900 px-4 py-2.5 text-sm font-medium text-white text-center">
            Approved — booking coming in Week 5
          </div>
        ) : (
          <button
            onClick={handleApprove}
            disabled={loading}
            className="w-full rounded-xl border border-zinc-900 px-4 py-2.5 text-sm font-medium text-zinc-900 hover:bg-zinc-900 hover:text-white transition-colors disabled:opacity-40"
          >
            {loading ? "Approving…" : "Choose this trip"}
          </button>
        )}
      </div>
    </div>
  )
}
