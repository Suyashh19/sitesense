import { Icon } from './Icon'
import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import type { Range } from './types'

export const lakh = (v: number | null | undefined, d = 1) => (v == null ? '–' : `Rs ${v < 0 ? '−' : ''}${Math.abs(v).toFixed(d)} lakh`)
export const num = (v: number) => Math.round(v).toLocaleString('en-IN')

const BAND: Record<string, string> = { Prime: 'good', Strong: 'good', Viable: 'brand', Marginal: 'warn', Avoid: 'bad' }
export const Band = ({ band, boi }: { band: string; boi?: number }) => <span className={`chip ${BAND[band] ?? ''}`}>{band}{boi != null ? ` · ${boi.toFixed(0)}/100` : ''}</span>
export const Conf = ({ c }: { c: string }) => <span className={`chip ${c === 'High' ? 'good' : c === 'Low' ? 'bad' : 'warn'}`}>{c} confidence</span>

/** P10-P90 bar with the median marked, on a shared scale [lo, hi]. */
export function RangeBar({ r, lo, hi, unit = 'lakh/month' }: { r: Range; lo: number; hi: number; unit?: string }) {
  const pos = (v: number) => `${Math.max(0, Math.min(100, ((v - lo) / (hi - lo || 1)) * 100))}%`
  return (
    <div>
      <div className="range">
        <i style={{ left: pos(r.p10), width: `calc(${pos(r.p90)} - ${pos(r.p10)})` }} />
        <u style={{ left: pos(r.p50) }} />
      </div>
      <div className="rl"><span>weak case {r.p10.toFixed(1)}</span><span>likely {r.p50.toFixed(1)}</span><span>strong case {r.p90.toFixed(1)} {unit}</span></div>
    </div>
  )
}

export function FactorBars({ factors, names, weights }: { factors: Record<string, number | null>; names: Record<string, string>; weights?: Record<string, number> }) {
  return (
    <div className="bars">
      {Object.keys(names).map(k => (
        <div className="row" key={k} title={weights ? `Matters ${weights[k]}% for this business` : undefined}>
          <span>{names[k]}{weights ? <small style={{ color: 'var(--mute)' }}> · {weights[k]}%</small> : null}</span>
          <div className="track"><div className="fill" style={{ width: `${factors[k] ?? 0}%` }} /></div>
          <b>{factors[k] == null ? '–' : factors[k]}</b>
        </div>
      ))}
    </div>
  )
}

export const Note = ({ children, warn }: { children: ReactNode; warn?: boolean }) => <div className={`note${warn ? ' warn' : ''}`}>{children}</div>
export const Busy = ({ children }: { children: ReactNode }) => <p><span className="spin" />{children}</p>

export const KIND: Record<string, { label: string; cls: string }> = {
  real: { label: 'real data', cls: 'tag-real' }, modelled: { label: 'modelled', cls: 'tag-est' },
  estimated: { label: 'estimate', cls: 'tag-est' }, indicator: { label: 'indicator', cls: 'tag-est' }, assumption: { label: 'assumption', cls: 'tag-est' },
}

/** Red banner with a close button; hides itself after `seconds` (the timer restarts whenever the message changes). */
export function ErrorBanner({ msg, onClose, seconds = 12 }: { msg: string; onClose?: () => void; seconds?: number }) {
  const [gone, setGone] = useState(false)
  useEffect(() => {
    setGone(false)
    const t = setTimeout(() => { setGone(true); onClose?.() }, seconds * 1000)
    return () => clearTimeout(t)
  }, [msg]) // eslint-disable-line react-hooks/exhaustive-deps
  if (gone) return null
  const [title, ...rest] = msg.split('\n')
  return (
    <div className="err toast" role="alert">
      <Icon name="warning" size={20} />
      <div style={{ flex: 1 }}><b>{title}</b>{rest.map((r, i) => <div key={i}>{r}</div>)}</div>
      <button className="x" aria-label="Close message" title="Close" onClick={() => { setGone(true); onClose?.() }}><Icon name="close" size={16} /></button>
    </div>
  )
}

/** Blue information note with a close button; hides itself after `seconds` unless seconds is 0. */
export function Dismissible({ children, warn, seconds = 20, resetKey }: { children: ReactNode; warn?: boolean; seconds?: number; resetKey?: unknown }) {
  const [gone, setGone] = useState(false)
  useEffect(() => {
    setGone(false)
    if (!seconds) return
    const t = setTimeout(() => setGone(true), seconds * 1000)
    return () => clearTimeout(t)
  }, [resetKey, seconds])
  if (gone) return null
  return (
    <div className={`note toast${warn ? ' warn' : ''}`}>
      <div style={{ flex: 1 }}>{children}</div>
      <button className="x" aria-label="Close message" title="Close" onClick={() => setGone(true)}><Icon name="close" size={16} /></button>
    </div>
  )
}
