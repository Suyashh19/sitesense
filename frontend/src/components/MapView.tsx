import { useEffect, useMemo } from 'react'
import { CircleMarker, MapContainer, Marker, Polygon, TileLayer, Tooltip, useMap, useMapEvents } from 'react-leaflet'
import L from 'leaflet'
import { cellToBoundary } from 'h3-js'
import type { Layer, Point, Site } from '../types'
import { TILE_ATTRIBUTION, TILE_URL } from '../config'

export type MapMode = 'fit' | 'profit' | 'competition' | 'population'
export type ClickMode = 'select' | 'own' | 'rival'

const pin = (n: number, sel: boolean) => {
  const s = sel ? 40 : 32
  return L.divIcon({ className: '', iconSize: [s, s], iconAnchor: [s / 2, s / 2],
    html: `<div class="pin${sel ? ' sel' : ''}" style="width:${s}px;height:${s}px;line-height:${s - 6}px;font-size:${sel ? 18 : 15}px">${n}</div>` })
}

function Fly({ to }: { to: [number, number] | null }) {
  const map = useMap()
  useEffect(() => { if (to) map.flyTo(to, Math.max(map.getZoom(), 13), { duration: 0.6 }) }, [to?.[0], to?.[1]])  // eslint-disable-line react-hooks/exhaustive-deps
  return null
}
function Clicks({ onClick }: { onClick: (p: Point) => void }) {
  useMapEvents({ click: e => onClick({ lat: e.latlng.lat, lon: e.latlng.lng }) })
  return null
}

const lerp = (a: number[], b: number[], t: number) => a.map((x, i) => Math.round(x + (b[i] - x) * t))
const ramp = (stops: number[][], t: number) => {
  const x = Math.max(0, Math.min(1, t)) * (stops.length - 1), i = Math.min(Math.floor(x), stops.length - 2)
  const c = lerp(stops[i], stops[i + 1], x - i)
  return `rgb(${c[0]},${c[1]},${c[2]})`
}
const TEAL = [[216, 230, 238], [127, 196, 201], [14, 124, 134], [7, 61, 74]]
const RDGN = [[201, 58, 49], [241, 217, 214], [216, 239, 224], [26, 138, 74]]

export const LEGEND: Record<MapMode, { title: string; text: string; profit?: boolean }> = {
  fit: { title: 'How good is each area for this business?', text: 'Darker = stronger match (market fit score, 0-100)' },
  profit: { title: 'Expected monthly profit of a new store', text: 'Green = profitable, red = loss (before your own stores/limits)', profit: true },
  competition: { title: 'Competing shops within 1 km', text: 'Darker = more competitors' },
  population: { title: 'People living within 1 km', text: 'Darker = more residents' },
}

export function MapView(props: {
  center: [number, number]; layer: Layer | null; mode: MapMode; sites: Site[]; selected: string | null; flyTo: [number, number] | null
  own: Point[]; rivals: Point[]; competitors: { lat: number; lon: number; name: string }[]; clickMode: ClickMode
  onPick: (h3: string) => void; onMapClick: (p: Point) => void
}) {
  const { layer, mode } = props
  const cells = useMemo(() => {
    if (!layer) return []
    const val = mode === 'fit' ? layer.fit : mode === 'profit' ? layer.profit : mode === 'competition' ? layer.competitors : layer.pop
    const arr = val.map(v => (v == null ? 0 : v))
    const sorted = [...arr].sort((a, b) => a - b)
    const q = (p: number) => sorted[Math.floor(p * (sorted.length - 1))]
    const lo = mode === 'profit' ? Math.min(q(0.05), -0.01) : q(0.02), hi = mode === 'profit' ? Math.max(q(0.95), 0.01) : q(0.98)
    return layer.h3.map((h, i) => {
      let t = (arr[i] - lo) / (hi - lo || 1)
      let col: string
      if (mode === 'profit') { const m = Math.max(Math.abs(lo), Math.abs(hi)); t = (arr[i] + m) / (2 * m); col = ramp(RDGN, t) } else col = ramp(TEAL, t)
      return { h, col, i, boundary: cellToBoundary(h) as [number, number][] }
    })
  }, [layer, mode])

  return (
    <div className="map">
      <MapContainer center={props.center} zoom={11} style={{ height: '100%' }} preferCanvas>
        <TileLayer attribution={TILE_ATTRIBUTION} url={TILE_URL} />
        <Fly to={props.flyTo} />
        <Clicks onClick={props.onMapClick} />
        {cells.map(c => (
          <Polygon key={c.h} positions={c.boundary}
            pathOptions={{ stroke: c.h === props.selected, color: '#e0a100', weight: 3, fillColor: c.col, fillOpacity: 0.55 }}
            eventHandlers={{ click: e => { if (props.clickMode === 'select') { L.DomEvent.stopPropagation(e); props.onPick(c.h) } } }}>
            {layer && <Tooltip sticky>
              {layer.arch[c.i] || 'Zone'} · market fit {layer.fit[c.i] ?? '–'}/100<br />
              {layer.competitors[c.i]} competitors within 1 km · {layer.pop[c.i].toLocaleString('en-IN')} residents within 1 km<br />
              est. profit Rs {layer.profit[c.i] ?? '–'} lakh/month
            </Tooltip>}
          </Polygon>
        ))}
        {props.competitors.map((c, i) => <CircleMarker key={i} center={[c.lat, c.lon]} radius={5} pathOptions={{ color: '#fff', weight: 1, fillColor: '#7b1fa2', fillOpacity: 1 }}><Tooltip>Competitor: {c.name}</Tooltip></CircleMarker>)}
        {props.own.map((p, i) => <CircleMarker key={'o' + i} center={[p.lat, p.lon]} radius={8} pathOptions={{ color: '#fff', weight: 2, fillColor: '#1565c0', fillOpacity: 1 }}><Tooltip>Your existing store</Tooltip></CircleMarker>)}
        {props.rivals.map((p, i) => <CircleMarker key={'r' + i} center={[p.lat, p.lon]} radius={8} pathOptions={{ color: '#fff', weight: 2, fillColor: '#c93a31', fillOpacity: 1 }}><Tooltip>New rival (what-if)</Tooltip></CircleMarker>)}
        {props.sites.map(s => <Marker key={s.h3} position={[s.lat, s.lon]} icon={pin(s.rank, s.h3 === props.selected)} zIndexOffset={s.h3 === props.selected ? 1000 : 500}
          eventHandlers={{ click: e => { L.DomEvent.stopPropagation(e); props.onPick(s.h3) } }} />)}
      </MapContainer>
      <div className="legend">
        <b>{LEGEND[mode].title}</b>
        <div className={`bar${LEGEND[mode].profit ? ' profit' : ''}`} />
        {LEGEND[mode].text}
        {props.clickMode !== 'select' && <div style={{ marginTop: 4, color: 'var(--brand)' }}><b>Click the map to {props.clickMode === 'own' ? 'add your store' : 'drop a new rival'}</b></div>}
      </div>
    </div>
  )
}
