import { Icon } from '../Icon'
import { useState } from 'react'
import { plan } from '../api'
import type { Params, PlanResult } from '../types'
import { Busy, ErrorBanner, Note, lakh } from '../ui'

export function Plan({ params, onPick }: { params: Params; onPick: (h3: string) => void }) {
  const [k, setK] = useState(3)
  const [total, setTotal] = useState<number | ''>('')
  const [res, setRes] = useState<PlanResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const go = async () => {
    setBusy(true); setErr('')
    try { setRes(await plan(params, k, total === '' ? null : total)) } catch (e) { setErr((e as Error).message) } finally { setBusy(false) }
  }
  const gain = res?.feasible && res.greedy_net_profit != null ? (res.net_profit ?? 0) - res.greedy_net_profit : null
  return (
    <>
      <div className="card">
        <h3><Icon name="plan" size={18} /> Plan several stores together</h3>
        <p className="hint">Choosing the best site, then the next best, can put two stores next to each other so they steal each other’s customers.
          The planner picks the <b>set</b> of stores that earns the most after that overlap, within your budget and spacing.</p>
        <div className="grid2">
          <div><label className="f">How many stores: <b>{k}</b></label><input type="range" min={2} max={6} value={k} onChange={e => setK(Number(e.target.value))} /></div>
          <div><label className="f">Total money for all of them (Rs lakh)<small> – optional</small></label>
            <input type="number" value={total} placeholder="no limit" onChange={e => setTotal(e.target.value === '' ? '' : Number(e.target.value))} /></div>
        </div>
        <div style={{ marginTop: 10 }}><button className="btn sm" style={{ width: 'auto' }} disabled={busy} onClick={go}><Icon name="run" size={14} /> Build the plan</button></div>
        <p className="hint">Uses your settings from the left (category, limits, existing stores).</p>
      </div>
      {err && <ErrorBanner msg={err} onClose={() => setErr("")} />}
      {busy && <Busy>Choosing the best combination of sites…</Busy>}
      {res && !busy && (!res.feasible ? <Note warn>{res.message}</Note> : (
        <div className="card">
          <h3>Recommended opening order</h3>
          <table className="t"><thead><tr><th>Open</th><th>Where</th><th>Profit / month</th><th>Start-up cost</th><th>Confidence</th></tr></thead><tbody>
            {res.chosen!.map(c => (
              <tr key={c.h3} style={{ cursor: 'pointer' }} onClick={() => onPick(c.h3)}>
                <td><b>#{c.step}</b></td><td>{c.name}</td><td>{lakh(c.profit_p50)}</td><td>{lakh(c.upfront, 0)}</td><td>{c.confidence}</td></tr>))}
          </tbody></table>
          <div className="grid3" style={{ marginTop: 10 }}>
            <div className="note"><b>{lakh(res.net_profit)}</b><br />net profit per month after overlap</div>
            <div className="note"><b>{lakh(res.upfront, 0)}</b><br />total start-up cost</div>
            <div className="note"><b>{lakh(res.cannibalisation_cost)}</b><br />lost to the stores overlapping</div>
          </div>
          {gain != null && <Note>{gain > 0.05 ? `Planning the stores together earns ${lakh(gain)} more per month than simply taking the individually best sites.`
            : 'Here the individually best sites already work well together, so the plan matches the simple choice.'}</Note>}
          {res.binding && res.binding.length > 0 && <Note warn>What limits the plan: {res.binding.join(' and ')}. Relaxing it could allow a better set.</Note>}
        </div>))}
    </>
  )
}
