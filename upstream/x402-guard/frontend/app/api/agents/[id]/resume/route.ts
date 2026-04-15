import { NextRequest, NextResponse } from "next/server";

const BACKEND = process.env.BACKEND_URL || "https://x402-guard.fly.dev";

export async function POST(
  _req: NextRequest,
  { params }: { params: { id: string } }
) {
  try {
    const policiesRes = await fetch(`${BACKEND}/policies/agent/${params.id}`);
    if (!policiesRes.ok) throw new Error("Policy not found");

    const policy = await policiesRes.json();
    const policyId = Array.isArray(policy) ? policy[0]?.id : policy?.id;
    if (!policyId) throw new Error("No policy id");

    await fetch(`${BACKEND}/policies/${policyId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ active: true }),
    });

    return NextResponse.json({ success: true, message: `Agent ${params.id} resumed` });
  } catch (err) {
    return NextResponse.json({ success: false, message: String(err) }, { status: 500 });
  }
}
