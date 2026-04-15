export const dynamic = "force-dynamic";

import { NextRequest, NextResponse } from "next/server";
import { MOCK_POLICIES, isDemoMode } from "@/lib/mock-data";

const BACKEND = process.env.BACKEND_URL || "https://x402-guard.fly.dev";

export async function GET() {
  try {
    if (isDemoMode()) return NextResponse.json(MOCK_POLICIES);
    const res = await fetch(`${BACKEND}/policies/`);
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (err) {
    if (isDemoMode()) return NextResponse.json(MOCK_POLICIES);
    return NextResponse.json({ error: String(err) }, { status: 500 });
  }
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    if (isDemoMode()) {
      return NextResponse.json({
        id: body.id || `mock-${Date.now()}`,
        active: true,
        soft_alert_threshold: body.soft_alert_threshold ?? 0.8,
        created_at: new Date().toISOString(),
        ...body,
      });
    }
    const res = await fetch(`${BACKEND}/policies/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (err) {
    if (isDemoMode()) return NextResponse.json(MOCK_POLICIES);
    return NextResponse.json({ error: String(err) }, { status: 500 });
  }
}
