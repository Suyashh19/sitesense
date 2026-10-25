import { Icon } from '../Icon'
import { useState } from 'react'
import { scenario } from '../api'
import type { Params, Point, ScenarioResult } from '../types'
import type { ClickMode } from './MapView'
import { Busy, ErrorBanner, Note, lakh } from '../ui'

export function WhatIf(p: { params: Params; rivals: Point[]; setRivals: (r: Point[]) => void; clickMode: ClickMode; setClickMode: (m: ClickMode) => void }) {
  const [rent, setRent] = useState(0)
  const [res, setRes] = useState<ScenarioResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const go = async () => {
    setBusy(true); setErr('')
    try { setRes(await scenario(p.params, rent, p.rivals)) } catch (e) { setErr((e as Error).message) } finally { setBusy(false) }
  }
  return (
    <>
      <div className="card">
        <h3><Icon name="whatif" size={18} /> What if the market changes?</h3>
        <p className="hint">Change something, press the button, and see which recommendations survive. Nothing is saved — your normal results stay as they were.</p>
        <div className="grid2">
          <div>
            <label className="f">Rents rise or fall by: <b>{rent > 0 ? '+' : ''}{rent}%</b></label>
            <input type="range" min={-20} max={60} step={5} value={rent} onChange={e => setRent(Number(e.target.value))} />
          </div>
          <div>
            <label className="f">A new rival opens nearby <small>– click the map, then press the button</small></label>
            <div className="chips">
              <button className="btn sec sm" onClick={() => p.setClickMode(p.clickMode === 'rival' ? 'select' : 'rival')}>{p.clickMode === 'rival' ? <><Icon name="check" /> Click the map…</> : <><Icon name="rival" /> Drop a rival on the map</>}</button>
              {p.rivals.length > 0 && <button className="btn sec sm" onClick={() => p.setRivals([])}>Clear ({p.rivals.length})</button>}
            </div>
          </div>
        </div>
        <div style={{ marginTop: 10 }}><button className="btn sm" style={{ width: 'auto' }} disabled={busy} onClick={go}><Icon name="run" size={14} /> Run the what-if</button></div>
      </div>
      {err && <ErrorBanner msg={err} onClose={() => setErr("")} />}
      {busy && <Busy>Re-running competition, economics and ranking for the changed market…</Busy>}
      {res && !busy && (res.empty ? <Note warn>{res.message}</Note> : (
        <div className="card">
          <h3>Result</h3>
          <table className="t"><thead><tr><th>Site</th><th>Rank before → after</th><th>Profit / month before → after</th><th></th></tr></thead><tbody>
            {res.rows.map(r => (
              <tr key={r.h3}><td>{r.name}</td><td>{r.rank_before ?? 'new'} → <b>{r.rank_after}</b></td>
                <td>{r.profit_before == null ? '–' : lakh(r.profit_before)} → <b>{lakh(r.profit_after)}</b></td>
                <td><span className={`chip ${r.survives ? 'good' : 'bad'}`}>{r.survives ? 'still profitable' : 'loses money'}</span></td></tr>))}
          </tbody></table>
          {res.dropped.length > 0 && <Note warn>No longer in the top list: {res.dropped.map(d => `${d.name} (was #${d.rank_before})`).join(', ')}.</Note>}
        </div>))}
    </>
  )
}
