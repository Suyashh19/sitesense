import { Icon } from '../Icon'
import { useState } from 'react'
import type { Meta, Params } from '../types'
import type { ClickMode } from './MapView'
import { ask } from '../api'
import type { AskResult } from '../types'

const STRAT_TEXT: Record<string, string> = {
  'Balanced': 'A sensible mix of market fit, profit and safety',
  'Maximise profit': 'Chase the highest expected monthly profit',
  'Play it safe': 'Prefer sites that stay profitable even in a weak case',
  'Best market fit': 'Prefer areas that look most like proven locations',
}

export function Controls(p: {
  meta: Meta; params: Params; set: (patch: Partial<Params>) => void; run: () => void; busy: boolean
  clickMode: ClickMode; setClickMode: (m: ClickMode) => void; onAsk: (r: AskResult) => void
}) {
  const { meta, params: q, set } = p
  const [text, setText] = useState('')
  const [asking, setAsking] = useState(false)
  const [askErr, setAskErr] = useState('')
  const cat = meta.categories.find(c => c.key === q.category)!
  const lim = meta.limits

  const doAsk = async () => {
    if (text.trim().length < 3) return
    setAsking(true); setAskErr('')
    try { p.onAsk(await ask(text)) } catch (e) { setAskErr((e as Error).message) } finally { setAsking(false) }
  }

  return (
    <aside className="ctl">
      <div className="step">
        <h3><Icon name="ask" size={17} /> Just ask</h3>
        <div className="ask">
          <input type="text" value={text} placeholder="e.g. best 3 pharmacy sites near Baner under 60 lakh"
            onChange={e => setText(e.target.value)} onKeyDown={e => e.key === 'Enter' && doAsk()} />
          <button className="btn" disabled={asking} onClick={doAsk}>{asking ? '…' : 'Go'}</button>
        </div>
        {askErr && <div className="err">{askErr}</div>}
        <div className="hint">Or fill in the four steps below. Either way you will see exactly what was understood.</div>
      </div>

      <div className="step">
        <h3><i>1</i> What do you sell?</h3>
        <div className="cats">
          {meta.categories.map(c => (
            <button key={c.key} className={`cat${c.key === q.category ? ' on' : ''}`} onClick={() => set({ category: c.key, overrides: {} })}>
              <span className="ic"><Icon name={c.icon} size={22} /></span><b>{c.name}</b><span>{c.blurb}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="step">
        <h3><i>2</i> Your limits <small style={{ fontWeight: 400, color: 'var(--mute)' }}>(optional)</small></h3>
        <label className="f">Total money to start the store (Rs lakh)<small> – fit-out, stock and deposit</small></label>
        <input type="number" min={lim.budget_lakh?.minimum} max={lim.budget_lakh?.maximum} placeholder="no limit" value={q.budget_lakh ?? ''}
          onChange={e => set({ budget_lakh: e.target.value === '' ? null : Number(e.target.value) })} />
        <label className="f">Highest rent you can pay (Rs per sq ft per month)</label>
        <input type="number" min={lim.max_rent_psf?.minimum} max={lim.max_rent_psf?.maximum} placeholder="no limit" value={q.max_rent_psf ?? ''}
          onChange={e => set({ max_rent_psf: e.target.value === '' ? null : Number(e.target.value) })} />
        <label className="f">Only look near</label>
        <select value={q.near ? `${q.near.lat},${q.near.lon}` : ''} onChange={e => {
          const l = meta.city.localities.find(x => `${x.lat},${x.lon}` === e.target.value)
          set({ near: l ? { lat: l.lat, lon: l.lon, radius_km: 3 } : null })
        }}>
          <option value="">Anywhere in {meta.city.name}</option>
          {meta.city.localities.map(l => <option key={l.name} value={`${l.lat},${l.lon}`}>{l.name} (within 3 km)</option>)}
        </select>
        <label className="f">Store size (sq ft)<small> – typical for {cat.name.toLowerCase()}: {cat.defaults.size_sqft}</small></label>
        <input type="number" min={lim.n_results ? 100 : undefined} placeholder={String(cat.defaults.size_sqft)} value={q.overrides.size_sqft ?? ''}
          onChange={e => set({ overrides: { ...q.overrides, size_sqft: e.target.value === '' ? undefined : Number(e.target.value) } })} />
      </div>

      <div className="step">
        <h3><i>3</i> What matters most?</h3>
        {Object.keys(meta.strategies).map(s => (
          <label key={s} className={`strat${q.strategy === s ? ' on' : ''}`}>
            <input type="radio" name="strat" hidden checked={q.strategy === s} onChange={() => set({ strategy: s })} />
            <b>{s}</b><span>{STRAT_TEXT[s] ?? ''}</span>
          </label>
        ))}
      </div>

      <div className="step">
        <h3><i>4</i> Your existing stores <small style={{ fontWeight: 400, color: 'var(--mute)' }}>(optional)</small></h3>
        <div className="hint">Add the stores you already run so SiteSense avoids stealing your own sales (cannibalisation).</div>
        <div className="chips" style={{ marginBottom: 6 }}>
          <button className={`btn sec sm`} style={{ background: p.clickMode === 'own' ? 'var(--soft)' : undefined }}
            onClick={() => p.setClickMode(p.clickMode === 'own' ? 'select' : 'own')}>
            {p.clickMode === 'own' ? <><Icon name="check" /> Click the map…</> : <><Icon name="pin" /> Add on map</>}
          </button>
          {q.own_stores.length > 0 && <button className="btn sec sm" onClick={() => set({ own_stores: [] })}>Clear ({q.own_stores.length})</button>}
        </div>
        <label className="f">Brand strength of the new store</label>
        <select value={q.brand_tier} onChange={e => set({ brand_tier: e.target.value })}>
          <option value="independent">New independent shop</option>
          <option value="regional_chain">Regional / growing chain</option>
          <option value="national_chain">Well-known national chain</option>
        </select>
        <label className="f">How many sites to show: {q.n_results}</label>
        <input type="range" min={lim.n_results?.minimum} max={lim.n_results?.maximum} value={q.n_results} onChange={e => set({ n_results: Number(e.target.value) })} />
      </div>

      <button className="btn" disabled={p.busy} onClick={p.run}>{p.busy ? 'Working…' : <><Icon name="search" /> Find best locations</>}</button>
      <div className="hint" style={{ marginTop: 8 }}>Data: OpenStreetMap, WorldPop and curated estimates. Everything marked “estimate” is an assumption, not a measurement.</div>
    </aside>
  )
}
