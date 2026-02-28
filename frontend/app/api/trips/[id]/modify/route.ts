import { auth } from "@/lib/auth"
import { NextRequest, NextResponse } from "next/server"

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const session = await auth()
  if (!session) return NextResponse.json({ detail: "Unauthorized" }, { status: 401 })

  const { id } = await params
  const body = await req.json()

  const res = await fetch(`${process.env.BACKEND_URL}/trips/${id}/modify`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-user-email": session.user!.email!,
      "x-api-key": process.env.INTERNAL_API_KEY!,
    },
    body: JSON.stringify(body),
  })

  const data = await res.json()
  return NextResponse.json(data, { status: res.status })
}
