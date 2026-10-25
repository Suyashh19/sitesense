"""Learned components: M-2 viability (PU), M-3 ranker (LambdaRank), M-6 archetypes, M-10 SHAP explanations.

Honest-evidence design (PRD section 12): there is no sales data (A-01, L-01), so labels are WEAK - a zone that already
hosts an established chain outlet of the category is a positive, everything else is *unlabelled* (not "bad"). The defining
outlets are masked out of the competitor features (leakage mask), models are validated on whole geographic blocks that were
never seen in training (spatial block cross-validation), and every score is out-of-fold so a known site is never "recalled".
"""
import warnings

import h3
import lightgbm as lgb
import numpy as np
import pandas as pd
import shap
from scipy.optimize import linear_sum_assignment
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import ndcg_score, silhouette_score
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

warnings.filterwarnings("ignore", category=UserWarning)

MODEL_FEATURES = ["pop_1km", "pop_3km", "eff_pop_1km", "workers_1km", "students_1km", "affluence", "anchors_1km", "compl_1km",
                  "compl_500", "access_idx", "transit_km", "road_idx_1km", "bus_stops_500m", "comp_nonchain_500",
                  "comp_nonchain_1km", "rent_psf", "growth", "dist_centre_km"]
FEATURE_FG = {"pop_1km": "FG1", "pop_3km": "FG1", "eff_pop_1km": "FG1", "workers_1km": "FG2", "students_1km": "FG3",
              "affluence": "FG4", "anchors_1km": "FG5", "dist_centre_km": "FG5", "compl_1km": "FG6", "compl_500": "FG6",
              "access_idx": "FG7", "transit_km": "FG7", "road_idx_1km": "FG7", "bus_stops_500m": "FG7",
              "comp_nonchain_500": "FG8", "comp_nonchain_1km": "FG8", "rent_psf": "FG9", "growth": "FG10", "viability": "FG8"}
FEATURE_LABEL = {"pop_1km": "residents within 1 km", "pop_3km": "residents within 3 km", "eff_pop_1km": "customers within 1 km",
                 "workers_1km": "office workers nearby", "students_1km": "students nearby", "affluence": "neighbourhood affluence",
                 "anchors_1km": "malls and footfall anchors", "dist_centre_km": "distance from city centre",
                 "compl_1km": "complementary businesses within 1 km", "compl_500": "complementary businesses within 500 m",
                 "access_idx": "overall accessibility", "transit_km": "distance to metro or rail", "road_idx_1km": "main-road access",
                 "bus_stops_500m": "bus stops within 500 m", "comp_nonchain_500": "independent competitors within 500 m",
                 "comp_nonchain_1km": "independent competitors within 1 km", "rent_psf": "estimated rent", "growth": "area growth trend",
                 "viability": "similarity to proven locations"}
MIN_POSITIVES = 25
BLOCK_RES = 7


def blocks(cells: list[str]) -> np.ndarray:
    parents = [h3.cell_to_parent(c, BLOCK_RES) for c in cells]
    return pd.factorize(np.array(parents))[0]


def make_labels(cf: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, str]:
    """Binary PU positives and graded 0-3 relevance. Falls back to branded outlets if national chains are too rare."""
    pos = (cf.chain_here > 0).values
    src = "national chain outlet in the zone"
    if pos.sum() < MIN_POSITIVES and "branded_here" in cf:
        pos = pos | (cf.branded_here > 0).values
        src = "branded (chain or brand-tagged) outlet in the zone"
    graded = np.zeros(len(cf), dtype=int)
    graded[(cf.comp_here > 0).values] = 1                       # any same-category outlet
    graded[(cf.chain_near > 0).values] = 2                      # chain in an adjacent zone
    graded[pos] = 3
    return pos, graded, src


def _ndcg_by_block(score, rel, grp, k=10):
    vals = []
    for g in np.unique(grp):
        m = grp == g
        if rel[m].max() > 0 and m.sum() > k:
            vals.append(ndcg_score(rel[m][None, :], score[m][None, :], k=k))
    return float(np.mean(vals)) if vals else float("nan")


def recall_at_top(score, pos, frac=0.10, mask=None):
    m = np.ones(len(score), bool) if mask is None else mask
    cut = np.quantile(score[m], 1 - frac)
    p = pos & m
    return float((score[p] >= cut).mean()) if p.any() else float("nan")


def _pu_fit_predict(Xtr, ytr, Xte, bags=8, seed=0):
    rng = np.random.default_rng(seed)
    pos_i, unl_i = np.where(ytr == 1)[0], np.where(ytr == 0)[0]
    pred = np.zeros(len(Xte))
    for b in range(bags):                                       # PU bagging: each bag sees a different slice of the unlabelled
        u = rng.choice(unl_i, size=min(len(unl_i), max(3 * len(pos_i), 200)), replace=False)
        idx = np.r_[pos_i, u]
        clf = XGBClassifier(n_estimators=120, max_depth=3, learning_rate=0.08, subsample=0.8, colsample_bytree=0.8,
                            min_child_weight=2, n_jobs=1, random_state=seed + b, verbosity=0)
        clf.fit(Xtr[idx], ytr[idx])
        pred += clf.predict_proba(Xte)[:, 1] / bags
    return pred


def viability_and_rank(X: pd.DataFrame, cf: pd.DataFrame, cells: list[str], urban: np.ndarray, boi_score: np.ndarray, log=print) -> dict:
    """Train M-2 and M-3 with spatial block cross-validation. Returns out-of-fold scores, full-fit models and honest metrics."""
    pos, graded, label_src = make_labels(cf)
    n_pos = int((pos & urban).sum())
    out = {"labels": {"source": label_src, "positives": n_pos, "zones": int(urban.sum())}}
    if n_pos < 12:
        out.update(enabled=False, reason=f"only {n_pos} labelled positive zones - too few to learn from; ranking falls back to the transparent index")
        return out
    Xv = X[MODEL_FEATURES].values.astype(float)
    grp = blocks(cells)
    ids = np.where(urban)[0]
    n_splits = min(5, len(np.unique(grp[ids])))
    folds = list(GroupKFold(n_splits=n_splits).split(ids, groups=grp[ids]))
    oof2 = np.full(len(X), np.nan)
    c_est = []
    for tr, te in folds:                                        # ---- M-2 viability (Elkan-Noto corrected PU score)
        tri, tei = ids[tr], ids[te]
        s = _pu_fit_predict(Xv[tri], pos[tri].astype(int), Xv[tei])
        held = _pu_fit_predict(Xv[tri], pos[tri].astype(int), Xv[tei][pos[tei]]) if pos[tei].any() else np.array([])
        c = float(np.mean(held)) if len(held) else 0.5
        c_est.append(c)
        oof2[tei] = np.clip(s / max(c, 1e-3), 0, 1)
    c_full = float(np.mean(c_est))
    out["m2_metrics"] = {
        "recall_top10": recall_at_top(oof2, pos, 0.10, urban), "recall_top20": recall_at_top(oof2, pos, 0.20, urban),
        "baseline_population_top10": recall_at_top(X["pop_1km"].values, pos, 0.10, urban),
        "baseline_index_top10": recall_at_top(boi_score, pos, 0.10, urban), "random_top10": 0.10,
        "validation": f"{n_splits}-fold spatial block cross-validation (whole ~5 km blocks held out)"}

    # ---- M-3 LambdaRank on graded weak labels, queries = geographic blocks, monotone: higher rent never raises score
    Xr = np.c_[Xv, np.nan_to_num(oof2, nan=0.0)]
    feats = MODEL_FEATURES + ["viability"]
    mono = [(-1 if f == "rent_psf" else 0) for f in feats]
    params = dict(n_estimators=150, learning_rate=0.06, num_leaves=15, min_child_samples=20, subsample=0.8, subsample_freq=1,
                  colsample_bytree=0.8, monotone_constraints=mono, objective="lambdarank", verbose=-1, n_jobs=1, random_state=0,
                  lambdarank_truncation_level=20)
    oof3 = np.full(len(X), np.nan)
    for tr, te in folds:
        tri, tei = ids[tr], ids[te]
        order = np.argsort(grp[tri], kind="stable")
        tri = tri[order]
        sizes = np.bincount(pd.factorize(grp[tri])[0])
        m = lgb.LGBMRanker(**params).fit(Xr[tri], graded[tri], group=sizes)
        oof3[tei] = m.predict(Xr[tei])
    m3_metrics = {"ndcg10": _ndcg_by_block(oof3[ids], graded[ids], grp[ids], 10), "ndcg10_index": _ndcg_by_block(boi_score[ids], graded[ids], grp[ids], 10),
                  "ndcg10_population": _ndcg_by_block(X["pop_1km"].values[ids], graded[ids], grp[ids], 10),
                  "recall_top10": recall_at_top(oof3, pos, 0.10, urban)}
    order = np.argsort(grp[ids], kind="stable")
    full_ids = ids[order]
    sizes = np.bincount(pd.factorize(grp[full_ids])[0])
    ranker = lgb.LGBMRanker(**params).fit(Xr[full_ids], graded[full_ids], group=sizes)
    # full-fit viability model (used only for scenario deltas, never to score the zones it trained on)
    clfs = []
    rng = np.random.default_rng(1)
    pi, ui = ids[pos[ids]], ids[~pos[ids]]
    for b in range(8):
        u = rng.choice(ui, size=min(len(ui), max(3 * len(pi), 200)), replace=False)
        clfs.append(XGBClassifier(n_estimators=120, max_depth=3, learning_rate=0.08, subsample=0.8, colsample_bytree=0.8,
                                  min_child_weight=2, n_jobs=1, random_state=b, verbosity=0).fit(Xv[np.r_[pi, u]], np.r_[np.ones(len(pi)), np.zeros(len(u))]))
    imp = pd.Series(ranker.feature_importances_, index=feats).sort_values(ascending=False)
    out.update(enabled=True, viability=oof2, rank_score=oof3, ranker=ranker, pu_models=clfs, c=c_full, feats=feats, m3_metrics=m3_metrics,
               importance=(imp / imp.sum()).round(4).to_dict(), graded=graded, positives=pos)
    return out


def explain(ranker, Xrows: np.ndarray, feats: list[str], background: np.ndarray):
    """M-10: Tree SHAP of the ranker, summed within factor groups. Returns (per-feature, per-FG) contribution arrays."""
    ex = shap.TreeExplainer(ranker, data=background, feature_perturbation="interventional")
    sv = ex.shap_values(Xrows, check_additivity=False)
    fgs = sorted(set(FEATURE_FG[f] for f in feats), key=lambda s: int(s[2:]))
    by_fg = np.stack([sv[:, [i for i, f in enumerate(feats) if FEATURE_FG[f] == g]].sum(1) for g in fgs], axis=1)
    return sv, pd.DataFrame(by_fg, columns=fgs)


# ----------------------------------------------------------------------------------------- M-6 archetypes
ARCH_COLS = ["pop_1km", "workers_1km", "students_1km", "affluence", "anchors_1km", "access_idx", "poi_total_1km", "rent_psf"]
ARCH_RULES = {   # archetype -> weights on centroid z-scores (used for a one-to-one assignment, not hard thresholds)
    "Office hub": {"workers_1km": 1.4, "rent_psf": .4, "access_idx": .4},
    "Student belt": {"students_1km": 1.6, "pop_1km": .2},
    "Dense residential": {"pop_1km": 1.3, "anchors_1km": -.4, "rent_psf": -.3},
    "Transit node": {"access_idx": 1.3, "poi_total_1km": .3},
    "High street": {"anchors_1km": 1.2, "poi_total_1km": 1.0, "rent_psf": .5},
    "Emerging periphery": {"pop_1km": -.8, "poi_total_1km": -.8, "access_idx": -.5, "rent_psf": -.4},
}


def archetypes(df: pd.DataFrame, urban: np.ndarray, k: int = 6) -> dict:
    X = df.loc[urban, ARCH_COLS].values.astype(float)
    Z = StandardScaler().fit_transform(np.log1p(np.maximum(X, 0)))
    P = PCA(n_components=min(5, Z.shape[1]), random_state=0).fit_transform(Z)
    km = KMeans(k, n_init=10, random_state=0).fit(P)
    zc = pd.DataFrame([Z[km.labels_ == c].mean(0) for c in range(k)], columns=ARCH_COLS)
    names = list(ARCH_RULES)[:k]
    score = np.array([[sum(w * zc.loc[c, col] for col, w in ARCH_RULES[nm].items()) for nm in names] for c in range(k)])
    r, c = linear_sum_assignment(-score)
    label = {int(ri): names[ci] for ri, ci in zip(r, c)}
    arch = np.full(len(df), "", dtype=object)
    arch[np.where(urban)[0]] = [label[int(i)] for i in km.labels_]
    d = np.sort(km.transform(P), axis=1)
    margin = np.full(len(df), np.nan)
    margin[np.where(urban)[0]] = d[:, 1] - d[:, 0]
    return {"archetype": arch, "margin": margin, "silhouette": float(silhouette_score(P, km.labels_, sample_size=min(3000, len(P)), random_state=0)),
            "centroids": zc.rename(index=label).round(2)}
