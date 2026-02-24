import { auth } from "@/lib/auth"
import { redirect, notFound } from "next/navigation"
import Link from "next/link"
import { SignOutButton } from "@/components/SignOutButton"
import { ItineraryCard } from "@/components/ItineraryCard"

interface ParsedSpec {
  origin?: string
  destination?: string
  destination_city?: string
  depart_date?: string
  return_date?: string
  budget_total?: number
  num_travelers?: number
  cabin_class?: string
  hotel_area?: string
  notes?: string
}

interface Trip {
  id: string
  status: string
  raw_request: string
  parsed_spec: ParsedSpec | null
  itinerary_options: Array<{
    label: string
    description: string
    flight: object
    hotel: object
    total_usd: number
    within_budget: boolean
  }> | null
  approved_itinerary: { label: string } | null
  created_at: string
}

async function getTrip(id: string, email: string): Promise<Trip | null> {
  try {
    const res = await fetch(`${process.env.BACKEND_URL}/trips/${id}`, {
      headers: {
        "x-user-email": email,
        "x-api-key": process.env.INTERNAL_API_KEY!,
      },
      cache: "no-store",
    })
    if (res.status === 404) return null
    if (!res.ok) return null
    return res.json()
  } catch {
    return null
  }
}

const STATUS_MESSAGES: Record<string, string> = {
  parsing: "Parsing your trip request…",
  searching: "Searching for flights and hotels…",
  search_failed: "We couldn't find matching flights or hotels. Try adjusting your request.",
  failed: "Something went wrong processing this trip.",
}

export default async function TripPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const session = await auth()
  if (!session) redirect("/")

  const { id } = await params
  const trip = await getTrip(id, session.user!.email!)
  if (!trip) notFound()

  const spec = trip.parsed_spec
  const options = trip.itinerary_options ?? []
  const approvedLabel = trip.approved_itinerary?.label

  return (
    <div className="min-h-screen bg-zinc-50">
      {/* Nav */}
      <nav className="bg-white border-b border-zinc-100 px-8 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link
            href="/dashboard"
            className="text-sm text-zinc-500 hover:text-zinc-900 transition-colors"
          >
            ← Dashboard
          </Link>
          <span className="text-zinc-200">|</span>
          <span className="text-lg font-semibold tracking-tight">Travel Planner</span>
        </div>
        <div className="flex items-center gap-4">
          <span className="text-sm text-zinc-400">{session.user?.email}</span>
          <SignOutButton />
        </div>
      </nav>

      <main className="max-w-5xl mx-auto px-6 py-12">
        {/* Trip header */}
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-zinc-900">
            {spec?.destination_city
              ? `Trip to ${spec.destination_city}`
              : "Your trip"}
          </h1>
          <p className="mt-1 text-zinc-500 text-sm italic">&ldquo;{trip.raw_request}&rdquo;</p>

          {spec && (
            <div className="mt-4 flex flex-wrap gap-2">
              {spec.origin && spec.destination && (
                <Chip>{spec.origin} → {spec.destination}</Chip>
              )}
              {spec.depart_date && (
                <Chip>
                  {fmtDate(spec.depart_date)}
                  {spec.return_date ? ` – ${fmtDate(spec.return_date)}` : ""}
                </Chip>
              )}
              {spec.budget_total && (
                <Chip>Budget: ${spec.budget_total.toLocaleString()}</Chip>
              )}
              {spec.num_travelers && spec.num_travelers > 1 && (
                <Chip>{spec.num_travelers} travelers</Chip>
              )}
              {spec.cabin_class && spec.cabin_class !== "ECONOMY" && (
                <Chip>{spec.cabin_class.replace(/_/g, " ")}</Chip>
              )}
              {spec.hotel_area && (
                <Chip>Hotel near {spec.hotel_area}</Chip>
              )}
            </div>
          )}
        </div>

        {/* In-progress states */}
        {(trip.status === "parsing" || trip.status === "searching") && (
          <div className="rounded-2xl border border-zinc-200 bg-white p-8 text-center shadow-sm">
            <div className="w-8 h-8 border-2 border-zinc-900 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
            <p className="text-zinc-600">{STATUS_MESSAGES[trip.status]}</p>
            <p className="text-xs text-zinc-400 mt-2">Refresh in a moment to see results.</p>
          </div>
        )}

        {/* Error states */}
        {(trip.status === "search_failed" || trip.status === "failed") && (
          <div className="rounded-2xl border border-red-100 bg-red-50 p-6 shadow-sm">
            <p className="text-sm text-red-700">{STATUS_MESSAGES[trip.status]}</p>
            <Link
              href="/dashboard"
              className="mt-3 inline-block text-sm font-medium text-red-700 underline underline-offset-4"
            >
              Try a new request
            </Link>
          </div>
        )}

        {/* Itinerary options */}
        {options.length > 0 && (
          <>
            {trip.status === "approved" ? (
              <div className="mb-6 rounded-xl bg-green-50 border border-green-200 px-5 py-4">
                <p className="text-sm font-medium text-green-800">
                  You approved the <strong>{approvedLabel}</strong> option.
                  Booking execution will be available in Week 5.
                </p>
              </div>
            ) : (
              <p className="mb-6 text-sm text-zinc-500">
                Here are your itinerary options — pick one to lock it in.
              </p>
            )}

            <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
              {options.map((option, i) => (
                <ItineraryCard
                  key={i}
                  option={option as Parameters<typeof ItineraryCard>[0]["option"]}
                  optionIndex={i}
                  tripId={trip.id}
                  approved={trip.status === "approved" && approvedLabel === option.label}
                />
              ))}
            </div>
          </>
        )}
      </main>
    </div>
  )
}

function Chip({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded-full bg-zinc-100 px-3 py-1 text-xs font-medium text-zinc-600">
      {children}
    </span>
  )
}

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  })
}
