import type { Analysis, AskResult, Economics, Layer, Meta, Params, PipelineStatus, PlanResult, ScenarioResult, ZoneProfile } from './types'
import { BACKEND_URL } from './config'

const FIELDS: Record<string, string> = {
  budget_lakh: 'Total money to start the store', max_rent_psf: 'Highest rent you can pay', min_pop_1km: 'Minimum residents nearby',
  size_sqft: 'Store size', n_results: 'How many sites to show', min_spacing_km: 'Spacing between sites', keep_away_km: 'Distance from your stores',
  margin: 'Margin', fixed_lakh: 'Fixed monthly cost', spend_per_person: 'Spend per person', rent_change_pct: 'Rent change',
  new_rent_change_pct: 'Rent change', k: 'Number of stores', total_budget_lakh: 'Total budget for all stores', radius_km: 'Search radius',
}
const LIMIT_TEXT = (m: string) => m.replace('Input should be greater than or equal to', 'must be at least').replace('Input should be less than or equal to', 'must be at most')
  .replace('Input should be a valid number, unable to parse string as a number', 'must be a number').replace(/^Input should be /, 'must be ')

/** Turns any failure into a short title plus a line saying what to do (shown in the red banner). */
async function fail(r: Response): Promise<never> {
  let body: unknown = null
  const text = await r.text()
  try { body = JSON.parse(text) } catch { /* not JSON */ }
  const detail = (body as { detail?: unknown } | null)?.detail
  if (r.status === 422 && Array.isArray(detail)) {
    const lines = detail.map((d: { loc?: string[]; msg: string }) => {
      const field = FIELDS[String(d.loc?.[d.loc.length - 1])] ?? String(d.loc?.[d.loc.length - 1] ?? 'A field')
      return `• ${field} ${LIMIT_TEXT(d.msg)}`
    })
    throw new Error(`Some of your settings are not valid\n${lines.join('\n')}\nFix them in the left panel and press “Find best locations” again.`)
  }
  if (r.status === 503) throw new Error(`The data has not been built yet\n${typeof detail === 'string' ? detail : 'Open “4 Data & trust” and press Build.'}`)
  if (r.status === 404) throw new Error(`That item was not found\n${typeof detail === 'string' ? detail : 'Try searching again.'}`)
  if (r.status === 400) throw new Error(`The request could not be used\n${typeof detail === 'string' ? detail : text}`)
  if (r.status >= 500) throw new Error(`The server hit a problem (error ${r.status})\nYour settings were fine. Try again in a moment; if it keeps happening, restart the backend and check its log window.`)
  throw new Error(`Unexpected response (${r.status})\n${text.slice(0, 200)}`)
}

async function req<T>(url: string, init?: RequestInit): Promise<T> {
  let r: Response
  try { r = await fetch(BACKEND_URL + url, init) } catch (e) {
    if ((e as Error).name === 'AbortError') throw e
    throw new Error('Cannot reach the SiteSense server\nStart the backend (run-backend.bat) and check that http://127.0.0.1:8000/api/health opens, then reload this page.')
  }
  if (!r.ok) await fail(r)
  return r.json() as Promise<T>
}
const post = <T,>(url: string, body: unknown, signal?: AbortSignal) =>
  req<T>(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal })

export const getMeta = () => req<Meta>('/api/meta')
export const getPipeline = () => req<PipelineStatus>('/api/pipeline')
export const runPipeline = () => post<{ started: boolean; message?: string }>('/api/pipeline/run', {})
export const getLayer = (category: string) => req<Layer>(`/api/layer/${category}`)
export const analyze = (p: Params, signal?: AbortSignal) => post<Analysis>('/api/analyze', p, signal)
export const getZone = (h3: string, category: string) => req<ZoneProfile>(`/api/zone/${h3}?category=${category}`)
export const economics = (p: Params, h3: string) => post<Economics>('/api/economics', { ...p, h3 })
export const scenario = (p: Params, newRent: number, newCompetitors: { lat: number; lon: number }[]) =>
  post<ScenarioResult>('/api/scenario', { ...p, new_rent_change_pct: newRent, new_competitors: newCompetitors })
export const plan = (p: Params, k: number, total?: number | null) => post<PlanResult>('/api/plan', { ...p, k, total_budget_lakh: total ?? null })
export const ask = (text: string) => post<AskResult>('/api/ask', { text })
export const briefing = (p: Params, rank: number) => post<{ text: string; source: string }>('/api/briefing', { ...p, rank })
