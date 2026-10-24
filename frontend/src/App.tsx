import { useEffect, useRef, useState } from 'react'
import { analyze, getMeta } from './api'
import type { Analysis, Limit, Meta, Params } from './types'
import { TopTab } from './components/TopTab'
import { ClustersTab } from './components/ClustersTab'
import { SimTab } from './components/SimTab'
import { CompareTab } from './components/CompareTab'
import { ModelTab } from './components/ModelTab'

const TABS = ['🏆 Top 5 Locations', '🧩 Zone Clusters', '🎲 Simulation & What-If', '⚖️ Compare & Ranking', '🧠 Model & Assumptions']

// Starting values and allowed ranges come from the API (/api/meta), so they are defined once, in the backend.
const defaultsFrom = (m: Meta) =>
  Object.fromEntries(Object.entries(m.params).map(([k, v]) => [k, v.default])) as unknown as Params

function Slider(props: { label: string; value: number; lim: Limit; step?: number; onChange: (v: number) => void }) {
  return (
    <>
      <label>{props.label}<b>{props.value}</b></label>
      <input type="range" min={props.lim.minimum} max={props.lim.maximum} step={props.step ?? 1} value={props.value}
        onChange={e => props.onChange(Number(e.target.value))} />
    </>
  )
}

export default function App() {
  const [meta, setMeta] = useState<Meta | null>(null)
  const [p, setP] = useState<Params | null>(null)
  const [data, setData] = useState<Analysis | null>(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [tab, setTab] = useState(() => Number(location.hash.replace('#tab=', '')) || 0)
  const [sel, setSel] = useState(1)
  const set = <K extends keyof Params>(k: K, v: Params[K]) => setP(prev => prev && ({ ...prev, [k]: v }))
  const abort = useRef<AbortController | null>(null)

  useEffect(() => {
    getMeta().then(m => { setMeta(m); setP(defaultsFrom(m)) }).catch(e => setErr(`Cannot reach the API (${e.message}). Start the backend: uvicorn app.main:app --port 8000`))
  }, [])

  useEffect(() => {
    if (!p) return
    const t = setTimeout(() => {
      abort.current?.abort()
      const ac = new AbortController()
      abort.current = ac
      setBusy(true)
      analyze(p, ac.signal)
        .then(d => { setData(d); setErr(''); setSel(s => (d.empty || s > d.top.length ? 1 : s)); setBusy(false) })
        .catch(e => { if (e.name !== 'AbortError') { setErr(String(e.message)); setBusy(false) } })
    }, 350)
    return () => clearTimeout(t)
  }, [p])

  if (!meta || !p) {
    return <main>{err ? <div className="err">{err}</div> : <p>Connecting to the API…</p>}</main>
  }
  const lim = meta.params
  const icon = meta.domains.find(d => d.name === p.domain)?.icon ?? '📍'
  return (
    <div className="layout">
      <aside>
        <h2 style={{ margin: 0 }}>🏪 Your business</h2>
        <label>Business domain</label>
        <select value={p.domain} onChange={e => set('domain', e.target.value)}>
          {meta.domains.map(d => <option key={d.name} value={d.name}>{d.icon} {d.name}</option>)}
        </select>
        <label>City to expand in</label>
        <select value={p.city} onChange={e => set('city', e.target.value)}>
          {meta.cities.map(c => <option key={c}>{c}</option>)}
        </select>
        <Slider label="Existing stores (training data)" value={p.n_stores} lim={lim.n_stores} step={5} onChange={v => set('n_stores', v)} />
        <h3>🎯 Strategy</h3>
        <select value={p.preset} onChange={e => set('preset', e.target.value)}>
          {Object.keys(meta.presets).map(k => <option key={k}>{k}</option>)}
        </select>
        <h3>🚧 Constraints</h3>
        <Slider label="Max rent (Rs/sq ft/month)" value={p.max_rent} lim={lim.max_rent} step={5} onChange={v => set('max_rent', v)} />
        <label>Investment budget per store (Rs lakh)</label>
        <input type="number" min={lim.max_capex.minimum} max={lim.max_capex.maximum} step={10} value={p.max_capex} onChange={e => set('max_capex', Number(e.target.value))} />
        <Slider label="Min vacant units in zone" value={p.min_units} lim={lim.min_units} onChange={v => set('min_units', v)} />
        <Slider label="Min distance from our stores (km)" value={p.min_own_km} lim={lim.min_own_km} step={0.5} onChange={v => set('min_own_km', v)} />
        <Slider label="Min spacing between picks (km)" value={p.min_sep_km} lim={lim.min_sep_km} step={0.5} onChange={v => set('min_sep_km', v)} />
        <p className="mute" style={{ marginTop: 18 }}>
          Data store: {meta.db.engine}{meta.db.postgis ? ' + PostGIS' : ''}<br />
          AI briefings: {meta.llm_provider ?? 'templates (no LLM key set)'}
        </p>
      </aside>
      <main>
        <div className="hero">
          <h1>📍 Retail Expansion Intelligence Platform</h1>
          <p>{icon} {p.domain} · {p.city} · learns from your {p.n_stores} existing stores to find the best location for the next one</p>
        </div>
        {err && <div className="err">{err}</div>}
        <div className="tabs">
          {TABS.map((t, i) => <button key={t} className={i === tab ? 'on' : ''} onClick={() => { setTab(i); history.replaceState(null, '', '#tab=' + i) }}>{t}</button>)}
        </div>
        {!data && !err && <p>Simulating the city and training the demand model… (first run takes a few seconds)</p>}
        {data?.empty && <div className="err">{data.message}</div>}
        {data && !data.empty && (
          <div className={busy ? 'loading' : ''}>
            {tab === 0 && <TopTab data={data} p={p} sel={sel} setSel={setSel} />}
            {tab === 1 && <ClustersTab data={data} k={p.k} lim={lim.k} setK={v => set('k', v)} />}
            {tab === 2 && <SimTab data={data} p={p} sel={sel} lim={meta.sim_params} />}
            {tab === 3 && <CompareTab data={data} />}
            {tab === 4 && <ModelTab data={data} p={p} />}
          </div>
        )}
      </main>
    </div>
  )
}
