import { useEffect, useState } from 'react'
import { briefing, nearby } from '../api'
import type { Analysis, Briefing, Params } from '../types'
import { Kpi, Rich, n1 } from '../ui'
import { MapView } from './MapView'

export function TopTab({ data, p, sel, setSel }: { data: Analysis; p: Params; sel: number; setSel: (n: number) => void }) {
  const { top, kpis } = data
  const cur = top.find(t => t.pick === sel) ?? top[0]
  const [near, setNear] = useState<{ zone_name: string; km: number }[]>([])
  useEffect(() => {
    nearby(p, cur.lat, cur.lon).then(setNear).catch(() => setNear([]))
  }, [cur.zone_id, p.city, p.domain, p.n_stores])  // eslint-disable-line react-hooks/exhaustive-deps
  // template briefing arrives with the analysis; an LLM-written one (if a key is configured) replaces it when ready
  const [brief, setBrief] = useState<Briefing & { pick: number } | null>(null)
  useEffect(() => {
    const ac = new AbortController()
    briefing(p, cur.pick, ac.signal).then(b => setBrief({ ...b, pick: cur.pick })).catch(() => {})
    return () => ac.abort()
  }, [p, cur.pick])
  const shown = brief?.pick === cur.pick ? brief : { text: cur.briefing, source: 'template' }

  return (
    <>
      <div className="kpis">
        <Kpi label="Best site monthly profit" value={`Rs ${kpis.best_profit.toFixed(1)} L`} />
        <Kpi label="Portfolio profit (picks)" value={`Rs ${kpis.portfolio_profit.toFixed(1)} L/mo`} />
        <Kpi label="Avg. payback" value={`${kpis.avg_payback.toFixed(0)} months`} />
        <Kpi label="Viable sites found" value={`${kpis.viable} of ${kpis.vacant}`} />
      </div>
      {top.length < 5 && <p className="mute">Only {top.length} sites meet all constraints with the chosen spacing.</p>}
      <div className="pills">
        {top.map(t => (
          <button key={t.pick} className={t.pick === sel ? 'on' : ''} onClick={() => setSel(t.pick)}>#{t.pick} {t.zone_name}</button>
        ))}
      </div>
      <div className="grid2">
        <div>
          <MapView data={data} sel={sel} />
          <p className="mute">OpenStreetMap · use the layer control (top-right) for the profit heat-map, competition density and existing stores.</p>
        </div>
        <div>
          <div className="panel">
            <h3 style={{ margin: 0 }}>#{cur.pick} · {cur.zone_name}</h3>
            <p className="mute">Lat {cur.lat.toFixed(4)}, Lon {cur.lon.toFixed(4)} · suitability score <b>{cur.score.toFixed(0)}/100</b></p>
            <p><Rich text={cur.headline} /></p>
            <h4>Factor-wise breakdown</h4>
            {cur.cards.map(c => (
              <div key={c.name} className={`card ${c.verdict}`}>
                <div className="t"><span>{c.name}</span>
                  <span className={`pill ${c.verdict}`}>
                    {c.impact != null ? `${c.impact >= 0 ? '+' : ''}${c.impact.toFixed(0)}% sales` : { good: 'Favourable', bad: 'Weak', neutral: 'OK' }[c.verdict]}
                  </span>
                </div>
                <ul>{c.evidence.map((e, i) => <li key={i}><Rich text={e} /></li>)}</ul>
              </div>
            ))}
            <h4>✅ Why this location wins</h4>
            <ul className="tight">{(cur.why.length ? cur.why : ['Balanced profile - no single dominant strength.']).map((w, i) => <li key={i}><Rich text={w} /></li>)}</ul>
            <h4>⚠️ Risks</h4>
            <ul className="tight">{(cur.risks.length ? cur.risks : ['No material risk factors detected.']).map((w, i) => <li key={i}><Rich text={w} /></li>)}</ul>
            {cur.comparison.length > 0 && <><h4>🔁 Versus the alternative</h4><p><Rich text={cur.comparison[0]} /></p></>}
            <h4>📍 Our stores within 3 km</h4>
            <p className="mute">{near.length ? near.slice(0, 5).map(n => `${n.zone_name} (${n.km.toFixed(1)} km)`).join(' · ') : 'None - no overlap with existing stores.'}</p>
          </div>
        </div>
      </div>
      <div className="panel">
        <h4>📝 Executive briefing ({shown.source === 'template' ? "auto-generated from the model's outputs" : `written by ${shown.source} from the model's outputs; no other information added`})</h4>
        <p>{shown.text}</p>
      </div>
      <div className="panel scroll">
        <h4>Recommended sites at a glance</h4>
        <table>
          <thead><tr><th>Rank</th><th>Location</th><th>Zone type</th><th>Sales L/mo</th><th>Profit L/mo</th><th>Payback (mo)</th><th>ROI %/yr</th><th>Competitors</th><th>Rent/sqft</th><th>Vacant</th><th>Score</th></tr></thead>
          <tbody>{top.map(t => (
            <tr key={t.pick}><td>{t.pick}</td><td>{t.zone_name}</td><td>{t.archetype}</td><td>{n1(t.pred_revenue)}</td><td>{n1(t.profit)}</td>
              <td>{n1(t.payback_months)}</td><td>{t.roi_pct.toFixed(0)}</td><td>{t.competitors_1km}</td><td>{t.rent_psf}</td><td>{t.vacant_units}</td><td>{t.score.toFixed(0)}</td></tr>))}</tbody>
        </table>
      </div>
    </>
  )
}
