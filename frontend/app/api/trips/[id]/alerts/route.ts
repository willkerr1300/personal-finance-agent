import { auth } from "@/lib/auth"
import { NextRequest, NextResponse } from "next/server"

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const session = await auth()
  if (!session) return NextResponse.json({ detail: "Unauthorized" }, { status: 401 })

  const { id } = await params
  const res = await fetch(`${process.env.BACKEND_URL}/trips/${id}/alerts`, {
    headers: {
      "x-user-email": session.user!.email!,
      "x-api-key": process.env.INTERNAL_API_KEY!,
    },
  })

  const data = await res.json()
  return NextResponse.json(data, { status: res.status })
}
