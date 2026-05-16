// Patient screens are mobile-shaped and own their own background — no admin
// sidebar / app shell. Centred content with a max-w-md column so it looks
// reasonable on a desktop too.
export default function PatientLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen min-h-dvh bg-[#f2ece0] text-[#1a1208] flex flex-col items-center">
      <div className="w-full max-w-md flex-1 flex flex-col px-6 py-8">
        {children}
      </div>
    </div>
  )
}
