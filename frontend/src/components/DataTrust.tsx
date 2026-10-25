import { Icon } from '../Icon'
import { useEffect, useState } from 'react'
import { getPipeline, runPipeline } from '../api'
import type { Meta, PipelineStatus } from '../types'
import { Note } from '../ui'

const pct = (v: unknown) => (typeof v === 'number' ? `${(v * 100).toFixed(0)}%` : '–')

export function DataTrust({ meta, onBuilt }: { meta: Meta; onBuilt: () => void }) {
  const [st, setSt] = useState<PipelineStatus | null>(null)
  const refresh = () => getPipeline().then(s => { setSt(s); return s })
  useEffect(() => { refresh() }, [])
  useEffect(() => {
    if (!st?.job.running) return
    const t = setInterval(() => refresh().then(s => { if (!s.job.running) onBuilt() }), 2500)
    return () => clearInterval(t)
  }, [st?.job.running]) // eslint-disable-line react-hooks/exhaustive-deps
  const m = st?.status?.meta
  const build = async () => { await runPipeline(); refresh() }
  return (
    <>
      <div className="card">
        <h3>How SiteSense reached these answers</h3>
        <ol>
          <li><b>Collect</b> real map data (shops, offices, colleges, hospitals, bus and metro stops, roads) from OpenStreetMap and population from WorldPop.</li>
          <li><b>Divide</b> {meta.city.name} into small hexagonal zones (about 10 hectares each) and measure the surroundings of every zone.</li>
          <li><b>Score</b> each zone on ten factors, weighted differently for each business type (the “Retail DNA”).</li>
          <li><b>Learn</b> what proven locations look like by studying where established chains already trade, then rank every zone.</li>
          <li><b>Simulate</b> customers choosing between stores to estimate sales and profit as a <i>range</i>, not a single guess.</li>
          <li><b>Explain</b> every recommendation in plain language with reasons, risks and a confidence level.</li>
        </ol>
      </div>

      <div className="card">
        <h3>Data pipeline {st?.ready ? <span className="chip good">ready</span> : <span className="chip bad">not built</span>}</h3>
        {!st?.ready && <Note warn>No data has been built yet. Press the button — it downloads map data and trains the models (takes several minutes the first time).</Note>}
        <button className="btn sec sm" disabled={st?.job.running} onClick={build}>{st?.job.running ? 'Building…' : st?.ready ? <><Icon name="refresh" /> Rebuild from cached data</> : <><Icon name="build" /> Build data and models</>}</button>
        {st?.job.error && <div className="err">Build failed: {st.job.error}</div>}
        {(st?.job.running || (st?.log.length ?? 0) > 0) && <pre className="log">{st?.log.join('\n')}</pre>}
        {st?.status && <div style={{ marginTop: 8 }}>
          {st.status.stages.map((s, i) => (
            <div className="stage" key={i}><span><Icon name={s.real === false ? 'estimate' : 'done'} size={16} /></span>
              <div><b>{s.name}</b> – {s.detail}{s.source && <div className="hint">{s.real === false ? 'Estimate · ' : 'Real data · '}{s.source}</div>}</div></div>))}
          <p className="hint">Last built {st.status.finished.replace('T', ' ')} UTC in {st.status.seconds}s.</p>
        </div>}
      </div>

      {m && <div className="card">
        <h3>How well do the learned models work?</h3>
        <p className="hint">Tested on whole neighbourhoods the model never saw (spatial block cross-validation). “Recall” asks: of the zones that really host an established chain,
          how many land in the model’s top 10%? Random guessing would score 10%.</p>
        <table className="t"><thead><tr><th>Business</th><th>Chain sites used</th><th>Viability model recall</th><th>…if only population</th><th>…if only the index</th><th>Ranker NDCG@10</th><th>Competitors mapped</th></tr></thead><tbody>
          {meta.categories.map(c => {
            const x = m.categories[c.key]
            return <tr key={c.key}><td><Icon name={c.icon} /> {c.name}</td><td>{x.labels.positives}</td>
              {x.enabled ? <>
                <td><b>{pct(x.m2?.recall_top10)}</b></td><td>{pct(x.m2?.baseline_population_top10)}</td><td>{pct(x.m2?.baseline_index_top10)}</td>
                <td>{typeof x.m3?.ndcg10 === 'number' ? x.m3.ndcg10.toFixed(2) : '–'}</td></> :
                <td colSpan={4}><span className="chip warn">Too few chain sites to learn from – using the transparent index only</span></td>}
              <td>{x.competitors}</td></tr>
          })}
        </tbody></table>
        <p className="hint">Rent model: CatBoost trained on {m.rent.n_localities} locality prices; typical error {(m.rent.loo_mape * 100).toFixed(0)}% when a whole locality is hidden
          (versus {(m.rent.baseline_mape * 100).toFixed(0)}% for a simple price × yield rule). Zone types: 6 archetypes, silhouette {m.archetype_silhouette.toFixed(2)}.</p>
      </div>}

      <div className="card">
        <h3>Retail DNA – what matters for each business (version {meta.dna_version})</h3>
        <p className="hint">Expert starting weights, each column sums to 100. They are kept in a configuration file, not in code, and are shown here so you can challenge them.</p>
        <table className="t dna"><thead><tr><th>Factor</th>{meta.categories.map(c => <th key={c.key} className="n"><Icon name={c.icon} /><br />{c.name.split(' ')[0]}</th>)}</tr></thead><tbody>
          {Object.entries(meta.factor_groups).map(([k, n]) => (
            <tr key={k}><td>{n}</td>{meta.categories.map(c => <td key={c.key} className={`n${c.dna[k] >= 20 ? ' hi' : ''}`}>{c.dna[k]}</td>)}</tr>))}
        </tbody></table>
      </div>
      <p className="hint">Map data © OpenStreetMap contributors (ODbL). Population: WorldPop (CC BY 4.0). Basemap tiles: OpenStreetMap. Database: {meta.db.engine}{meta.db.postgis ? ' + PostGIS' : ''}.
        AI wording: {meta.llm_provider ?? 'plain templates (no language-model key set)'}.</p>
    </>
  )
}
