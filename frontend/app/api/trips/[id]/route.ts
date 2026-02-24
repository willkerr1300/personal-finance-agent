import { auth } from "@/lib/auth"
import { NextResponse } from "next/server"

const BACKEND_URL = process.env.BACKEND_URL!
const INTERNAL_API_KEY = process.env.INTERNAL_API_KEY!

// GET /api/trips/[id] — fetch a single trip with itinerary options
export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const session = await auth()
  if (!session?.user?.email) {
    return NextResponse.json({ detail: "Unauthorized" }, { status: 401 })
  }

  const { id } = await params

  const res = await fetch(`${BACKEND_URL}/trips/${id}`, {
    headers: {
      "x-user-email": session.user.email,
      "x-api-key": INTERNAL_API_KEY,
    },
    cache: "no-store",
  })

  const data = await res.json()
  return NextResponse.json(data, { status: res.status })
}
