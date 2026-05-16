import { NextRequest, NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

const DEMO_PAYMENT_HEADER = 'demo-paid';
const DEMO_PAY_TO = '0x000000000000000000000000000000000000dEaD';

function buildResourceUrl(request: NextRequest, city: string, units: string): string {
  const url = new URL('/api/demo-x402-weather', request.nextUrl.origin);
  url.searchParams.set('city', city);
  url.searchParams.set('units', units);
  return url.toString();
}

export async function GET(request: NextRequest) {
  const city = request.nextUrl.searchParams.get('city')?.trim() || 'Singapore';
  const units = request.nextUrl.searchParams.get('units')?.trim() || 'metric';
  const resource = buildResourceUrl(request, city, units);
  const xPayment = request.headers.get('x-payment')?.trim();

  if (!xPayment) {
    return NextResponse.json({
      error: 'X-PAYMENT header is required.',
      accepts: [
        {
          scheme: 'exact',
          network: 'kite-testnet',
          maxAmountRequired: '1000000',
          resource,
          description: 'Boundless local x402 demo weather endpoint.',
          payTo: DEMO_PAY_TO,
          asset: 'USDT',
          merchantName: 'Boundless Local Demo',
        },
      ],
      hint: `For local recording, complete the second step with X-PAYMENT: ${DEMO_PAYMENT_HEADER}`,
    }, { status: 402 });
  }

  if (xPayment !== DEMO_PAYMENT_HEADER) {
    return NextResponse.json({
      error: 'Invalid local demo X-PAYMENT value.',
      expected: DEMO_PAYMENT_HEADER,
    }, { status: 402 });
  }

  return NextResponse.json({
    ok: true,
    paid: true,
    source: 'boundless-local-x402-demo',
    city,
    units,
    forecast: {
      summary: 'Light showers, manageable humidity, warm afternoon.',
      temperature: units === 'imperial' ? '88F' : '31C',
      humidity: '68%',
      confidence: 'demo',
    },
  });
}
