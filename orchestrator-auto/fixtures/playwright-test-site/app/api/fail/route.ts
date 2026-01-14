import { NextResponse } from "next/server";

export async function GET() {
  return NextResponse.json({ ok: false, source: "fail" }, { status: 500 });
}
