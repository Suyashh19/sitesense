import { Icon } from './Icon'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { analyze, getLayer, getMeta } from './api'
import type { Analysis, AskResult, Layer, Meta, Params, Point } from './types'
import { Controls } from './components/Controls'
import { MapView } from './components/MapView'
import type { ClickMode, MapMode } from './components/MapView'
import { Funnel, SiteDetail, SiteList } from './components/Results'
import { WhatIf } from './components/WhatIf'
import { Plan } from './components/Plan'
import { DataTrust } from './components/DataTrust'
import { Busy, Dismissible, ErrorBanner, Note } from './ui'

type Tab = 'find' | 'whatif' | 'plan' | 'data'
const TABS: [Tab, string][] = [['find', '1  Find sites'], ['whatif', '2  What-if'], ['plan', '3  Expansion plan'], ['data', '4  Data & trust']]
const MODES: [MapMode, string][] = [['fit', 'Market fit'], ['profit', 'Profit'], ['competition', 'Competition'], ['population', 'Population']]

const defaults = (m: Meta): Params => ({
  category: m.categories[0].key, budget_lakh: null, max_rent_psf: null, min_pop_1km: 0, strategy: 'Balanced', brand_tier: 'regional_chain',
  own_stores: [], extra_competitors: [], rent_change_pct: 0, n_results: Number(m.limits.n_results?.default ?? 5),
  min_spacing_km: Number(m.limits.min_spacing_km?.default ?? 1.5), keep_away_km: Number(m.limits.keep_away_km?.default ?? 0.8), near: null, overrides: {},
})

export default function App() {
  const [meta, setMeta] = useState<Meta | null>(null)
  const [params, setParams] = useState<Params | null>(null)
  const [a, setA] = useState<Analysis | null>(null)
  const [layer, setLayer] = useState<Layer | null>(null)
  const [tab, setTab] = useState<Tab>('find')
  const [sel, setSel] = useState<string | null>(null)
  const [mode, setMode] = useState<MapMode>('fit')
  const [clickMode, setClickMode] = useState<ClickMode>('select')
  const [rivals, setRivals] = useState<Point[]>([])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [asked, setAsked] = useState<AskResult | null>(null)
  const [flyTo, setFlyTo] = useState<[number, number] | null>(null)
  const abort = useRef<AbortController | null>(null)

  const loadMeta = useCallback(() => getMeta().then(m => { setMeta(m); setParams(p => p ?? defaults(m)) })
    .catch(e => setErr(`Cannot reach the SiteSense API (${e.message}). Start the backend: run-backend.bat`)), [])
  useEffect(() => { loadMeta() }, [loadMeta])

  const run = useCallback((override?: Params) => {
    const p = override ?? params
    if (!p || !meta?.ready) return
    abort.current?.abort()
    const ac = new AbortController()
    abort.current = ac
    setBusy(true); setErr('')
    analyze(p, ac.signal)
      .then(r => { setA(r); setSel(r.empty ? null : r.top[0].h3); if (!r.empty) setFlyTo([r.top[0].lat, r.top[0].lon]); setBusy(false) })
      .catch(e => { if (e.name !== 'AbortError') { setErr(e.message); setBusy(false); setA(null) } })
  }, [params, meta?.ready])

  useEffect(() => { if (meta?.ready && params) getLayer(params.category).then(setLayer).catch(e => setErr(e.message)) }, [params?.category, meta?.ready]) // eslint-disable-line react-hooks/exhaustive-deps
  const first = useRef(true)
  useEffect(() => { if (meta?.ready && params && first.current) { first.current = false; run() } }, [meta?.ready, params, run])

  const set = (patch: Partial<Params>) => setParams(p => (p ? { ...p, ...patch } : p))
  const onMapClick = (pt: Point) => {
    if (clickMode === 'own') set({ own_stores: [...params!.own_stores, pt] })
    if (clickMode === 'rival') setRivals(r => [...r, pt])
  }
  const onAsk = (r: AskResult) => {
    setAsked(r)
    if (!r.grounded || !params || !meta) return
    const g = r.args as Record<string, unknown>
    const next: Params = { ...params, category: (g.category as string) ?? params.category, budget_lakh: (g.budget_lakh as number) ?? null,
      max_rent_psf: (g.max_rent_psf as number) ?? null, strategy: (g.strategy as string) ?? params.strategy, n_results: (g.n_results as number) ?? params.n_results,
      near: g.near ? { lat: (g.near as Point).lat, lon: (g.near as Point).lon, radius_km: 3 } : null }
    setParams(next); setTab(r.tool === 'plan_expansion' ? 'plan' : 'find'); run(next)
  }

  const sites = a && !a.empty ? a.top : []
  const site = useMemo(() => sites.find(t => t.h3 === sel) ?? null, [a, sel]) // eslint-disable-line react-hooks/exhaustive-deps
  const pick = (h: string) => { setSel(h); const t = sites.find(x => x.h3 === h); if (t) setFlyTo([t.lat, t.lon]) }
  const cat = meta?.categories.find(c => c.key === params?.category)

  if (!meta || !params) return <div style={{ padding: 24 }}>{err ? <div className="err">{err}</div> : <Busy>Connecting to SiteSense…</Busy>}</div>
  const center = meta.center ?? [(meta.city.bbox.north + meta.city.bbox.south) / 2, (meta.city.bbox.east + meta.city.bbox.west) / 2] as [number, number]

  return (
    <div className="app">
      <header className="top">
        <div className="logo">Site<span>Sense</span></div>
        <div className="tag">Where should your next store go? · {meta.city.name}</div>
        <nav className="tabs">{TABS.map(([k, n]) => <button key={k} className={tab === k ? 'on' : ''} onClick={() => setTab(k)}>{n}</button>)}</nav>
      </header>
      <div className="body">
        <Controls meta={meta} params={params} set={set} run={() => { setTab('find'); run() }} busy={busy} clickMode={clickMode} setClickMode={setClickMode} onAsk={onAsk} />
        <section className="main">
          {err && <ErrorBanner msg={err} onClose={() => setErr('')} />}
          {!meta.ready && tab !== 'data' && <Note warn>The data has not been built yet. Open <b>4 Data & trust</b> and press “Build data and models”.</Note>}
          {asked && tab !== 'data' && (
            <Dismissible warn={!asked.grounded} resetKey={asked}>
              <b>I understood:</b> {asked.grounded ? asked.executed_as : asked.clarify}
              {asked.notes.length > 0 && <div>{asked.notes.join('; ')}</div>}
              <div className="hint">You can change anything on the left and press “Find best locations” again.</div>
            </Dismissible>)}

          {tab === 'data' && <DataTrust meta={meta} onBuilt={() => { loadMeta(); run() }} />}

          {tab !== 'data' && meta.ready && (
            <>
              <div className="maptools">
                <b>Map shows:</b>
                <div className="seg">{MODES.map(([k, n]) => <button key={k} className={mode === k ? 'on' : ''} onClick={() => setMode(k)}>{n}</button>)}</div>
                <span className="hint" style={{ margin: 0 }}>{cat && <Icon name={cat.icon} size={15} />} {cat?.name} · click a numbered pin or any hexagon for details</span>
                {clickMode !== 'select' && <button className="btn sec sm" onClick={() => setClickMode('select')}>Done placing</button>}
              </div>
              <MapView center={center} layer={layer} mode={mode} sites={sites} selected={sel} flyTo={flyTo}
                own={params.own_stores} rivals={rivals} competitors={[]} clickMode={clickMode} onPick={pick} onMapClick={onMapClick} />
            </>
          )}

          {tab === 'find' && meta.ready && (
            <div className={busy ? 'busy' : ''} style={{ marginTop: 14 }}>
              {busy && !a && <Busy>Checking every zone, simulating customers and ranking the sites…</Busy>}
              {a?.empty && <Note warn><b>No site matches.</b> {a.message}</Note>}
              {a && !a.empty && (
                <>
                  <h3 style={{ margin: '0 0 8px' }}>How we got from the whole city to these sites</h3>
                  <Funnel f={a.funnel} total={layer?.h3.length} />
                  <p className="hint">Ordered by “{a.strategy}”: {Object.entries(a.strategy_weights).map(([k, v]) => `${k} ${(v * 100).toFixed(0)}%`).join(', ')}. Method: {a.model_used}.
                    Profit numbers are <b>estimates</b> from a simulation, shown as a likely value with a weak-case/strong-case range.</p>
                  <div className="grid2" style={{ alignItems: 'start' }}>
                    <SiteList a={a} sel={sel} onSel={pick} catName={cat?.name ?? ''} />
                    {site && <SiteDetail s={site} meta={meta} params={params} a={a} />}
                  </div>
                </>
              )}
            </div>
          )}
          {tab === 'whatif' && meta.ready && <div style={{ marginTop: 14 }}><WhatIf params={params} rivals={rivals} setRivals={setRivals} clickMode={clickMode} setClickMode={setClickMode} /></div>}
          {tab === 'plan' && meta.ready && <div style={{ marginTop: 14 }}><Plan params={params} onPick={h => { pick(h) }} /></div>}
        </section>
      </div>
    </div>
  )
}
