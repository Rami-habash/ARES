import { NextRequest, NextResponse } from 'next/server'

// Use the non-NEXT_PUBLIC_ var — NEXT_PUBLIC_ vars are browser-only and
// undefined in server-side API routes.
const CV_BASE = process.env.CV_BASE_INTERNAL ?? process.env.NEXT_PUBLIC_CV_BASE ?? 'http://localhost:8001'

// Proxy the ArUco marker PNG from the CV service, bypassing the ngrok
// browser interstitial that blocks <img> tags fetching directly from ngrok URLs.
export async function GET(req: NextRequest) {
  const markerId = req.nextUrl.searchParams.get('marker_id') ?? '0'
  const res = await fetch(`${CV_BASE}/live/marker.png?marker_id=${markerId}`, {
    headers: { 'ngrok-skip-browser-warning': 'true' },
    cache: 'no-store',
  })

  if (!res.ok) {
    return new NextResponse('marker unavailable', { status: 502 })
  }

  const buf = await res.arrayBuffer()
  return new NextResponse(buf, {
    headers: {
      'Content-Type': 'image/png',
      'Cache-Control': 'no-store',
    },
  })
}
