import { useEffect, useRef, useState } from 'react'
import { analyze, getMeta } from './api'
import type { Analysis, Meta, Params } from './types'
import { TopTab } from './components/TopTab'
import { ClustersTab } from './components/ClustersTab'
import { SimTab } from './components/SimTab'
import { CompareTab } from './components/CompareTab'
import { ModelTab } from './components/ModelTab'

const TABS = ['🏆 Top 5 Locations', '🧩 Zone Clusters', '🎲 Simulation & What-If', '⚖️ Compare & Ranking', '🧠 Model & Assumptions']

const DEFAULTS: Params = {
  city: 'Pune', domain: 'Luxury fashion boutique', n_stores: 60, preset: 'Balanced',
  max_rent: 250, max_capex: 300, min_units: 1, min_own_km: 1, min_sep_km: 3, k: 5,
}

function Slider(props: { label: string; value: number; min: number; max: number; step?: number; onChange: (v: number) => void }) {
  return (
    <>
      <label>{props.label}<b>{props.value}</b></label>
      <input type="range" min={props.min} max={props.max} step={props.step ?? 1} value={props.value}
        onChange={e => props.onChange(Number(e.target.value))} />
    </>
  )
}

export default function App() {
  const [meta, setMeta] = useState<Meta | null>(null)
  const [p, setP] = useState<Params>(DEFAULTS)
  const [data, setData] = useState<Analysis | null>(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [tab, setTab] = useState(() => Number(location.hash.replace('#tab=', '')) || 0)
  const [sel, setSel] = useState(1)
  const set = <K extends keyof Params>(k: K, v: Params[K]) => setP(prev => ({ ...prev, [k]: v }))
  const abort = useRef<AbortController | null>(null)

  useEffect(() => {
    getMeta().then(setMeta).catch(e => setErr(`Cannot reach the API (${e.message}). Start the backend: uvicorn app.main:app --port 8000`))
  }, [])

  useEffect(() => {
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

  const icon = meta?.domains.find(d => d.name === p.domain)?.icon ?? '📍'
  return (
    <div className="layout">
      <aside>
        <h2 style={{ margin: 0 }}>🏪 Your business</h2>
        <label>Business domain</label>
        <select value={p.domain} onChange={e => set('domain', e.target.value)}>
          {meta?.domains.map(d => <option key={d.name} value={d.name}>{d.icon} {d.name}</option>)}
        </select>
        <label>City to expand in</label>
        <select value={p.city} onChange={e => set('city', e.target.value)}>
          {meta?.cities.map(c => <option key={c}>{c}</option>)}
        </select>
        <Slider label="Existing stores (training data)" value={p.n_stores} min={30} max={100} step={5} onChange={v => set('n_stores', v)} />
        <h3>🎯 Strategy</h3>
        <select value={p.preset} onChange={e => set('preset', e.target.value)}>
          {meta && Object.keys(meta.presets).map(k => <option key={k}>{k}</option>)}
        </select>
        <h3>🚧 Constraints</h3>
        <Slider label="Max rent (Rs/sq ft/month)" value={p.max_rent} min={40} max={250} step={5} onChange={v => set('max_rent', v)} />
        <label>Investment budget per store (Rs lakh)</label>
        <input type="number" min={20} max={500} step={10} value={p.max_capex} onChange={e => set('max_capex', Number(e.target.value))} />
        <Slider label="Min vacant units in zone" value={p.min_units} min={1} max={5} onChange={v => set('min_units', v)} />
        <Slider label="Min distance from our stores (km)" value={p.min_own_km} min={0} max={4} step={0.5} onChange={v => set('min_own_km', v)} />
        <Slider label="Min spacing between picks (km)" value={p.min_sep_km} min={1} max={6} step={0.5} onChange={v => set('min_sep_km', v)} />
        <p className="mute" style={{ marginTop: 18 }}>
          Data store: {meta ? `${meta.db.engine}${meta.db.postgis ? ' + PostGIS' : ''}` : '…'}
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
            {tab === 1 && <ClustersTab data={data} k={p.k} setK={v => set('k', v)} />}
            {tab === 2 && <SimTab data={data} p={p} sel={sel} />}
            {tab === 3 && <CompareTab data={data} />}
            {tab === 4 && <ModelTab data={data} p={p} />}
          </div>
        )}
      </main>
    </div>
  )
}
