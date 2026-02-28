import { auth } from "@/lib/auth"
import { NextRequest, NextResponse } from "next/server"

export async function POST(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string; alertId: string }> }
) {
  const session = await auth()
  if (!session) return NextResponse.json({ detail: "Unauthorized" }, { status: 401 })

  const { id, alertId } = await params
  const res = await fetch(
    `${process.env.BACKEND_URL}/trips/${id}/alerts/${alertId}/read`,
    {
      method: "POST",
      headers: {
        "x-user-email": session.user!.email!,
        "x-api-key": process.env.INTERNAL_API_KEY!,
      },
    }
  )

  return new NextResponse(null, { status: res.status })
}
