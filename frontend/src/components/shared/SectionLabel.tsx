'use client'
interface Props { children: React.ReactNode }

export default function SectionLabel({ children }: Props) {
  return (
    <p className="text-xs font-semibold uppercase tracking-widest text-slate-500 mb-1">{children}</p>
  )
}
