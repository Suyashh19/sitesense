import { useEffect, useState } from 'react'
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Legend, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Circle, CircleMarker, MapContainer, TileLayer, Tooltip as MapTip, useMapEvents } from 'react-leaflet'
import { simulate } from '../api'
import { TILE_ATTRIBUTION, TILE_URL } from '../config'
import type { Analysis, Limit, Params, Point, SimResult } from '../types'
import { Kpi, n1 } from '../ui'

function ClickToPlace({ onPlace }: { onPlace: (pt: Point) => void }) {
  useMapEvents({ click: e => onPlace({ lat: e.latlng.lat, lon: e.latlng.lng }) })
  return null
}

export function SimTab({ data, p, sel, lim }: { data: Analysis; p: Params; sel: number; lim: Record<string, Limit> }) {
  const [pick, setPick] = useState(sel)
  const [ec, setEc] = useState(Number(lim.extra_comp.default))
  const [rp, setRp] = useState(Number(lim.rent_pct.default))
  const [own, setOwn] = useState(Number(lim.own_km.default))
  const [placed, setPlaced] = useState<Point[]>([])
  const [res, setRes] = useState<SimResult | null>(null)
  const [err, setErr] = useState('')
  useEffect(() => { setPick(sel) }, [sel])

  useEffect(() => {
    const ac = new AbortController()
    const t = setTimeout(() => {
      simulate({ ...p, pick, extra_comp: ec, rent_pct: rp, own_km: own, extra_competitors: placed }, ac.signal)
        .then(r => { setRes(r); setErr('') }).catch(e => { if (e.name !== 'AbortError') setErr(String(e.message)) })
    }, 300)
    return () => { clearTimeout(t); ac.abort() }
  }, [p, pick, ec, rp, own, placed])

  const site = data.top.find(t => t.pick === pick) ?? data.top[0]
  const mc = res?.mc
  const dp = res ? res.scenario.profit - res.base.profit : 0
  return (
    <>
      <div className="panel">
        <label>Site to simulate</label>
        <select value={pick} onChange={e => setPick(Number(e.target.value))}>
          {data.top.map(t => <option key={t.pick} value={t.pick}>#{t.pick} {t.zone_name}</option>)}
        </select>
      </div>
      {err && <div className="err">{err}</div>}
      {mc && res && (
        <>
          <div className="kpis">
            <Kpi label="Chance of being profitable" value={(mc.p_profit > 0.995 ? ">99%" : `${(mc.p_profit * 100).toFixed(0)}%`)} />
            <Kpi label="Break-even within 24 mo" value={`${(mc.p_break_even * 100).toFixed(0)}%`} />
            <Kpi label="Median break-even" value={mc.be_median != null ? `${mc.be_median.toFixed(0)} months` : 'n/a'} />
            <Kpi label="24-mo worst case (5%)" value={`Rs ${mc.var5 >= 0 ? '+' : ''}${mc.var5.toFixed(0)} L`} />
          </div>
          <div className="grid-eq">
            <div className="panel">
              <h4>Monthly profit distribution (4,000 simulated futures)</h4>
              <ResponsiveContainer width="100%" height={330}>
                <BarChart data={mc.hist}><CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="x" type="number" domain={['dataMin', 'dataMax']} tickFormatter={v => Number(v).toFixed(0)} label={{ value: 'Steady-state profit (Rs L/month)', position: 'insideBottom', offset: -2 }} />
                  <YAxis /><Tooltip labelFormatter={v => `Rs ${Number(v).toFixed(1)} L`} />
                  <ReferenceLine x={0} stroke="#d23c32" strokeDasharray="4 4" />
                  <Bar isAnimationActive={false} dataKey="n" name="Simulations" fill="#1e6fd9" />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="panel">
              <h4>Cumulative cash position (incl. fit-out capex & 6-month ramp-up)</h4>
              <ResponsiveContainer width="100%" height={330}>
                <AreaChart data={mc.fan.map(f => ({ ...f, band: [f.p10, f.p90] }))}><CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="month" label={{ value: 'Month', position: 'insideBottom', offset: -2 }} /><YAxis /><Tooltip formatter={(v) => (Array.isArray(v) ? v.map(x => Number(x).toFixed(0)).join(' to ') : Number(v).toFixed(0))} />
                  <ReferenceLine y={0} stroke="#888" strokeDasharray="4 4" />
                  <Area isAnimationActive={false} dataKey="band" name="10–90% range" stroke="none" fill="#1e6fd9" fillOpacity={0.25} />
                  <Line isAnimationActive={false} dataKey="p50" name="Median" stroke="#1e6fd9" strokeWidth={3} dot={false} /><Legend />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>
          <div className="panel">
            <h4>🔮 What-if scenario lab — {site.zone_name}</h4>
            <p className="mute">Re-runs the trained XGBoost model on a modified version of the site.</p>
            <div className="grid-eq" style={{ gridTemplateColumns: 'repeat(3,1fr)' }}>
              <div><label>New competitors open nearby <b>{ec}</b></label><input type="range" min={lim.extra_comp.minimum} max={lim.extra_comp.maximum} value={ec} onChange={e => setEc(Number(e.target.value))} /></div>
              <div><label>Rent change (%) <b>{rp}</b></label><input type="range" min={lim.rent_pct.minimum} max={lim.rent_pct.maximum} step={5} value={rp} onChange={e => setRp(Number(e.target.value))} /></div>
              <div><label>We open another store (km away, 0 = none) <b>{own}</b></label><input type="range" min={lim.own_km.minimum} max={lim.own_km.maximum} step={0.5} value={own} onChange={e => setOwn(Number(e.target.value))} /></div>
            </div>
            <h4>📍 Drop competitors on the map</h4>
            <p className="mute">
              Click the map to place a competitor store. Each one within 1 km of a site (dashed ring) counts as an extra competitor there,
              on top of the slider. {placed.length > 0 && <>{placed.length} placed, {res.placed_nearby} near this site.{' '}
                <button className="btn" onClick={() => setPlaced([])}>Clear</button></>}
            </p>
            <div className="map" style={{ height: 320, marginBottom: 12, cursor: 'crosshair' }}>
              <MapContainer key={site.pick} center={[site.lat, site.lon]} zoom={13} style={{ height: '100%' }}>
                <TileLayer attribution={TILE_ATTRIBUTION} url={TILE_URL} />
                <ClickToPlace onPlace={pt => setPlaced(v => [...v, pt])} />
                {data.top.map(t => (
                  <CircleMarker key={t.pick} center={[t.lat, t.lon]} radius={t.pick === pick ? 9 : 6}
                    pathOptions={{ color: '#fff', weight: 2, fillColor: t.pick === pick ? '#e53935' : '#f5b301', fillOpacity: 1 }}>
                    <MapTip>#{t.pick} {t.zone_name}</MapTip>
                  </CircleMarker>))}
                <Circle center={[site.lat, site.lon]} radius={1000} pathOptions={{ color: '#e53935', weight: 1.5, dashArray: '5 5', fill: false }} />
                {placed.map((c, i) => (
                  <CircleMarker key={i} center={[c.lat, c.lon]} radius={6} pathOptions={{ color: '#fff', weight: 1.5, fillColor: '#7b1fa2', fillOpacity: 1 }}
                    eventHandlers={{ click: () => setPlaced(v => v.filter((_, j) => j !== i)) }}>
                    <MapTip>Simulated competitor (click to remove)</MapTip>
                  </CircleMarker>))}
              </MapContainer>
            </div>
            <div className="grid-eq">
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={[{ m: 'Sales', base: res.base.rev, sc: res.scenario.rev }, { m: 'Profit', base: res.base.profit, sc: res.scenario.profit },
                  { m: 'Profit (P10)', base: res.base.profit_p10, sc: res.scenario.profit_p10 }]}>
                  <CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="m" /><YAxis /><Tooltip formatter={(v) => `Rs ${Number(v).toFixed(1)} L`} /><Legend />
                  <ReferenceLine y={0} stroke="#888" />
                  <Bar isAnimationActive={false} dataKey="base" name="Base case" fill="#1e6fd9" /><Bar isAnimationActive={false} dataKey="sc" name="Scenario" fill="#f5a623" />
                </BarChart>
              </ResponsiveContainer>
              <div style={{ alignSelf: 'center' }}>
                <div className="kpi"><div className="l">Profit change</div><div className="v" style={{ color: dp >= 0 ? 'var(--good)' : 'var(--bad)' }}>Rs {dp >= 0 ? '+' : ''}{dp.toFixed(1)} L/mo</div></div>
                <p>{res.scenario.profit > 0 ? '✅ Still profitable.' : '❌ This scenario makes the site loss-making.'}</p>
              </div>
            </div>
            <h4>Resilience of all picks to the same scenario</h4>
            <table>
              <thead><tr><th>Rank</th><th>Location</th><th>Base profit</th><th>Scenario profit</th><th>Change</th><th>Placed competitors ≤1 km</th><th>Survives?</th></tr></thead>
              <tbody>{res.resilience.map(r => (
                <tr key={r.pick}><td>{r.pick}</td><td>{r.zone_name}</td><td>{n1(r.base)}</td><td>{n1(r.scenario)}</td><td>{n1(r.change)}</td><td>{r.placed_nearby}</td><td>{r.survives ? 'Yes' : 'No'}</td></tr>))}</tbody>
            </table>
          </div>
        </>
      )}
    </>
  )
}
