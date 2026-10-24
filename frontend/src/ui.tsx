import type { ReactNode } from 'react'

export const PALETTE = ['#1e6fd9', '#e8590c', '#2f9e44', '#9c36b5', '#c2255c', '#0c8599', '#f08c00']
export const colorFor = (names: string[]) => (n: string) => PALETTE[Math.max(0, names.indexOf(n)) % PALETTE.length]

export function Kpi({ label, value }: { label: string; value: ReactNode }) {
  return <div className="kpi"><div className="l">{label}</div><div className="v">{value}</div></div>
}

/** Render **bold** markers from the API as <b>. */
export function Rich({ text }: { text: string }) {
  return <>{text.split(/\*\*(.+?)\*\*/g).map((s, i) => (i % 2 ? <b key={i}>{s}</b> : <span key={i}>{s.replace(/\*(.+?)\*/g, '$1')}</span>))}</>
}

export const n1 = (v: number | null | undefined) => (v == null ? '–' : v.toFixed(1))
export const rs = (v: number) => `Rs ${v.toFixed(1)} L`
