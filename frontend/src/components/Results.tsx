import { Icon } from '../Icon'
import { useEffect, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { briefing, economics, getZone } from '../api'
import type { Analysis, Economics, Meta, Params, Site, ZoneProfile } from '../types'
import { Band, Busy, Conf, ErrorBanner, FactorBars, KIND, Note, RangeBar, lakh, num } from '../ui'

const FUNNEL_HELP: Record<string, string> = {}

export function Funnel({ f, total }: { f: Record<string, number>; total?: number }) {
  const items = Object.entries(f)
  return (
    <div className="funnel" title="Every filter that was applied, and how many zones were left after each">
      {total != null && <div><b>{num(total)}</b>zones in the city grid</div>}
      {items.map(([k, v]) => (
        <span key={k} style={{ display: 'contents' }}>
          <div className="arrow">→</div>
          <div title={FUNNEL_HELP[k]}><b>{num(v)}</b>{k}</div>
        </span>
      ))}
    </div>
  )
}

export function SiteList({ a, sel, onSel, catName }: { a: Analysis; sel: string | null; onSel: (h: string) => void; catName: string }) {
  const lo = Math.min(...a.top.map(t => t.profit.p10), 0), hi = Math.max(...a.top.map(t => t.profit.p90))
  return (
    <div className="sites">
      {a.top.map(t => (
        <div key={t.h3} className={`site${t.h3 === sel ? ' on' : ''}`} onClick={() => onSel(t.h3)}>
          <div className="no">{t.rank}</div>
          <div>
            <h4>{t.name}</h4>
            <div className="chips" style={{ margin: '4px 0' }}>
              <Band band={t.band} boi={t.boi} /><Conf c={t.confidence} />
              <span className="chip">{t.archetype}</span>
              {t.cannibalisation_pct > 25 && <span className="chip warn">takes {t.cannibalisation_pct.toFixed(0)}% from your stores</span>}
            </div>
            <div style={{ fontSize: '.86rem' }}>{t.drivers[0]?.text}.</div>
            <RangeBar r={t.profit} lo={lo} hi={hi} />
          </div>
          <div className="money">
            <b>{lakh(t.profit.p50)}</b>
            <small>expected profit / month<br />{(t.p_profit * 100).toFixed(0)}% chance of profit<br />start-up cost {lakh(t.upfront_lakh, 0)}</small>
          </div>
        </div>
      ))}
      {a.top.length === 0 && <Note>No {catName} sites found.</Note>}
    </div>
  )
}

export function SiteDetail({ s, meta, params, a }: { s: Site; meta: Meta; params: Params; a: Analysis }) {
  const [zone, setZone] = useState<ZoneProfile | null>(null)
  const [eco, setEco] = useState<Economics | null>(null)
  const [brief, setBrief] = useState<{ text: string; source: string } | null>(null)
  const [err, setErr] = useState('')
  useEffect(() => {
    setZone(null); setEco(null); setBrief(null); setErr('')
    getZone(s.h3, params.category).then(setZone).catch(e => setErr(e.message))
    economics(params, s.h3).then(setEco).catch(e => setErr(e.message))
  }, [s.h3]) // eslint-disable-line react-hooks/exhaustive-deps
  const w = meta.categories.find(c => c.key === params.category)!.dna
  const money = eco ? [
    { name: 'Sales', v: eco.breakdown.revenue }, { name: 'After product cost', v: eco.breakdown.gross_margin },
    { name: 'Rent', v: -eco.breakdown.rent }, { name: 'Staff & other', v: -eco.breakdown.fixed_costs }, { name: 'Profit', v: eco.breakdown.profit }] : []
  return (
    <div className="card">
      <div style={{ display: 'flex', gap: 10, alignItems: 'baseline', flexWrap: 'wrap' }}>
        <h3 style={{ fontSize: '1.2rem' }}>#{s.rank} {s.name}</h3>
        <Band band={s.band} boi={s.boi} /><Conf c={s.confidence} />
      </div>
      <p className="hint">{s.archetype} area · {num(s.population_1km)} residents within 1 km · {s.competitors_1km} competing shops within 1 km · estimated rent Rs {s.rent_psf}/sq ft/month</p>
      {s.drivers.length > 0 && <>
        <h4>Why this area</h4>
        <ul className="why">{s.drivers.map(d => <li key={d.group}><b>{d.name}:</b> {d.text}</li>)}</ul>
      </>}
      <h4>What could go wrong</h4>
      <ul className="risk">{s.risks.map((r, i) => <li key={i}><b>{r.type}:</b> {r.text}</li>)}</ul>
      {s.why_over_next && <Note>{s.why_over_next}</Note>}
      <Note>Confidence is <b>{s.confidence}</b> because map coverage here is {(s.coverage * 100).toFixed(0)}%, the chance of profit is {(s.p_profit * 100).toFixed(0)}%
        {s.rank_pct != null ? ` and the learned ranker puts this zone in the top ${(100 - s.rank_pct).toFixed(0)}% of Pune` : ''}.</Note>
      {err && <ErrorBanner msg={err} onClose={() => setErr("")} />}
      <div className="grid2" style={{ marginTop: 10 }}>
        <div>
          <h4>How well it fits (0-100, higher is better)</h4>
          <FactorBars factors={s.factors} names={meta.factor_groups} weights={w} />
          <p className="hint">The percentage next to each name is how much that factor matters for {meta.categories.find(c => c.key === params.category)?.name}.</p>
        </div>
        <div>
          <h4>Where the money goes (Rs lakh per month, typical case)</h4>
          {!eco ? <Busy>Simulating customers…</Busy> : (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={money} margin={{ left: -10 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" /><XAxis dataKey="name" tick={{ fontSize: 10 }} interval={0} /><YAxis tick={{ fontSize: 10 }} />
                <Tooltip formatter={v => `Rs ${Number(v).toFixed(1)} lakh`} /><ReferenceLine y={0} stroke="var(--ink)" />
                <Bar dataKey="v">{money.map((m, i) => <Cell key={i} fill={m.v >= 0 ? '#1a8a4a' : '#c93a31'} />)}</Bar>
              </BarChart>
            </ResponsiveContainer>)}
        </div>
      </div>
      {eco && <div className="grid2">
        <div>
          <h4>What if something is different? <small style={{ fontWeight: 400 }}>(change in monthly profit)</small></h4>
          <table className="t"><thead><tr><th>Factor</th><th>If worse</th><th>If better</th></tr></thead><tbody>
            {eco.sensitivity.map(x => <tr key={x.factor}><td>{x.factor}</td><td style={{ color: x.down < 0 ? 'var(--bad)' : 'var(--good)' }}>{x.down >= 0 ? '+' : ''}{x.down.toFixed(1)}</td>
              <td style={{ color: x.up < 0 ? 'var(--bad)' : 'var(--good)' }}>{x.up >= 0 ? '+' : ''}{x.up.toFixed(1)}</td></tr>)}
          </tbody></table>
        </div>
        <div>
          <h4>Nearest competitors</h4>
          {eco.competitors.length === 0 ? <p className="hint">No mapped competitors within 1.5 km — an untested market, or thin map data.</p> :
            <table className="t"><tbody>{eco.competitors.slice(0, 6).map((c, i) => <tr key={i}><td>{c.name}</td><td>{c.km} km</td><td>{c.tier.replace('_', ' ')}</td></tr>)}</tbody></table>}
        </div>
      </div>}
      {zone && <details style={{ marginTop: 8 }}><summary><b>Every number behind this zone</b> (and whether it is real or estimated)</summary>
        <div className="kv" style={{ marginTop: 8 }}>
          {zone.values.map(v => <span key={v.label} style={{ display: 'contents' }}>
            <span>{v.label}</span><b>{v.value}</b>
            <span className="src"><span className={KIND[v.kind]?.cls}>{KIND[v.kind]?.label}</span> · {v.source}</span></span>)}
        </div>
        <h4 style={{ marginTop: 10 }}>How this zone suits all five businesses</h4>
        <div className="chips">{zone.category_fit.map(c => <span key={c.key} className="chip"><Icon name={c.icon} size={13} /> {c.name}: {c.boi.toFixed(0)} ({c.band})</span>)}</div>
      </details>}
      <details style={{ marginTop: 8 }}><summary><b>Assumptions used</b></summary>
        <table className="t"><tbody>{(eco?.assumptions ?? a.assumptions).map(x => <tr key={x.name}><td>{x.name}</td><td>{x.value}</td><td className="tag-est">{x.source}</td></tr>)}</tbody></table>
      </details>
      <div style={{ marginTop: 10 }}>
        <button className="btn sec sm" onClick={() => briefing(params, s.rank).then(setBrief).catch(e => setErr(e.message))}><Icon name="brief" /> Write a short briefing</button>
        {brief && <Note>{brief.text}<br /><small>source: {brief.source}</small></Note>}
      </div>
    </div>
  )
}
