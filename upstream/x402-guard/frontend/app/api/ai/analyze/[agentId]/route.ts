import { NextRequest, NextResponse } from "next/server";
import { isDemoMode, mockAnalysis } from "@/lib/mock-data";

const BACKEND = process.env.BACKEND_URL || "https://x402-guard.fly.dev";

export async function POST(
  req: NextRequest,
  { params }: { params: { agentId: string } }
) {
  try {
    const body = await req.json().catch(() => ({}));
    if (isDemoMode()) return NextResponse.json(mockAnalysis(params.agentId));
    const res = await fetch(`${BACKEND}/ai/analyze/${params.agentId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (err) {
    if (isDemoMode()) return NextResponse.json(mockAnalysis(params.agentId));
    return NextResponse.json({ error: String(err) }, { status: 500 });
  }
}
