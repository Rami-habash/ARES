'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { motion, AnimatePresence } from 'framer-motion'
import { ArrowRight, Eye, EyeOff, Activity, Shield, Brain } from 'lucide-react'
import { login, register, googleLoginUrl } from '@/lib/api/auth'

type Mode = 'landing' | 'signin' | 'signup'

// Sun icon — radiating rays around a circle, solstice motif
function SunIcon({ size = 28 }: { size?: number }) {
  const r = size / 2
  const innerR = r * 0.32
  const outerR = r * 0.46
  const rayLen = r * 0.18
  const rayCount = 12

  const rays = Array.from({ length: rayCount }, (_, i) => {
    const angle = (i * 360) / rayCount
    const rad = (angle * Math.PI) / 180
    const x1 = r + Math.cos(rad) * (outerR + 1)
    const y1 = r + Math.sin(rad) * (outerR + 1)
    const x2 = r + Math.cos(rad) * (outerR + rayLen)
    const y2 = r + Math.sin(rad) * (outerR + rayLen)
    return { x1, y1, x2, y2 }
  })

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} fill="none">
      <circle cx={r} cy={r} r={innerR} fill="currentColor" />
      {rays.map((ray, i) => (
        <line
          key={i}
          x1={ray.x1} y1={ray.y1}
          x2={ray.x2} y2={ray.y2}
          stroke="currentColor"
          strokeWidth={i % 2 === 0 ? 1.8 : 1.1}
          strokeLinecap="round"
        />
      ))}
    </svg>
  )
}

export default function LandingPage() {
  const [mode, setMode] = useState<Mode>('landing')
  const router = useRouter()

  return (
    <div className="min-h-screen bg-[#f2ece0] overflow-hidden" style={{ fontFamily: "'DM Sans', system-ui, sans-serif" }}>
      {/* Nav */}
      <nav className="flex items-center justify-between px-10 py-6">
        <div className="flex items-center gap-2.5">
          <div className="text-[#e8622c]">
            <SunIcon size={30} />
          </div>
          <span className="text-[#1a1208] font-bold text-xl tracking-tight">SOLSTICE</span>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setMode('signin')}
            className="text-sm font-medium text-[#1a1208]/60 hover:text-[#1a1208] transition-colors px-4 py-2"
          >
            Sign In
          </button>
          <button
            onClick={() => setMode('signup')}
            className="text-sm font-semibold bg-[#1a1208] text-[#f2ece0] px-5 py-2.5 rounded-full hover:bg-[#2d2010] transition-colors"
          >
            Get Access
          </button>
        </div>
      </nav>

      <AnimatePresence mode="wait">
        {mode === 'landing' && (
          <HeroSection key="hero" onSignIn={() => setMode('signin')} onSignUp={() => setMode('signup')} />
        )}
        {mode === 'signin' && (
          <AuthForm key="signin" mode="signin" onSwitch={() => setMode('signup')} onSuccess={() => router.push('/dashboard')} />
        )}
        {mode === 'signup' && (
          <AuthForm key="signup" mode="signup" onSwitch={() => setMode('signin')} onSuccess={() => router.push('/dashboard')} />
        )}
      </AnimatePresence>
    </div>
  )
}

function HeroSection({ onSignIn, onSignUp }: { onSignIn: () => void; onSignUp: () => void }) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.3 }}
    >
      {/* Hero */}
      <div className="px-10 pt-14 pb-24 max-w-7xl mx-auto">
        <div className="grid grid-cols-2 gap-16 items-center">
          <div>
            {/* Pill tag — orange used minimally here as background tint */}
            <div className="inline-flex items-center gap-2 border border-[#1a1208]/15 text-[#1a1208]/60 text-xs font-medium px-3 py-1.5 rounded-full mb-8 tracking-wide">
              <span className="w-1.5 h-1.5 bg-[#e8622c] rounded-full" />
              AI-Powered Rehab Intelligence
            </div>

            {/* Headline — mostly black, one word in orange */}
            <h1 className="text-[80px] font-bold leading-[0.9] tracking-tight text-[#1a1208] mb-8">
              Move<br />
              <span className="text-[#e8622c]">Better.</span><br />
              Recover<br />
              Smarter.
            </h1>

            <p className="text-[#1a1208]/55 text-lg leading-relaxed mb-10 max-w-md font-normal">
              Real-time AI movement analysis for physical therapy clinics. Every rep tracked. Every deviation caught. Every patient safer.
            </p>

            <div className="flex items-center gap-4">
              <button
                onClick={onSignUp}
                className="flex items-center gap-2 bg-[#1a1208] text-[#f2ece0] font-semibold px-7 py-4 rounded-full hover:bg-[#2d2010] transition-colors text-base"
              >
                Start Free Trial
                <ArrowRight className="w-4 h-4" />
              </button>
              <button
                onClick={onSignIn}
                className="flex items-center gap-2 text-[#1a1208] font-medium px-7 py-4 rounded-full border border-[#1a1208]/20 hover:border-[#1a1208]/40 transition-colors text-base"
              >
                Sign In
              </button>
            </div>
          </div>

          {/* Visual — sun circle + floating card */}
          <div className="relative h-[520px]">
            {/* Solstice sun rings */}
            <div className="absolute top-[20px] right-[-40px] w-[420px] h-[420px] rounded-full border border-[#1a1208]/8" />
            <div className="absolute top-[50px] right-[-10px] w-[360px] h-[360px] rounded-full bg-[#e8622c]/12" />
            <div className="absolute top-[90px] right-[30px] w-[280px] h-[280px] rounded-full bg-[#e8622c]/18" />

            {/* Large sun SVG in background */}
            <div className="absolute top-[30px] right-[20px] text-[#e8622c]/25">
              <SunIcon size={400} />
            </div>

            {/* Mock dashboard card */}
            <div className="absolute top-[60px] left-0 right-[20px] z-10 bg-[#faf7f2] border border-[#e0d8cc] rounded-2xl p-5 shadow-2xl">
              <div className="flex items-center gap-2 mb-4">
                <span className="w-2 h-2 bg-[#2d7a4f] rounded-full animate-pulse" />
                <span className="text-xs text-[#1a1208]/50 font-medium">Live Session · Room A</span>
              </div>
              <div className="grid grid-cols-3 gap-2.5 mb-4">
                {[
                  { label: 'Form Score', value: '88', unit: '/100' },
                  { label: 'Confidence', value: '94', unit: '%' },
                  { label: 'Risk Level', value: 'Low', unit: '' },
                ].map(item => (
                  <div key={item.label} className="bg-[#f2ece0] rounded-xl p-3">
                    <p className="text-[10px] text-[#1a1208]/40 uppercase tracking-wider mb-1">{item.label}</p>
                    <p className="text-xl font-bold text-[#1a1208]">
                      {item.value}
                      <span className="text-xs font-normal text-[#1a1208]/40">{item.unit}</span>
                    </p>
                  </div>
                ))}
              </div>
              {/* Skeleton canvas */}
              <div className="bg-[#1a1208] rounded-xl overflow-hidden aspect-video flex items-center justify-center">
                <svg viewBox="0 0 100 100" className="w-28 h-28">
                  {[
                    [50,12,40,30],[50,12,60,30],[40,30,60,30],
                    [40,30,35,50],[60,30,65,50],[35,50,33,65],[65,50,67,65],
                    [42,58,60,58],[42,58,40,76],[60,58,60,76],
                    [40,76,38,90],[60,76,62,90],
                  ].map(([x1,y1,x2,y2], i) => (
                    <line key={i} x1={x1} y1={y1} x2={x2} y2={y2} stroke="#e8622c" strokeWidth="1.5" strokeOpacity="0.85" />
                  ))}
                  {[[50,12],[40,30],[60,30],[35,50],[65,50],[33,65],[67,65],[42,58],[60,58],[40,76],[60,76],[38,90],[62,90]].map(([cx,cy], i) => (
                    <circle key={i} cx={cx} cy={cy} r="2" fill="white" />
                  ))}
                </svg>
              </div>
              <div className="mt-3 flex items-center justify-between">
                <div>
                  <p className="text-xs font-semibold text-[#1a1208]">Maya Patel · Bodyweight Squat</p>
                  <p className="text-[10px] text-[#1a1208]/40 mt-0.5">Rep 8 of 10 · Eccentric phase</p>
                </div>
                {/* Orange used as a meaningful alert signal */}
                <span className="text-[10px] bg-[#e8622c]/10 text-[#e8622c] px-2 py-1 rounded-full font-semibold border border-[#e8622c]/20">
                  Knee valgus ⚠
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Feature strip */}
      <div className="border-t border-[#1a1208]/10 bg-[#faf7f2] px-10 py-14">
        <div className="max-w-7xl mx-auto grid grid-cols-3 gap-12">
          {[
            {
              icon: Activity,
              title: 'Real-Time Movement Analysis',
              desc: 'MediaPipe pose estimation tracks 33 landmarks per patient at 30fps. Deviations flagged the moment they happen.',
            },
            {
              icon: Brain,
              title: 'AI Coaching Intelligence',
              desc: 'LLM-powered coaching cues generated from movement data. Ask anything about any patient, any session.',
            },
            {
              icon: Shield,
              title: 'Clinical Safety Layer',
              desc: 'Automated fall-risk scoring, restriction enforcement, and escalation paths built for real PT workflows.',
            },
          ].map(({ icon: Icon, title, desc }) => (
            <div key={title}>
              {/* Icon container — subtle, not orange-heavy */}
              <div className="w-10 h-10 bg-[#1a1208]/6 rounded-xl flex items-center justify-center mb-4">
                <Icon className="w-5 h-5 text-[#1a1208]" />
              </div>
              <h3 className="font-bold text-[#1a1208] text-lg mb-2">{title}</h3>
              <p className="text-[#1a1208]/50 text-sm leading-relaxed">{desc}</p>
            </div>
          ))}
        </div>
      </div>

      {/* CTA */}
      <div className="px-10 py-20 max-w-7xl mx-auto text-center">
        <p className="text-[#1a1208]/40 text-xs uppercase tracking-widest font-semibold mb-5">Trusted by rehab clinics</p>
        <h2 className="text-5xl font-bold text-[#1a1208] mb-8 leading-tight">
          Ready to see it <span className="text-[#e8622c]">live?</span>
        </h2>
        <button
          onClick={onSignUp}
          className="inline-flex items-center gap-2 bg-[#1a1208] text-[#f2ece0] font-semibold px-8 py-4 rounded-full hover:bg-[#2d2010] transition-colors text-base"
        >
          Create your account
          <ArrowRight className="w-4 h-4" />
        </button>
      </div>
    </motion.div>
  )
}

function AuthForm({
  mode,
  onSwitch,
  onSuccess,
}: {
  mode: 'signin' | 'signup'
  onSwitch: () => void
  onSuccess: () => void
}) {
  const [showPassword, setShowPassword] = useState(false)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const isSignUp = mode === 'signup'

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      if (isSignUp) {
        await register(email, password, name)
      } else {
        await login(email, password)
      }
      onSuccess()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong')
    } finally {
      setLoading(false)
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -16 }}
      transition={{ duration: 0.25 }}
      className="flex items-center justify-center min-h-[calc(100vh-88px)] px-4 relative"
    >
      {/* Sun decoration behind form */}
      <div className="absolute top-[-80px] right-[-80px] text-[#e8622c]/10 pointer-events-none">
        <SunIcon size={480} />
      </div>

      <div className="w-full max-w-md relative z-10">
        <div className="bg-[#faf7f2] border border-[#e0d8cc] rounded-3xl p-10 shadow-sm">
          {/* Form header */}
          <div className="flex items-center gap-2 mb-1">
            <div className="text-[#e8622c]">
              <SunIcon size={20} />
            </div>
            <span className="text-xs font-semibold text-[#1a1208]/40 uppercase tracking-widest">Solstice</span>
          </div>
          <h2 className="text-3xl font-bold text-[#1a1208] mt-3 mb-1">
            {isSignUp ? 'Create account' : 'Welcome back'}
          </h2>
          <p className="text-[#1a1208]/50 mb-8">
            {isSignUp
              ? 'Start monitoring your rehab room today.'
              : 'Sign in to your Solstice dashboard.'}
          </p>

          {error && (
            <div className="px-4 py-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            {isSignUp && (
              <div>
                <label className="block text-xs font-semibold text-[#1a1208]/50 uppercase tracking-wider mb-1.5">
                  Full Name
                </label>
                <input
                  type="text"
                  value={name}
                  onChange={e => setName(e.target.value)}
                  placeholder="Dr. Jane Smith"
                  required
                  className="w-full px-4 py-3 bg-[#f2ece0] border border-[#e0d8cc] rounded-xl text-[#1a1208] placeholder-[#1a1208]/25 focus:outline-none focus:border-[#1a1208]/50 transition-colors"
                />
              </div>
            )}

            <div>
              <label className="block text-xs font-semibold text-[#1a1208]/50 uppercase tracking-wider mb-1.5">
                Email
              </label>
              <input
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                placeholder="you@clinic.com"
                required
                className="w-full px-4 py-3 bg-[#f2ece0] border border-[#e0d8cc] rounded-xl text-[#1a1208] placeholder-[#1a1208]/25 focus:outline-none focus:border-[#1a1208]/50 transition-colors"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-[#1a1208]/50 uppercase tracking-wider mb-1.5">
                Password
              </label>
              <div className="relative">
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  placeholder="••••••••"
                  required
                  className="w-full px-4 py-3 bg-[#f2ece0] border border-[#e0d8cc] rounded-xl text-[#1a1208] placeholder-[#1a1208]/25 focus:outline-none focus:border-[#1a1208]/50 transition-colors pr-12"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(p => !p)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-[#1a1208]/30 hover:text-[#1a1208]/60 transition-colors"
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            {isSignUp && (
              <div>
                <label className="block text-xs font-semibold text-[#1a1208]/50 uppercase tracking-wider mb-1.5">
                  Clinic / Organization
                </label>
                <input
                  type="text"
                  placeholder="Sunrise Physical Therapy"
                  className="w-full px-4 py-3 bg-[#f2ece0] border border-[#e0d8cc] rounded-xl text-[#1a1208] placeholder-[#1a1208]/25 focus:outline-none focus:border-[#1a1208]/50 transition-colors"
                />
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-[#1a1208] text-[#f2ece0] font-semibold py-3.5 rounded-xl hover:bg-[#2d2010] transition-colors disabled:opacity-60 mt-2 flex items-center justify-center gap-2"
            >
              {loading ? (
                <>
                  <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  {isSignUp ? 'Creating account...' : 'Signing in...'}
                </>
              ) : (
                isSignUp ? 'Create Account' : 'Sign In'
              )}
            </button>
          </form>

          {/* Divider */}
          <div className="mt-6 flex items-center gap-3">
            <div className="flex-1 h-px bg-[#e0d8cc]" />
            <span className="text-xs text-[#1a1208]/30 font-medium">or</span>
            <div className="flex-1 h-px bg-[#e0d8cc]" />
          </div>

          {/* Google OAuth */}
          <button
            type="button"
            onClick={() => { window.location.href = googleLoginUrl() }}
            className="mt-4 w-full flex items-center justify-center gap-3 py-3 border border-[#e0d8cc] rounded-xl text-sm text-[#1a1208]/70 hover:bg-[#f2ece0] transition-colors font-medium"
          >
            <svg className="w-4 h-4" viewBox="0 0 24 24">
              <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
              <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
              <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z"/>
              <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
            </svg>
            Continue with Google
          </button>

          <div className="mt-5 text-center">
            <p className="text-sm text-[#1a1208]/50">
              {isSignUp ? 'Already have an account?' : "Don't have an account?"}{' '}
              <button
                onClick={onSwitch}
                className="text-[#1a1208] font-semibold hover:underline"
              >
                {isSignUp ? 'Sign in' : 'Sign up'}
              </button>
            </p>
          </div>

          {!isSignUp && (
            <div className="mt-8 pt-6 border-t border-[#e0d8cc]">
              <p className="text-xs text-center text-[#1a1208]/30 mb-3">Demo access</p>
              <button
                onClick={onSuccess}
                className="w-full py-3 border border-[#e0d8cc] rounded-xl text-sm text-[#1a1208]/60 hover:bg-[#f2ece0] transition-colors font-medium"
              >
                Continue as Demo User →
              </button>
            </div>
          )}
        </div>
      </div>
    </motion.div>
  )
}
