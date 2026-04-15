import { NextRequest, NextResponse } from "next/server";

const BACKEND = process.env.BACKEND_URL || "https://x402-guard.fly.dev";

export async function PATCH(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  try {
    const body = await req.json();
    const active = body.status !== "blocked" && body.status !== "paused";

    const policiesRes = await fetch(`${BACKEND}/policies/agent/${params.id}`);
    if (!policiesRes.ok) throw new Error("Policy not found");

    const policy = await policiesRes.json();
    const policyId = Array.isArray(policy) ? policy[0]?.id : policy?.id;
    if (!policyId) throw new Error("No policy id");

    const updated = await fetch(`${BACKEND}/policies/${policyId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ active }),
    });

    const data = await updated.json();
    return NextResponse.json(data);
  } catch (err) {
    return NextResponse.json({ error: String(err) }, { status: 500 });
  }
}
