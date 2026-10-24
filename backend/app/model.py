"""AI engine: revenue prediction with uncertainty, attribution, zone clustering, portfolio-aware ranking,
Monte-Carlo simulation and what-if analysis."""
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import mean_absolute_percentage_error, r2_score, silhouette_score
from sklearn.model_selection import KFold, cross_val_predict
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler
from xgboost import XGBRegressor

from .data import DOMAINS, FACTOR_GROUPS, FEATURES, LABELS

RAMP = np.array([.55, .65, .75, .85, .92, 1.0])  # first-6-month sales ramp-up (assumption)
WEIGHT_PRESETS = {
    "Balanced": {"Profit": .40, "Downside safety": .25, "Coverage gap": .20, "Confidence": .15},
    "Maximise profit": {"Profit": .70, "Downside safety": .10, "Coverage gap": .10, "Confidence": .10},
    "Play it safe": {"Profit": .25, "Downside safety": .40, "Coverage gap": .10, "Confidence": .25},
    "Fill coverage gaps": {"Profit": .30, "Downside safety": .15, "Coverage gap": .45, "Confidence": .10},
}


class ExpansionModel:
    def __init__(self, df: pd.DataFrame, domain: str):
        self.df = df.copy()
        self.domain, self.P = domain, DOMAINS[domain]
        tr = self.df[self.df.has_store]
        X, y = tr[FEATURES], np.log(tr.monthly_revenue_lakh)
        kw = dict(n_estimators=300, max_depth=3, learning_rate=0.05, subsample=0.8, colsample_bytree=0.9, random_state=0, n_jobs=1)
        self.mean = XGBRegressor(**kw).fit(X, y)
        cv_log = cross_val_predict(XGBRegressor(**kw), X, y, cv=KFold(5, shuffle=True, random_state=1))
        self.cv_pred = np.exp(cv_log)
        # calibrated 80% band from out-of-fold residuals (conformal-style), widened for unfamiliar zones
        res = y.values - cv_log
        self.q_lo, self.q_hi = float(np.quantile(res, .10)), float(np.quantile(res, .90))
        self.scaler = StandardScaler().fit(X)
        self.knn = NearestNeighbors(n_neighbors=6).fit(self.scaler.transform(X))
        loo = self.knn.kneighbors(self.scaler.transform(X))[0][:, 1:].mean(1)  # skip self
        self.novelty_ref = float(np.median(loo))
        actual = np.exp(y)
        self.metrics = {"cv_r2": float(r2_score(actual, self.cv_pred)),
                        "cv_mape": float(mean_absolute_percentage_error(actual, self.cv_pred)),
                        "n_train": int(len(y))}
        self.cv_actual = actual.values
        self.importance = pd.Series(self.mean.feature_importances_, index=FEATURES).sort_values()
        self.bg = X.sample(min(40, len(X)), random_state=0)
        self._predict_all()

    # ---------------- prediction ----------------
    def _econ(self, d):
        P = self.P
        d["profit"] = d.pred_revenue * P["margin"] - d.opex_lakh
        d["profit_p10"] = d.rev_p10 * P["margin"] - d.opex_lakh
        d["profit_p90"] = d.rev_p90 * P["margin"] - d.opex_lakh
        d["roi_pct"] = 100 * d.profit * 12 / (d.opex_lakh * 12 + P["capex"])
        d["payback_months"] = np.where(d.profit > 0, P["capex"] / d.profit.clip(lower=1e-6), np.inf)

    def _predict_all(self):
        d, X = self.df, self.df[FEATURES]
        d["pred_revenue"] = np.exp(self.mean.predict(X))
        d["novelty"] = self._novelty(X)
        wid = self._width(d["novelty"].values)
        d["rev_p10"], d["rev_p90"] = d.pred_revenue * np.exp(self.q_lo * wid), d.pred_revenue * np.exp(self.q_hi * wid)
        self._econ(d)
        d["uncertainty"] = (d.rev_p90 - d.rev_p10) / d.pred_revenue
        # unserved demand: populated areas far from our existing stores
        d["coverage_gap"] = np.clip(d.own_nearest_km / 6, 0, 1) * np.clip(d.population_k / 40, 0, 1)

    def _novelty(self, X):
        """How unlike our existing stores a zone is (mean distance to 5 nearest stores / typical)."""
        return self.knn.kneighbors(self.scaler.transform(X), n_neighbors=5)[0].mean(1) / self.novelty_ref

    @staticmethod
    def _width(nov):
        return np.clip(0.8 + 0.45 * np.asarray(nov), 0.8, 2.4)

    def predict_row(self, row: pd.Series):
        """Re-predict a single (possibly modified) zone row -> revenue, p10, p90."""
        X = pd.DataFrame([row[FEATURES]])
        r = float(np.exp(self.mean.predict(X))[0])
        w = float(self._width(self._novelty(X))[0])
        return r, r * float(np.exp(self.q_lo * w)), r * float(np.exp(self.q_hi * w))

    # ---------------- explainability ----------------
    def attribute(self, rows: pd.DataFrame) -> pd.DataFrame:
        """Per-feature contribution to log-revenue vs. the average existing store (marginal / Shapley-style)."""
        base = self.mean.predict(self.bg).mean()
        out = np.zeros((len(rows), len(FEATURES)))
        for i, (_, r) in enumerate(rows[FEATURES].iterrows()):
            for j, f in enumerate(FEATURES):
                Xb = self.bg.copy()
                Xb[f] = r[f]
                out[i, j] = self.mean.predict(Xb).mean() - base
        return pd.DataFrame(out, index=rows.index, columns=FEATURES)

    # ---------------- ranking ----------------
    def rank(self, weights, max_rent=None, min_own_km=0.0, min_units=1, max_capex=None):
        d = self.df
        c = d[~d.has_store & (d.vacant_units >= min_units) & (d.own_nearest_km >= min_own_km)].copy()
        if max_rent:
            c = c[c.rent_psf <= max_rent]
        if max_capex is not None and self.P["capex"] > max_capex:
            c = c.iloc[0:0]
        c = c[c.profit > 0]  # only commercially viable sites are recommended
        if c.empty:
            return c

        def nz(s):
            return (s - s.min()) / (s.max() - s.min() + 1e-9)
        comps = {"Profit": nz(c.profit), "Downside safety": nz(c.profit_p10),
                 "Coverage gap": nz(c.coverage_gap), "Confidence": 1 - nz(c.uncertainty)}
        w = pd.Series(weights, dtype=float)
        w = w / w.sum()
        c["score"] = (100 * sum(w[k] * comps[k] for k in comps)).round(1)
        for k, v in comps.items():
            c[f"s_{k}"] = v
        c = c.sort_values("score", ascending=False)
        c["rank"] = np.arange(1, len(c) + 1)
        return c

    @staticmethod
    def top_n(ranked: pd.DataFrame, n=5, min_sep_km=2.5) -> pd.DataFrame:
        """Greedy portfolio-aware pick: recommended sites must be >= min_sep_km apart
        so the new stores do not cannibalise each other."""
        picked = []
        for idx, r in ranked.iterrows():
            if all(np.hypot(r.gx - ranked.loc[p, "gx"], r.gy - ranked.loc[p, "gy"]) >= min_sep_km for p in picked):
                picked.append(idx)
            if len(picked) == n:
                break
        out = ranked.loc[picked].copy()
        out["pick"] = np.arange(1, len(out) + 1)
        return out

    # ---------------- clustering ----------------
    def cluster(self, k=5):
        cols = ["population_k", "income_index", "avg_spend_k", "footfall_k", "transit_score", "road_access",
                "rent_psf", "competitors_1km"]
        scaler = StandardScaler()
        Z = scaler.fit_transform(self.df[cols])
        km = KMeans(k, n_init=10, random_state=0).fit(Z)
        d = self.df
        d["cluster"] = km.labels_
        z = pd.DataFrame(km.cluster_centers_, columns=cols)  # centroid z-scores
        names, used = {}, {}
        for c, r in z.iterrows():
            if r.footfall_k > .5 and r.rent_psf > .5 and r.competitors_1km > .3:
                n = "Saturated Premium Hub"
            elif r.footfall_k > .5 and r.rent_psf > .3:
                n = "Premium Commercial Hub"
            elif r.income_index > .4 and r.footfall_k < .4:
                n = "Affluent Residential Enclave"
            elif r.population_k > .2 and r.income_index < .1:
                n = "Dense Mass-Market Belt"
            elif r.rent_psf < -.3 and r.population_k < -.2:
                n = "Low-Density Periphery"
            elif r.transit_score > .2 and r.rent_psf < .2:
                n = "Connected Value Corridor"
            else:
                n = "Emerging Mixed-Use Area"
            used[n] = used.get(n, 0) + 1
            names[c] = n if used[n] == 1 else f"{n} {'I' * used[n]}"
        d["archetype"] = d.cluster.map(names)
        pca = PCA(2, random_state=0)
        xy = pca.fit_transform(Z)
        d["pc1"], d["pc2"] = xy[:, 0], xy[:, 1]
        cand = d[~d.has_store]
        fit = cand.groupby("archetype").agg(
            zones=("zone_id", "count"), avg_profit=("profit", "mean"),
            pct_viable=("profit", lambda s: 100 * (s > 0).mean()), avg_rent=("rent_psf", "mean"),
            avg_comp=("competitors_1km", "mean"), avg_income=("income_index", "mean"),
            avg_pop=("population_k", "mean"), avg_foot=("footfall_k", "mean"))
        q = fit.avg_profit.rank(pct=True)
        fit["domain_fit"] = np.select([q > .66, q > .33], ["High", "Medium"], "Low")
        return {"sil": float(silhouette_score(Z, km.labels_)), "z": z.set_index(z.index.map(names)),
                "cols": cols, "pca": pca, "fit": fit.sort_values("avg_profit", ascending=False)}

    # ---------------- simulation ----------------
    def monte_carlo(self, cand: pd.Series, n=4000, months=24, seed=0, rev=None):
        rng = np.random.default_rng(seed)
        P = self.P
        r, lo, hi = rev if rev else (cand.pred_revenue, cand.rev_p10, cand.rev_p90)
        sigma = max(np.log(hi / lo) / 2.563, 1e-3)
        level = r * np.exp(rng.normal(0, sigma, n) - 0)  # persistent demand level
        opex = cand.opex_lakh * (1 + rng.normal(0, .06, n))
        margin = P["margin"] + rng.normal(0, .01, n)
        ramp = np.r_[RAMP, np.ones(months - len(RAMP))]
        monthly = level[:, None] * ramp[None] * np.exp(rng.normal(0, .06, (n, months)))
        profit = monthly * margin[:, None] - opex[:, None]
        cum = -P["capex"] + np.cumsum(profit, axis=1)
        steady = level * margin - opex
        be = np.where((cum >= 0).any(1), (cum >= 0).argmax(1) + 1, np.inf)
        return {"steady": steady, "cum": cum, "p_profit": float((steady > 0).mean()),
                "p_break_even": float((be <= months).mean()), "be_median": float(np.median(be[np.isfinite(be)])) if np.isfinite(be).any() else np.inf,
                "roi24": float(np.mean(cum[:, -1] / P["capex"]) * 100), "var5": float(np.percentile(cum[:, -1], 5))}

    def what_if(self, cand: pd.Series, extra_comp=0, rent_pct=0, new_own_store_km=None):
        row = cand.copy()
        row["competitors_1km"] = row.competitors_1km + extra_comp
        if new_own_store_km is not None:
            row["own_nearest_km"] = min(row.own_nearest_km, new_own_store_km)
        row["opex_lakh"] = (row.rent_psf * (1 + rent_pct / 100) * self.P["size"] / 1e5 + self.P["fixed"])
        r, lo, hi = self.predict_row(row)
        return {"rev": r, "lo": lo, "hi": hi, "profit": r * self.P["margin"] - row.opex_lakh,
                "profit_p10": lo * self.P["margin"] - row.opex_lakh, "opex": row.opex_lakh}

    def sanity_check(self):
        """Only possible because the data is simulated: compare predictions to hidden truth on vacant zones."""
        c = self.df[~self.df.has_store]
        return float(spearmanr(c.pred_revenue, c._true_rev)[0])


# ---------------- evidence-based explanations ----------------
def fmt(f, v):
    if f in ("competitors_1km", "own_stores_3km"):
        return f"{int(v)}"
    if f in ("own_nearest_km", "dist_center_km"):
        return f"{v:.1f} km"
    if f == "rent_psf":
        return f"Rs {v:.0f}/sq ft"
    if f in ("income_index", "transit_score", "road_access"):
        return f"{v:.2f}"
    return f"{v:.1f}"


def pct_impact(v):
    return (np.exp(v) - 1) * 100


def percentile(series, v):
    return float((series < v).mean() * 100)


def factor_cards(model: ExpansionModel, cand: pd.Series, contrib: pd.Series):
    """One card per business factor: value, city percentile, revenue impact, verdict, plain-English evidence."""
    d = model.df
    cards = []
    for name, feats in FACTOR_GROUPS.items():
        imp = pct_impact(contrib[feats].sum())
        verdict = "good" if imp > 4 else "bad" if imp < -4 else "neutral"
        ev = []
        for f in feats:
            p = percentile(d[f], cand[f])
            ev.append(f"{LABELS[f]}: **{fmt(f, cand[f])}** (higher than {p:.0f}% of city zones)")
        cards.append(dict(name=name, impact=imp, verdict=verdict, evidence=ev))
    # rent is a cost factor (not in the revenue model)
    rp = percentile(d.rent_psf, cand.rent_psf)
    med = d.loc[~d.has_store, "opex_lakh"].median()
    saving = (med - cand.opex_lakh)
    verdict = "good" if rp < 40 else "bad" if rp > 70 else "neutral"
    cards.append(dict(name="Rent & running cost", impact=None, verdict=verdict, evidence=[
        f"Rent: **Rs {cand.rent_psf:.0f}/sq ft/month** (cheaper than {100 - rp:.0f}% of zones)",
        f"Monthly running cost **Rs {cand.opex_lakh:.1f} L** vs. city median Rs {med:.1f} L "
        f"({'saves' if saving >= 0 else 'costs'} Rs {abs(saving):.1f} L/month)"]))
    u = int(cand.vacant_units)
    cards.append(dict(name="Space availability", impact=None, verdict="good" if u >= 3 else "neutral" if u >= 1 else "bad",
                      evidence=[f"**{u} vacant commercial unit(s)** currently listed in this zone"
                                + (" - good choice of premises and negotiating power" if u >= 3 else " - limited choice, act quickly")]))
    return cards


def summary(model, cand, contrib, other=None, other_contrib=None):
    P = model.P
    head = (f"Predicted sales **Rs {cand.pred_revenue:.1f} L/month** (80% range {cand.rev_p10:.1f}-{cand.rev_p90:.1f}), "
            f"profit **Rs {cand.profit:.1f} L/month**, payback **{cand.payback_months:.0f} months**, "
            f"ROI **{cand.roi_pct:.0f}%/yr**. Zone type: *{cand.archetype}*.")
    rank_pos = [(f, v) for f, v in contrib.sort_values(ascending=False).items() if v > .03][:3]
    rank_neg = [(f, v) for f, v in contrib.sort_values().items() if v < -.03][:3]
    why = [f"**{LABELS[f]}** = {fmt(f, cand[f])} -> {pct_impact(v):+.0f}% sales vs. an average store of ours" for f, v in rank_pos]
    risks = [f"**{LABELS[f]}** = {fmt(f, cand[f])} -> {pct_impact(v):+.0f}% sales vs. an average store of ours" for f, v in rank_neg]
    if cand.uncertainty > 0.8:
        risks.append(f"Wide forecast range: P10 sales Rs {cand.rev_p10:.1f} L vs P90 Rs {cand.rev_p90:.1f} L")
    if cand.profit_p10 < 0:
        risks.append(f"In the pessimistic (P10) case the store loses Rs {-cand.profit_p10:.1f} L/month")
    if cand.rent_psf > model.df.rent_psf.quantile(.75):
        risks.append(f"High rent (Rs {cand.rent_psf:.0f}/sq ft) in the top quartile of the city")
    cmp = []
    if other is not None:
        diff = (contrib - other_contrib).sort_values()
        b, w = diff.index[-1], diff.index[0]
        cmp.append(f"Versus **{other.zone_name}**: profit {cand.profit - other.profit:+.1f} L/month. "
                   f"Edge: {LABELS[b]} ({fmt(b, cand[b])} vs {fmt(b, other[b])}). "
                   f"Weakness: {LABELS[w]} ({fmt(w, cand[w])} vs {fmt(w, other[w])}).")
    return head, why, risks, cmp
