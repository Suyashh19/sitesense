import { useEffect } from 'react'
import { CircleMarker, LayerGroup, LayersControl, MapContainer, Marker, Popup, Rectangle, TileLayer, Tooltip, useMap } from 'react-leaflet'
import L from 'leaflet'
import type { Analysis } from '../types'

function Fly({ to }: { to: [number, number] }) {
  const map = useMap()
  useEffect(() => { map.flyTo(to, 12, { duration: 0.6 }) }, [to[0], to[1]])  // eslint-disable-line react-hooks/exhaustive-deps
  return null
}

const pin = (k: number, sel: boolean) => {
  const s = sel ? 40 : 30
  return L.divIcon({
    className: '', iconSize: [s, s], iconAnchor: [s / 2, s / 2],
    html: '<div class="pin' + (sel ? ' sel' : '') + '" style="width:' + s + 'px;height:' + s + 'px;line-height:' + (s - 4) + 'px;font-size:' + (sel ? 19 : 15) + 'px">' + k + '</div>',
  })
}

export function MapView({ data, sel }: { data: Analysis; sel: number }) {
  const { zones, half, top } = data
  const vac = zones.filter(z => !z.has_store)
  const lim = [...vac.map(z => Math.abs(z.profit))].sort((a, b) => a - b)[Math.floor(vac.length * 0.9)] || 1
  const bounds = (z: { lat: number; lon: number }): [[number, number], [number, number]] =>
    [[z.lat - half.lat, z.lon - half.lon], [z.lat + half.lat, z.lon + half.lon]]
  const cur = top.find(t => t.pick === sel) ?? top[0]
  const center: [number, number] = [zones.reduce((a, z) => a + z.lat, 0) / zones.length, zones.reduce((a, z) => a + z.lon, 0) / zones.length]
  return (
    <div className="map">
      <MapContainer center={center} zoom={11} style={{ height: '100%' }}>
        <TileLayer attribution="&copy; OpenStreetMap contributors" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
        <Fly to={[cur.lat, cur.lon]} />
        <LayersControl position="topright" collapsed={false}>
          <LayersControl.Overlay checked name="Profit heat-map (green = profitable)">
            <LayerGroup>{vac.map(z => {
              const v = Math.max(-1, Math.min(1, z.profit / lim))
              return (
                <Rectangle key={z.zone_id} bounds={bounds(z)}
                  pathOptions={{ stroke: false, fillOpacity: 0.08 + 0.5 * Math.abs(v), fillColor: v >= 0 ? '#1e9646' : '#d23c32' }}>
                  <Tooltip sticky>{z.zone_name}<br />Est. profit Rs {z.profit.toFixed(1)} L/mo</Tooltip>
                </Rectangle>)
            })}</LayerGroup>
          </LayersControl.Overlay>
          <LayersControl.Overlay name="Competition density">
            <LayerGroup>{vac.map(z => (
              <Rectangle key={z.zone_id} bounds={bounds(z)}
                pathOptions={{ stroke: false, fillColor: '#7b1fa2', fillOpacity: Math.min(0.75, z.competitors_1km * 0.09) }}>
                <Tooltip sticky>{z.zone_name}<br />{z.competitors_1km} competitors</Tooltip>
              </Rectangle>))}</LayerGroup>
          </LayersControl.Overlay>
          <LayersControl.Overlay checked name="Our existing stores">
            <LayerGroup>{zones.filter(z => z.has_store).map(z => (
              <CircleMarker key={z.zone_id} center={[z.lat, z.lon]} radius={5}
                pathOptions={{ color: '#fff', weight: 1.5, fillColor: '#1565c0', fillOpacity: 1 }}>
                <Tooltip>Our store: {z.zone_name}</Tooltip>
              </CircleMarker>))}</LayerGroup>
          </LayersControl.Overlay>
          <LayersControl.Overlay checked name="Top-5 recommendations">
            <LayerGroup>{top.map(t => (
              <Marker key={t.pick} position={[t.lat, t.lon]} icon={pin(t.pick, t.pick === sel)} zIndexOffset={t.pick === sel ? 1000 : 500}>
                <Popup><b>#{t.pick} {t.zone_name}</b><br />Sales Rs {t.pred_revenue.toFixed(1)} L/mo<br />Profit Rs {t.profit.toFixed(1)} L/mo</Popup>
              </Marker>))}</LayerGroup>
          </LayersControl.Overlay>
        </LayersControl>
      </MapContainer>
    </div>
  )
}
