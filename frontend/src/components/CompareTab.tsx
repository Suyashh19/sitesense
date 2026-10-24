import { useState } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { Analysis } from '../types'
import { PALETTE, n1 } from '../ui'

export function CompareTab({ data }: { data: Analysis }) {
  const { top, ranking } = data
  const [a, setA] = useState(1)
  const [b, setB] = useState(Math.min(2, top.length))
  const A = top.find(t => t.pick === a) ?? top[0]
  const B = top.find(t => t.pick === b) ?? top[0]
  const comps = Object.keys(top[0].components)
  const stack = top.map(t => ({ site: `#${t.pick} ${t.zone_name}`, ...t.components }))
  const drivers = Object.keys(A.contrib).map(k => ({ k, v: A.contrib[k] - B.contrib[k] })).sort((x, y) => x.v - y.v)
  const rows: [string, string | number, string | number][] = [
    ['Predicted sales (L/mo)', n1(A.pred_revenue), n1(B.pred_revenue)], ['Profit (L/mo)', n1(A.profit), n1(B.profit)],
    ['Pessimistic profit (L/mo)', n1(A.profit_p10), n1(B.profit_p10)], ['Payback (months)', n1(A.payback_months), n1(B.payback_months)],
    ['Rent (Rs/sqft)', A.rent_psf, B.rent_psf], ['Competitors within 1 km', A.competitors_1km, B.competitors_1km],
    ['Distance to our nearest store (km)', A.own_nearest_km, B.own_nearest_km], ['Vacant units', A.vacant_units, B.vacant_units],
    ['Zone type', A.archetype, B.archetype]]
  const csv = () => {
    const cols = Object.keys(ranking[0])
    const blob = new Blob([[cols.join(','), ...ranking.map(r => cols.map(c => JSON.stringify(r[c] ?? '')).join(','))].join('\n')], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    Object.assign(document.createElement('a'), { href: url, download: 'ranking.csv' }).click()
    URL.revokeObjectURL(url)
  }
  return (
    <>
      <div className="panel">
        <h4>Score breakdown of the picks</h4>
        <ResponsiveContainer width="100%" height={320}>
          <BarChart data={stack} layout="vertical" margin={{ left: 40 }}><CartesianGrid strokeDasharray="3 3" />
            <XAxis type="number" /><YAxis type="category" dataKey="site" width={190} tick={{ fontSize: 12 }} /><Tooltip formatter={(v) => Number(v).toFixed(1)} /><Legend />
            {comps.map((c, i) => <Bar isAnimationActive={false} key={c} dataKey={c} stackId="s" fill={PALETTE[i]} />)}
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="grid-eq">
        <div className="panel">
          <h4>Head-to-head</h4>
          <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
            <select value={a} onChange={e => setA(Number(e.target.value))}>{top.map(t => <option key={t.pick} value={t.pick}>Site A: #{t.pick}</option>)}</select>
            <select value={b} onChange={e => setB(Number(e.target.value))}>{top.map(t => <option key={t.pick} value={t.pick}>Site B: #{t.pick}</option>)}</select>
          </div>
          <table><thead><tr><th>Metric</th><th>#{A.pick}</th><th>#{B.pick}</th></tr></thead>
            <tbody>{rows.map(([m, x, y]) => <tr key={m}><td>{m}</td><td>{x}</td><td>{y}</td></tr>)}</tbody></table>
        </div>
        <div className="panel">
          <h4>Why #{A.pick} beats / loses to #{B.pick} (sales impact by driver, %)</h4>
          <ResponsiveContainer width="100%" height={380}>
            <BarChart data={drivers} layout="vertical" margin={{ left: 70 }}><CartesianGrid strokeDasharray="3 3" />
              <XAxis type="number" /><YAxis type="category" dataKey="k" width={230} tick={{ fontSize: 11 }} /><Tooltip formatter={(v) => `${Number(v).toFixed(1)}%`} />
              <Bar isAnimationActive={false} dataKey="v">{drivers.map(d => <Cell key={d.k} fill={d.v >= 0 ? '#1e9646' : '#d23c32'} />)}</Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
      <div className="panel">
        <h4>Full ranking of every viable vacant zone <button className="btn" style={{ float: 'right' }} onClick={csv}>⬇ Download CSV</button></h4>
        <div className="scroll">
          <table>
            <thead><tr>{Object.keys(ranking[0]).map(c => <th key={c}>{c.replace(/_/g, ' ')}</th>)}</tr></thead>
            <tbody>{ranking.map(r => <tr key={String(r.zone_id)}>{Object.keys(r).map(c => <td key={c}>{typeof r[c] === "number" ? +(r[c] as number).toFixed(2) : r[c]}</td>)}</tr>)}</tbody>
          </table>
        </div>
      </div>
    </>
  )
}
