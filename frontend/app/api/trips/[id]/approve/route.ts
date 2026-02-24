import { auth } from "@/lib/auth"
import { NextRequest, NextResponse } from "next/server"

const BACKEND_URL = process.env.BACKEND_URL!
const INTERNAL_API_KEY = process.env.INTERNAL_API_KEY!

// POST /api/trips/[id]/approve — approve an itinerary option
export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const session = await auth()
  if (!session?.user?.email) {
    return NextResponse.json({ detail: "Unauthorized" }, { status: 401 })
  }

  const { id } = await params
  const body = await req.json()

  const res = await fetch(`${BACKEND_URL}/trips/${id}/approve`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-user-email": session.user.email,
      "x-api-key": INTERNAL_API_KEY,
    },
    body: JSON.stringify(body),
  })

  const data = await res.json()
  return NextResponse.json(data, { status: res.status })
}
