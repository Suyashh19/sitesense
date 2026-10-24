import type { Analysis, Meta, Params, SimResult } from './types'

async function req<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, init)
  if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`)
  return r.json() as Promise<T>
}
const post = <T,>(url: string, body: unknown, signal?: AbortSignal) =>
  req<T>(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal })

export const getMeta = () => req<Meta>('/api/meta')
export const analyze = (p: Params, signal?: AbortSignal) => post<Analysis>('/api/analyze', p, signal)
export const simulate = (p: Params & { pick: number; extra_comp: number; rent_pct: number; own_km: number }, signal?: AbortSignal) =>
  post<SimResult>('/api/simulate', p, signal)
export const nearby = (p: Params, lat: number, lon: number) =>
  req<{ zone_name: string; km: number }[]>(
    `/api/nearby?city=${encodeURIComponent(p.city)}&domain=${encodeURIComponent(p.domain)}&n_stores=${p.n_stores}&lat=${lat}&lon=${lon}`)
