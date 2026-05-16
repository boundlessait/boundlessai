import { NextResponse } from 'next/server';
import { isAddress } from 'viem';
import { readKitePassportSession, writeKitePassportSession } from '@/lib/kite-passport-session';

export const dynamic = 'force-dynamic';

export async function GET() {
  return NextResponse.json({ session: readKitePassportSession() });
}

export async function POST(request: Request) {
  const body = (await request.json().catch(() => null)) as Record<string, unknown> | null;
  if (!body) {
    return NextResponse.json({ error: 'Invalid JSON body.' }, { status: 400 });
  }

  const sessionId = typeof body.sessionId === 'string' ? body.sessionId.trim() : '';
  const payerAddress = typeof body.payerAddress === 'string' ? body.payerAddress.trim() : '';
  const expiresAt = typeof body.expiresAt === 'string' ? body.expiresAt.trim() : '';
  const network = body.network === 'kite-mainnet' ? 'kite-mainnet' : 'kite-testnet';
  const dailyBudgetUsd = Number(body.dailyBudgetUsd ?? 0);
  const spentUsd = Number(body.spentUsd ?? 0);

  if (!sessionId) {
    return NextResponse.json({ error: 'Session ID is required.' }, { status: 400 });
  }
  if (!payerAddress || !isAddress(payerAddress)) {
    return NextResponse.json({ error: 'A valid payer address is required.' }, { status: 400 });
  }
  if (!expiresAt) {
    return NextResponse.json({ error: 'Session expiry is required.' }, { status: 400 });
  }
  if (!Number.isFinite(dailyBudgetUsd) || dailyBudgetUsd <= 0) {
    return NextResponse.json({ error: 'Session budget must be positive.' }, { status: 400 });
  }
  if (!Number.isFinite(spentUsd) || spentUsd < 0) {
    return NextResponse.json({ error: 'Session spent amount must be zero or greater.' }, { status: 400 });
  }

  const session = writeKitePassportSession({
    sessionId,
    payerAddress,
    agentName: typeof body.agentName === 'string' ? body.agentName : undefined,
    agentId: typeof body.agentId === 'string' ? body.agentId : undefined,
    network,
    createdAt: typeof body.createdAt === 'string' ? body.createdAt : undefined,
    expiresAt,
    dailyBudgetUsd,
    spentUsd,
    portalUrl: typeof body.portalUrl === 'string' ? body.portalUrl : undefined,
    notes: typeof body.notes === 'string' ? body.notes : undefined,
  });

  return NextResponse.json({ ok: true, session });
}
