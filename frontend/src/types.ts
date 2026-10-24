export interface Params {
  city: string; domain: string; n_stores: number; preset: string
  weights?: Record<string, number>
  max_rent: number; max_capex: number; min_units: number; min_own_km: number; min_sep_km: number; k: number
}
export interface Meta {
  cities: string[]; domains: { name: string; icon: string }[]
  presets: Record<string, Record<string, number>>; labels: Record<string, string>
  db: { engine: string; postgis: boolean }
  params: Record<keyof Params, Limit>; sim_params: Record<string, Limit>
  llm_provider: string | null
}
export interface Limit { default: number | string; minimum?: number; maximum?: number }
export interface Point { lat: number; lon: number }
export interface Briefing { text: string; source: string }
export interface Card { name: string; impact: number | null; verdict: 'good' | 'bad' | 'neutral'; evidence: string[] }
export interface Site {
  pick: number; zone_id: string; zone_name: string; lat: number; lon: number; score: number
  pred_revenue: number; rev_p10: number; rev_p90: number; profit: number; profit_p10: number
  payback_months: number; roi_pct: number; archetype: string; rent_psf: number; vacant_units: number
  competitors_1km: number; own_nearest_km: number; population_k: number; income_index: number; opex_lakh: number
  components: Record<string, number>; headline: string; why: string[]; risks: string[]; comparison: string[]
  cards: Card[]; contrib: Record<string, number>; briefing: string
}
export interface Zone {
  zone_id: string; zone_name: string; lat: number; lon: number; has_store: boolean; profit: number; pred_revenue: number
  competitors_1km: number; rent_psf: number; income_index: number; population_k: number; archetype: string
  pc1: number; pc2: number; vacant_units: number
}
export interface Analysis {
  empty: boolean; message?: string
  kpis: { best_profit: number; portfolio_profit: number; avg_payback: number; viable: number; vacant: number }
  top: Site[]; weights: Record<string, number>; half: { lat: number; lon: number }; zones: Zone[]
  clusters: {
    silhouette: number; fit: Record<string, number | string>[]
    radar: { dims: string[]; series: { name: string; values: number[] }[] }
  }
  ranking: Record<string, number | string>[]
  model: {
    metrics: { cv_r2: number; cv_mape: number; n_train: number }; spearman: number; coverage_80: number
    importance: { feature: string; value: number }[]; cv: { actual: number; pred: number }[]
    assumptions: { size: number; margin: number; fixed: number; capex: number }
  }
}
export interface SimResult {
  mc: {
    p_profit: number; p_break_even: number; be_median: number | null; var5: number; roi24: number
    hist: { x: number; n: number }[]; fan: { month: number; p10: number; p50: number; p90: number }[]
  }
  base: { rev: number; profit: number; profit_p10: number }
  scenario: { rev: number; profit: number; profit_p10: number }
  resilience: { pick: number; zone_name: string; base: number; scenario: number; change: number; survives: boolean; placed_nearby: number }[]
  placed_nearby: number
}
