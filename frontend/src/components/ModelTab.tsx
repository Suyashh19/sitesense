import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis, Line, ComposedChart } from 'recharts'
import type { Analysis, Params } from '../types'
import { Kpi } from '../ui'

export function ModelTab({ data, p }: { data: Analysis; p: Params }) {
  const { model } = data
  const a = model.assumptions
  const mx = Math.ceil(Math.max(...model.cv.map(c => Math.max(c.actual, c.pred))))
  return (
    <>
      <div className="kpis">
        <Kpi label="Cross-validated R²" value={model.metrics.cv_r2.toFixed(2)} />
        <Kpi label="Error (MAPE, held-out stores)" value={`${(model.metrics.cv_mape * 100).toFixed(0)}%`} />
        <Kpi label="Training stores" value={model.metrics.n_train} />
        <Kpi label="Rank agreement with hidden truth" value={model.spearman.toFixed(2)} />
        <Kpi label="80% band actually covers" value={`${(model.coverage_80 * 100).toFixed(0)}%`} />
      </div>
      <p className="mute">Rank agreement and band coverage can be measured only because the data is simulated, so the true revenue of vacant zones is known.</p>
      <div className="grid-eq">
        <div className="panel">
          <h4>Honest validation: each store predicted by a model that never saw it</h4>
          <ResponsiveContainer width="100%" height={360}>
            <ComposedChart margin={{ left: 0, right: 10 }}><CartesianGrid strokeDasharray="3 3" />
              <XAxis type="number" dataKey="actual" name="Actual" domain={[0, mx]} label={{ value: 'Actual sales (Rs L/mo)', position: 'insideBottom', offset: -2 }} />
              <YAxis type="number" dataKey="pred" name="Predicted" domain={[0, mx]} /><Tooltip formatter={(v) => Number(v).toFixed(1)} />
              <Scatter isAnimationActive={false} data={model.cv} fill="#1e6fd9" />
              <Line isAnimationActive={false} data={[{ actual: 0, pred: 0 }, { actual: mx, pred: mx }]} dataKey="pred" stroke="#888" strokeDasharray="5 5" dot={false} legendType="none" />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
        <div className="panel">
          <h4>What drives sales (XGBoost feature importance)</h4>
          <ResponsiveContainer width="100%" height={360}>
            <BarChart data={model.importance} layout="vertical" margin={{ left: 60 }}><CartesianGrid strokeDasharray="3 3" />
              <XAxis type="number" /><YAxis type="category" dataKey="feature" width={250} tick={{ fontSize: 11 }} /><Tooltip /><Bar isAnimationActive={false} dataKey="value" fill="#2f9e44" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
      <div className="panel">
        <h4>How the AI works</h4>
        <ol>
          <li><b>Learn:</b> XGBoost learns <i>sales = f(demand, spending power, competition, accessibility, overlap with our own stores)</i> from the owner's existing stores.</li>
          <li><b>Predict:</b> every vacant zone is scored. An 80% uncertainty band is calibrated from out-of-fold residuals and <b>widened for zones unlike anything we operate in</b> (k-NN novelty).</li>
          <li><b>Economics:</b> profit = sales × {(a.margin * 100).toFixed(0)}% margin − (rent × {a.size.toLocaleString()} sq ft + Rs {a.fixed} L fixed costs); fit-out capex Rs {a.capex} L.</li>
          <li><b>Rank:</b> multi-criteria score (profit, downside safety, coverage gap, confidence) with adjustable weights; loss-making or constraint-breaking zones are removed.</li>
          <li><b>Portfolio-aware selection:</b> picks must be ≥ {p.min_sep_km} km apart so new stores do not cannibalise each other.</li>
          <li><b>Explain:</b> marginal (Shapley-style) per-factor attributions turn predictions into evidence, e.g. "+26% sales because no competitors within 1 km".</li>
          <li><b>Cluster & simulate:</b> K-Means groups zones into labelled archetypes; Monte-Carlo (demand, rent, margin shocks, 6-month ramp-up) and a what-if lab re-run the model.</li>
        </ol>
        <h4>Data, assumptions & limitations</h4>
        <ul>
          <li><b>All data is simulated</b> ({p.city}-centred 20×20 km grid of 1 km zones; real coordinates, synthetic attributes). Real deployment would plug in census, OpenStreetMap/POI, footfall, rent listings and the chain's own sales through the same columns.</li>
          <li>The simulator's revenue process is hidden from the model; it only sees {p.n_stores} stores' outcomes. Accuracy on real data will differ.</li>
          <li>Margins, store sizes, fixed costs, capex and ramp-up are stated assumptions, set per business domain.</li>
          <li>Competition is counted, not weighted by competitor strength; online sales, seasonality and future infrastructure are not modelled.</li>
          <li>With few training stores, extrapolation to unfamiliar zones is flagged through wider uncertainty, not hidden.</li>
        </ul>
      </div>
    </>
  )
}
