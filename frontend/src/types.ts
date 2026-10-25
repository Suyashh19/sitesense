export interface Point { lat: number; lon: number }
export interface Limit { default?: number | string; minimum?: number; maximum?: number }
export interface Category {
  key: string; name: string; icon: string; blurb: string; dna: Record<string, number>; behaviour: string
  defaults: { size_sqft: number; margin: number; fixed_lakh: number; spend_per_person: number }
}
export interface Meta {
  ready: boolean
  city: { name: string; bbox: Record<string, number>; h3_resolution: number; localities: { name: string; lat: number; lon: number }[] }
  center?: [number, number]
  categories: Category[]
  factor_groups: Record<string, string>
  strategies: Record<string, Record<string, number>>
  tiers: Record<string, number>
  limits: Record<string, Limit>
  db: { engine: string; postgis: boolean }
  llm_provider: string | null
  dna_version: number
}
export interface Params {
  category: string
  budget_lakh?: number | null
  max_rent_psf?: number | null
  min_pop_1km: number
  strategy: string
  brand_tier: string
  own_stores: Point[]
  extra_competitors: Point[]
  rent_change_pct: number
  n_results: number
  min_spacing_km: number
  keep_away_km: number
  near?: { lat: number; lon: number; radius_km: number } | null
  overrides: { margin?: number; fixed_lakh?: number; size_sqft?: number; spend_per_person?: number }
}
export interface Range { p10: number; p50: number; p90: number }
export interface Driver { group: string; name: string; text: string; strength: number; weight: number; score: number | null }
export interface Risk { type: string; text: string }
export interface Site {
  rank: number; h3: string; lat: number; lon: number; name: string; fit_score: number; boi: number; band: string; rank_pct: number | null
  archetype: string; confidence: 'High' | 'Medium' | 'Low'; confidence_score: number
  revenue: Range; profit: Range; p_profit: number; cannibalisation_pct: number
  rent_psf: number; rent_lakh: number; upfront_lakh: number; payback_months: number | null
  population_1km: number; competitors_1km: number; factors: Record<string, number | null>
  drivers: Driver[]; risks: Risk[]; coverage: number; why_over_next: string | null
}
export interface Assumption { name: string; value: string; source: string; kind: string }
export interface Analysis {
  empty: boolean; message?: string; funnel: Record<string, number>
  top: Site[]; strategy: string; strategy_weights: Record<string, number>; n_candidates: number; scenario: boolean
  model_used: string; assumptions: Assumption[]; dna_version: number
}
export interface Layer { h3: string[]; boi: (number | null)[]; fit: (number | null)[]; profit: (number | null)[]; competitors: number[]; pop: number[]; rent: (number | null)[]; arch: string[] }
export interface ZoneProfile {
  h3: string; lat: number; lon: number; name: string; archetype: string; boi: number; band: string
  values: { label: string; value: string; kind: string; source: string }[]
  factors: Record<string, number | null>
  category_fit: { key: string; name: string; icon: string; boi: number; band: string }[]
}
export interface Economics {
  revenue: Range; profit: Range; p_profit: number; cannibalisation_pct: number; upfront_lakh: number
  hist: { x: number; n: number }[]
  breakdown: { revenue: number; gross_margin: number; fixed_costs: number; rent: number; profit: number }
  sensitivity: { factor: string; down: number; up: number }[]
  competitors: { name: string; km: number; tier: string; lat: number; lon: number }[]
  assumptions: Assumption[]
}
export interface ScenarioResult {
  empty: boolean; message?: string; before: Site[]; after: Site[]
  rows: { h3: string; name: string; rank_before: number | null; rank_after: number; profit_before: number | null; profit_after: number; survives: boolean }[]
  dropped: { name: string; rank_before: number }[]
}
export interface PlanResult {
  feasible: boolean; message?: string
  chosen?: { step: number; h3: string; name: string; lat: number; lon: number; profit_p50: number; rev_p50: number; upfront: number; confidence: string; boi: number }[]
  net_profit?: number; greedy_net_profit?: number | null; upfront?: number; cannibalisation_cost?: number; binding?: string[]; candidates_considered?: number
}
export interface AskResult {
  tool: string; args: Record<string, unknown>; missing: string[]; notes: string[]; grounded: boolean; clarify?: string; executed_as: string
  result: (Analysis & PlanResult) | null
}
export interface PipelineStatus {
  ready: boolean
  status: null | {
    city: string; finished: string; seconds: number
    stages: { name: string; detail: string; seconds: number; source?: string; real?: boolean }[]
    meta: {
      categories: Record<string, {
        labels: { source: string; positives: number; zones: number }; enabled: boolean; reason?: string
        m2?: Record<string, number | string>; m3?: Record<string, number>; importance?: Record<string, number>
        competitors: number; chains: number; median_profit_lakh: number; viable_share: number
      }>
      rent: { n_localities: number; loo_mape: number; baseline_mape: number; model: string }
      archetype_silhouette: number; grid: { zones: number; analysed: number; res: number }; osm_counts: Record<string, number>
    }
  }
  job: { running: boolean; error: string | null; finished: string | null }
  log: string[]
}
