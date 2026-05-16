export const USE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK !== 'false'
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? 'http://localhost:8000'
// CV service — used for WebRTC signalling + /live/marker.png served to phones.
// When the CV box is fronted by ngrok / Cloudflare, set NEXT_PUBLIC_CV_BASE
// so the marker URL the patient page renders is reachable from a phone.
export const CV_BASE = process.env.NEXT_PUBLIC_CV_BASE ?? 'http://localhost:8001'
// Used for the long-lived /live/ws subscription from the admin browser. ngrok
// free tier blocks browser-origin WebSockets, so default to direct localhost.
// Override if you're running the admin frontend on a different host than CV.
export const CV_WS_BASE = process.env.NEXT_PUBLIC_CV_WS_BASE ?? 'http://localhost:8001'
