import type { Analysis, Briefing, Meta, Params, Point, SimResult } from './types'
import { BACKEND_URL } from './config'

async function req<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(BACKEND_URL + url, init)
  if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`)
  return r.json() as Promise<T>
}
const post = <T,>(url: string, body: unknown, signal?: AbortSignal) =>
  req<T>(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal })

export const getMeta = () => req<Meta>('/api/meta')
export const analyze = (p: Params, signal?: AbortSignal) => post<Analysis>('/api/analyze', p, signal)
export const simulate = (p: Params & { pick: number; extra_comp: number; rent_pct: number; own_km: number; extra_competitors: Point[] }, signal?: AbortSignal) =>
  post<SimResult>('/api/simulate', p, signal)
export const briefing = (p: Params, pick: number, signal?: AbortSignal) => post<Briefing>('/api/briefing', { ...p, pick }, signal)
export const nearby = (p: Params, lat: number, lon: number) =>
  req<{ zone_name: string; km: number }[]>(
    `/api/nearby?city=${encodeURIComponent(p.city)}&domain=${encodeURIComponent(p.domain)}&n_stores=${p.n_stores}&lat=${lat}&lon=${lon}`)
