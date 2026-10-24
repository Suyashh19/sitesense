import { Bar, BarChart, CartesianGrid, Legend, PolarAngleAxis, PolarGrid, PolarRadiusAxis, Radar, RadarChart, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from 'recharts'
import { CircleMarker, MapContainer, TileLayer, Tooltip as MapTip } from 'react-leaflet'
import type { Analysis, Limit } from '../types'
import { TILE_ATTRIBUTION, TILE_URL } from '../config'
import { Kpi, colorFor } from '../ui'

export function ClustersTab({ data, k, lim, setK }: { data: Analysis; k: number; lim: Limit; setK: (v: number) => void }) {
  const { zones, clusters, top } = data
  const names = clusters.fit.map(f => String(f.name))
  const col = colorFor(names)
  const topIds = new Set(top.map(t => t.zone_id))
  const center: [number, number] = [zones.reduce((a, z) => a + z.lat, 0) / zones.length, zones.reduce((a, z) => a + z.lon, 0) / zones.length]
  const radarData = clusters.radar.dims.map((d, i) => ({ dim: d, ...Object.fromEntries(clusters.radar.series.map(s => [s.name, s.values[i]])) }))
  return (
    <>
      <div className="kpis">
        <Kpi label="Cluster quality (silhouette)" value={clusters.silhouette.toFixed(2)} />
        <Kpi label="Zones clustered" value={zones.length} />
        <Kpi label="Best cluster for your domain" value={names[0]} />
      </div>
      <div className="panel">
        <label>Number of clusters: <b>{k}</b></label>
        <input type="range" min={lim.minimum} max={lim.maximum} value={k} onChange={e => setK(Number(e.target.value))} />
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginTop: 8 }}>
          {names.map(n => <span key={n} style={{ fontSize: '.85rem' }}><span style={{ color: col(n) }}>●</span> {n}</span>)}
        </div>
      </div>
      <div className="grid-eq">
        <div className="panel">
          <h4>Geographic map of zone types (gold ring = top picks)</h4>
          <div className="map" style={{ height: 440 }}>
            <MapContainer center={center} zoom={11} style={{ height: '100%' }}>
              <TileLayer attribution={TILE_ATTRIBUTION} url={TILE_URL} />
              {zones.map(z => (
                <CircleMarker key={z.zone_id} center={[z.lat, z.lon]} radius={topIds.has(z.zone_id) ? 11 : 7}
                  pathOptions={{ color: topIds.has(z.zone_id) ? '#f5b301' : '#fff', weight: topIds.has(z.zone_id) ? 4 : 1, fillColor: col(z.archetype), fillOpacity: 0.8 }}>
                  <MapTip>{z.zone_name}<br />{z.archetype}<br />Rent Rs {z.rent_psf} · {z.competitors_1km} competitors</MapTip>
                </CircleMarker>))}
            </MapContainer>
          </div>
        </div>
        <div className="panel">
          <h4>Similarity space (PCA of zone features)</h4>
          <ResponsiveContainer width="100%" height={440}>
            <ScatterChart margin={{ left: 0, right: 10, top: 10, bottom: 10 }}>
              <CartesianGrid strokeDasharray="3 3" /><XAxis type="number" dataKey="pc1" name="PC1" /><YAxis type="number" dataKey="pc2" name="PC2" /><ZAxis range={[40, 40]} />
              <Tooltip cursor={{ strokeDasharray: '3 3' }} formatter={(v) => (typeof v === 'number' ? v.toFixed(2) : v)} />
              {names.map(n => <Scatter isAnimationActive={false} key={n} name={n} data={zones.filter(z => z.archetype === n)} fill={col(n)} fillOpacity={0.7} />)}
              <Scatter isAnimationActive={false} name="Top picks" data={zones.filter(z => topIds.has(z.zone_id))} fill="#f5b301" stroke="#000" shape="star" legendType="star" />
            </ScatterChart>
          </ResponsiveContainer>
        </div>
      </div>
      <div className="panel scroll">
        <h4>What each cluster means for your business</h4>
        <table>
          <thead><tr><th>Cluster</th><th>Domain fit</th><th>Vacant zones</th><th>Avg profit (L/mo)</th><th>% viable</th><th>Avg rent</th><th>Avg competitors</th><th>Income idx</th><th>Pop (k)</th><th>Footfall (k)</th></tr></thead>
          <tbody>{clusters.fit.map(f => (
            <tr key={String(f.name)}><td><span style={{ color: col(String(f.name)) }}>●</span> {f.name}</td><td><b>{f.domain_fit}</b></td><td>{f.zones}</td>
              <td>{f.avg_profit}</td><td>{f.pct_viable}</td><td>{f.avg_rent}</td><td>{f.avg_comp}</td><td>{f.avg_income}</td><td>{f.avg_pop}</td><td>{f.avg_foot}</td></tr>))}</tbody>
        </table>
      </div>
      <div className="grid-eq">
        <div className="panel">
          <h4>Cluster identity (standardised profile)</h4>
          <ResponsiveContainer width="100%" height={400}>
            <RadarChart data={radarData}>
              <PolarGrid /><PolarAngleAxis dataKey="dim" tick={{ fontSize: 11 }} /><PolarRadiusAxis tick={{ fontSize: 10 }} />
              {names.map(n => <Radar isAnimationActive={false} key={n} name={n} dataKey={n} stroke={col(n)} fill={col(n)} fillOpacity={0.15} />)}
              <Legend /><Tooltip formatter={(v) => (typeof v === 'number' ? v.toFixed(2) : v)} />
            </RadarChart>
          </ResponsiveContainer>
        </div>
        <div className="panel">
          <h4>Average predicted profit by cluster (L/month)</h4>
          <ResponsiveContainer width="100%" height={400}>
            <BarChart data={clusters.fit.map(f => ({ name: String(f.name), profit: Number(f.avg_profit) }))} layout="vertical" margin={{ left: 30 }}>
              <CartesianGrid strokeDasharray="3 3" /><XAxis type="number" /><YAxis type="category" dataKey="name" width={170} tick={{ fontSize: 12 }} />
              <Tooltip /><Bar isAnimationActive={false} dataKey="profit" fill="#1e6fd9" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
      <p className="mute">Clusters come from unsupervised K-Means on population, income, spend, footfall, transit, road access, rent and competition. Names are assigned from each cluster's standardised profile; "Domain fit" ranks clusters by the ML-predicted profit for your business.</p>
    </>
  )
}
