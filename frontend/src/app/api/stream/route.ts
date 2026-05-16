import { NextResponse } from 'next/server'

const CV_BASE = process.env.CV_BASE_INTERNAL ?? process.env.NEXT_PUBLIC_CV_BASE ?? 'http://localhost:8001'

// Proxy the MJPEG stream from CV, bypassing the ngrok browser interstitial
// that blocks <img> tags from fetching directly from ngrok URLs.
export async function GET() {
  const res = await fetch(`${CV_BASE}/live/mjpeg`, {
    headers: { 'ngrok-skip-browser-warning': 'true' },
    // @ts-expect-error — Node fetch supports duplex for streaming
    duplex: 'half',
  })

  if (!res.ok || !res.body) {
    return new NextResponse('stream unavailable', { status: 502 })
  }

  return new NextResponse(res.body, {
    headers: {
      'Content-Type': res.headers.get('Content-Type') ?? 'multipart/x-mixed-replace; boundary=frame',
      'Cache-Control': 'no-store',
      'X-Accel-Buffering': 'no',
    },
  })
}
