import { auth } from "@/lib/auth"
import { redirect } from "next/navigation"
import Link from "next/link"
import { SignOutButton } from "@/components/SignOutButton"
import { TripRequestForm } from "@/components/TripRequestForm"

interface Trip {
  id: string
  status: string
  raw_request: string
  parsed_spec: {
    destination_city?: string
    depart_date?: string
    return_date?: string
  } | null
  created_at: string
}

const STATUS_LABELS: Record<string, string> = {
  parsing: "Parsing…",
  searching: "Searching…",
  options_ready: "Options ready",
  approved: "Approved",
  search_failed: "Search failed",
  failed: "Failed",
}

const STATUS_COLORS: Record<string, string> = {
  parsing: "bg-zinc-100 text-zinc-500",
  searching: "bg-zinc-100 text-zinc-500",
  options_ready: "bg-blue-50 text-blue-700",
  approved: "bg-green-50 text-green-700",
  search_failed: "bg-red-50 text-red-600",
  failed: "bg-red-50 text-red-600",
}

async function getTrips(email: string): Promise<Trip[]> {
  try {
    const res = await fetch(`${process.env.BACKEND_URL}/trips`, {
      headers: {
        "x-user-email": email,
        "x-api-key": process.env.INTERNAL_API_KEY!,
      },
      cache: "no-store",
    })
    if (!res.ok) return []
    return res.json()
  } catch {
    return []
  }
}

export default async function DashboardPage() {
  const session = await auth()
  if (!session) redirect("/")

  const trips = await getTrips(session.user!.email!)

  return (
    <div className="min-h-screen bg-zinc-50">
      {/* Nav */}
      <nav className="bg-white border-b border-zinc-100 px-8 py-4 flex items-center justify-between">
        <span className="text-lg font-semibold tracking-tight">Travel Planner</span>
        <div className="flex items-center gap-4">
          <Link href="/profile" className="text-sm text-zinc-500 hover:text-zinc-900 transition-colors">
            Profile
          </Link>
          <span className="text-sm text-zinc-400">{session.user?.email}</span>
          <SignOutButton />
        </div>
      </nav>

      <main className="max-w-3xl mx-auto px-6 py-12">
        <h1 className="text-3xl font-bold text-zinc-900">
          Where to{session.user?.name ? `, ${session.user.name.split(" ")[0]}` : ""}?
        </h1>
        <p className="mt-1 text-zinc-500">
          Describe your trip in plain English — the agent will find flights and hotels for you.
        </p>

        {/* Trip request input */}
        <div className="mt-8 rounded-2xl border border-zinc-200 bg-white p-6 shadow-sm">
          <TripRequestForm />
        </div>

        {/* Previous trips */}
        {trips.length > 0 && (
          <div className="mt-10">
            <h2 className="text-sm font-semibold uppercase tracking-widest text-zinc-400 mb-4">
              Your trips
            </h2>
            <div className="space-y-3">
              {trips.map((trip) => (
                <Link
                  key={trip.id}
                  href={`/trips/${trip.id}`}
                  className="block rounded-xl border border-zinc-200 bg-white px-5 py-4 hover:border-zinc-400 transition-colors"
                >
                  <div className="flex items-center justify-between">
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-zinc-900 truncate">
                        {trip.parsed_spec?.destination_city
                          ? `${trip.parsed_spec.destination_city}${
                              trip.parsed_spec.depart_date
                                ? ` · ${new Date(trip.parsed_spec.depart_date).toLocaleDateString(
                                    "en-US",
                                    { month: "short", day: "numeric" }
                                  )}`
                                : ""
                            }`
                          : trip.raw_request}
                      </p>
                      <p className="text-xs text-zinc-400 mt-0.5 truncate">
                        {trip.raw_request}
                      </p>
                    </div>
                    <span
                      className={`ml-4 shrink-0 rounded-full px-2.5 py-0.5 text-xs font-medium ${
                        STATUS_COLORS[trip.status] ?? "bg-zinc-100 text-zinc-500"
                      }`}
                    >
                      {STATUS_LABELS[trip.status] ?? trip.status}
                    </span>
                  </div>
                </Link>
              ))}
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
