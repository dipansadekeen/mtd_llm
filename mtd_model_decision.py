# # mtd_model_decision.py
# import os, time, joblib, torch, numpy as np, pandas as pd
# import torch.nn as nn


# class EntityEncoder(nn.Module):
#     def __init__(self, n, d=32):
#         super().__init__()
#         self.network = nn.Sequential(
#             nn.Linear(n, 64), nn.LayerNorm(64), nn.ReLU(), nn.Dropout(.10),
#             nn.Linear(64, d), nn.ReLU()
#         )
#     def forward(self, x): return self.network(x)


# class OperationDeepSets(nn.Module):
#     def __init__(self, hn, rn, d=32):
#         super().__init__()
#         self.host_encoder = EntityEncoder(hn, d)
#         self.route_encoder = EntityEncoder(rn, d)
#         self.decision = nn.Sequential(
#             nn.Linear(4*d, 64), nn.LayerNorm(64), nn.ReLU(), nn.Dropout(.20),
#             nn.Linear(64, 32), nn.ReLU(), nn.Dropout(.10), nn.Linear(32, 1)
#         )

#     @staticmethod
#     def pool(x, mask):
#         b = mask.bool()
#         f = b.unsqueeze(-1).float()
#         mean = (x*f).sum(1) / f.sum(1).clamp(min=1)
#         mx = x.masked_fill(~b.unsqueeze(-1), float("-inf")).max(1).values
#         empty = ~b.any(1)
#         mean[empty], mx[empty] = 0, 0
#         return torch.cat([mean, mx], 1)

#     def forward(self, h, hm, r, rm):
#         h = self.pool(self.host_encoder(h), hm)
#         r = self.pool(self.route_encoder(r), rm)
#         return self.decision(torch.cat([h, r], 1)).squeeze(1)


# class BinaryDNN(nn.Module):
#     def __init__(self, n, hidden=(128, 64, 32), dropout=.20):
#         super().__init__()
#         layers = []
#         for k in hidden:
#             layers += [nn.Linear(n, k), nn.BatchNorm1d(k), nn.ReLU(), nn.Dropout(dropout)]
#             n = k
#         layers += [nn.Linear(n, 1)]
#         self.network = nn.Sequential(*layers)
#     def forward(self, x): return self.network(x).squeeze(1)


# def matrix(rows, cols):
#     d = pd.DataFrame(rows)
#     missing = [c for c in cols if c not in d.columns]
#     if missing:
#         raise ValueError(f"Missing live model features: {missing}")
#     return (
#         d[cols].apply(pd.to_numeric, errors="coerce")
#         .replace([np.inf, -np.inf], np.nan).fillna(0.0)
#         .to_numpy(np.float32)
#     )


# def context(rows, cols, prefix):
#     x = matrix(rows, cols) if rows else np.empty((0, len(cols)), np.float32)
#     out = {f"{prefix}candidate_count": float(len(x))}
#     for j, c in enumerate(cols):
#         v = x[:, j] if len(x) else np.array([])
#         out[f"{prefix}{c}_mean"] = float(v.mean()) if len(v) else 0.0
#         out[f"{prefix}{c}_max"]  = float(v.max()) if len(v) else 0.0
#         out[f"{prefix}{c}_std"]  = float(v.std(ddof=1)) if len(v) > 1 else 0.0
#         out[f"{prefix}{c}_p90"]  = float(np.percentile(v, 90)) if len(v) else 0.0
#     return out


# class MTDModel:
#     def __init__(self, model_dir="mtd_three_models"):
#         self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
#         load = lambda f: torch.load(
#             os.path.join(model_dir, f), map_location=self.device, weights_only=False
#         )

#         self.oc = load("operation_deep_sets.pt")
#         self.hc = load("host_candidate_dnn.pt")
#         self.rc = load("route_candidate_dnn.pt")

#         self.ohs = joblib.load(os.path.join(model_dir, "host_operation_scaler.joblib"))
#         self.ors = joblib.load(os.path.join(model_dir, "route_operation_scaler.joblib"))
#         self.hs  = joblib.load(os.path.join(model_dir, "host_candidate_scaler.joblib"))
#         self.rs  = joblib.load(os.path.join(model_dir, "route_candidate_scaler.joblib"))

#         self.op = OperationDeepSets(
#             self.oc["host_input_dim"], self.oc["route_input_dim"], self.oc["embedding_dim"]
#         ).to(self.device)
#         self.op.load_state_dict(self.oc["state_dict"])
#         self.op.eval()

#         self.hm = BinaryDNN(
#             self.hc["input_dim"], tuple(self.hc["hidden"]), self.hc["dropout"]
#         ).to(self.device)
#         self.hm.load_state_dict(self.hc["state_dict"])
#         self.hm.eval()

#         self.rm = BinaryDNN(
#             self.rc["input_dim"], tuple(self.rc["hidden"]), self.rc["dropout"]
#         ).to(self.device)
#         self.rm.load_state_dict(self.rc["state_dict"])
#         self.rm.eval()

#         self.hbase = [c for c in self.hc["features"] if not c.startswith("ctx__")]
#         self.rbase = [c for c in self.rc["features"] if not c.startswith("ctx__")]

#     def _set(self, rows, features, scaler):
#         a = scaler.transform(matrix(rows, features)) if rows else np.empty((0, len(features)), np.float32)
#         n = max(1, len(a))
#         x = np.zeros((1, n, len(features)), np.float32)
#         m = np.zeros((1, n), np.float32)
#         if len(a):
#             x[0, :len(a)] = a
#             m[0, :len(a)] = 1
#         return (
#             torch.tensor(x, dtype=torch.float32, device=self.device),
#             torch.tensor(m, dtype=torch.float32, device=self.device),
#         )

#     def _rank(self, rows, ckpt, scaler, model, ctx, k):
#         d = pd.DataFrame(rows).copy()
#         for c, v in ctx.items():
#             d[c] = v
#         X = scaler.transform(matrix(d.to_dict("records"), ckpt["features"]))

#         with torch.no_grad():
#             conf = torch.sigmoid(
#                 model(torch.tensor(X, dtype=torch.float32, device=self.device))
#             ).cpu().numpy()

#         order = np.argsort(-conf)
#         chosen = [i for i in order if conf[i] >= ckpt["threshold"]][:k]
#         if not chosen and len(order):
#             chosen = [int(order[0])]

#         for i, p in enumerate(conf):
#             rows[i]["candidate_confidence"] = float(p)

#         return chosen

#     def decide(self, hosts, routes, k_ip=None, k_route=None):
#         t0 = time.perf_counter()

#         hx, hm = self._set(hosts, self.oc["host_features"], self.ohs)
#         rx, rm = self._set(routes, self.oc["route_features"], self.ors)

#         with torch.no_grad():
#             rm_conf = float(torch.sigmoid(self.op(hx, hm, rx, rm))[0])

#         action = "route_mutation" if rm_conf >= self.oc["threshold"] else "ip_shuffle"

#         if action == "ip_shuffle" and not hosts:
#             action = "route_mutation" if routes else "no_mtd"
#         elif action == "route_mutation" and not routes:
#             action = "ip_shuffle" if hosts else "no_mtd"

#         if action == "no_mtd":
#             return action, [], [], time.perf_counter()-t0, rm_conf

#         raw_ctx = {
#             **context(hosts, self.hbase, "host_"),
#             **context(routes, self.rbase, "route_"),
#         }
#         ctx = {"ctx__"+k: v for k, v in raw_ctx.items()}

#         if action == "ip_shuffle":
#             k = int(k_ip if k_ip is not None else self.hc["k"])
#             idx = self._rank(hosts, self.hc, self.hs, self.hm, ctx, k)
#             return action, [hosts[i]["host"] for i in idx], [], time.perf_counter()-t0, rm_conf

#         k = int(k_route if k_route is not None else self.rc["k"])
#         idx = self._rank(routes, self.rc, self.rs, self.rm, ctx, k)
#         return action, [], [routes[i] for i in idx], time.perf_counter()-t0, rm_conf



# ///////////////////////// new edition ////////////////////////
"""Verified execution loader for the uploaded MTD distillation bundles.

Public interface:
    action, hosts, routes, seconds, route_probability = MTDModel(dir).decide(
        ip_candidates, route_candidates, k_ip=6, k_route=20)

Candidate students output raw scores. Scores are not sigmoided. Deployment
keeps score > 0 and ranks descending. Auxiliary logits are probabilities only
for diagnostics.
"""

from __future__ import annotations

import math
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping, Sequence, Tuple

import joblib
import numpy as np
import pandas as pd
import torch
import torch.nn as nn

ACTION_IP, ACTION_ROUTE, ACTION_NONE = "ip_shuffle", "route_mutation", "no_mtd"
HOST_BASE = ["traffic_risk", "monitor_score", "ip_exposure", "grid_priority", "flow_suspicion"]
ROUTE_BASE = ["route_exposure", "link_usage", "link_monitor", "route_grid_priority", "overlap_pressure"]
HOST_DEFAULT_COST, ROUTE_DEFAULT_COST = 0.125625, 0.05


def _load_checkpoint(path: Path) -> Dict[str, Any]:
    try:
        obj = torch.load(path, map_location="cpu", weights_only=False)
    except TypeError:
        obj = torch.load(path, map_location="cpu")
    if not isinstance(obj, Mapping):
        raise TypeError(f"{path.name}: expected a checkpoint dictionary")
    return dict(obj)


def _state_dict(checkpoint: Mapping[str, Any]) -> Mapping[str, torch.Tensor]:
    state = checkpoint.get("state_dict", checkpoint.get("model_state_dict"))
    if not isinstance(state, Mapping):
        raise KeyError("checkpoint has no state_dict")
    return {(str(k)[7:] if str(k).startswith("module.") else str(k)): v for k, v in state.items()}


def _number(value: Any) -> float:
    try:
        value = float(value)
        return value if math.isfinite(value) else 0.0
    except (TypeError, ValueError):
        return 0.0


def _feature_matrix(
    rows: Sequence[Mapping[str, Any]], base: Sequence[str],
    feature_names: Sequence[str], label: str,
) -> np.ndarray:
    """Rebuild the winner's 5 direct + 10 context + count + 4 interaction inputs."""
    if not rows:
        return np.empty((0, len(feature_names)), dtype=np.float32)
    missing_base = sorted({c for row in rows for c in base if c not in row})
    if missing_base:
        raise KeyError(f"{label} runtime candidates are missing: {', '.join(missing_base)}")
    columns = {c: np.asarray([_number(row[c]) for row in rows]) for c in base}
    context: Dict[str, float] = {"snapshot_candidate_count": float(len(rows))}
    for c in base:
        context[f"{c}__snapshot_mean"] = float(np.mean(columns[c]))
        context[f"{c}__snapshot_max"] = float(np.max(columns[c]))

    matrix, missing = [], set()
    for row in rows:
        current = []
        for feature in feature_names:
            if feature in row:
                value = _number(row[feature])
            elif feature in context:
                value = context[feature]
            elif "__x__" in feature:
                left, right = feature.split("__x__", 1)
                if left in row and right in row:
                    value = _number(row[left]) * _number(row[right])
                else:
                    missing.add(feature); value = 0.0
            else:
                missing.add(feature); value = 0.0
            current.append(value)
        matrix.append(current)
    if missing:
        raise KeyError(f"{label} cannot reconstruct: {', '.join(sorted(missing))}")
    return np.asarray(matrix, dtype=np.float32)


class HybridInteractionStudent(nn.Module):
    """Exact state-dict architecture of host/route_best_student.pt."""
    def __init__(self, input_dim: int):
        super().__init__()
        self.skip = nn.Linear(input_dim, 1)
        self.trunk = nn.Sequential(
            nn.Linear(input_dim, 128), nn.LayerNorm(128), nn.SiLU(),
            nn.Linear(128, 64), nn.LayerNorm(64), nn.SiLU(),
            nn.Linear(64, 32), nn.LayerNorm(32), nn.SiLU(),
        )
        self.residual = nn.Linear(32, 1)
        self.positive_head = nn.Linear(32, 1)
        self.selected_head = nn.Linear(32, 1)
        self.kd_head = nn.Linear(32, 1)

    def forward(self, x: torch.Tensor):
        z = self.trunk(x)
        # The exported hybrid winner uses a small learned nonlinear correction
        # around its linear teacher-mimic skip path.
        score_z = self.skip(x) + 0.05 * self.residual(z)
        return (score_z.squeeze(-1), self.positive_head(z).squeeze(-1),
                self.selected_head(z).squeeze(-1), self.kd_head(z).squeeze(-1))


class CandidatePredictor:
    def __init__(self, checkpoint_path: Path, scaler_path: Path, kind: str):
        self.kind = kind
        checkpoint = _load_checkpoint(checkpoint_path)
        if checkpoint.get("config", {}).get("model") != "hybrid":
            raise ValueError(f"{checkpoint_path.name}: expected hybrid winner")
        self.features = [str(x) for x in checkpoint.get("feature_names", [])]
        self.input_dim = int(checkpoint.get("input_dim", len(self.features)))
        if len(self.features) != self.input_dim:
            raise ValueError(f"{checkpoint_path.name}: features != input_dim")
        self.model = HybridInteractionStudent(self.input_dim)
        self.model.load_state_dict(_state_dict(checkpoint), strict=True)
        self.model.eval()
        self.scaler = joblib.load(scaler_path)
        scaler_names = [str(x) for x in getattr(self.scaler, "feature_names_in_", [])]
        if scaler_names and scaler_names != self.features:
            raise ValueError(f"{scaler_path.name}: feature order differs from checkpoint")
        self.y_mean, self.y_std = float(checkpoint["y_mean"]), float(checkpoint["y_std"])
        self.threshold = float(checkpoint.get("candidate_score_threshold", 0.0))
        self.top_k = int(checkpoint.get("top_k_for_decision", 6 if kind == "host" else 20))
        self.base = HOST_BASE if kind == "host" else ROUTE_BASE

    def predict(self, rows: Sequence[MutableMapping[str, Any]]) -> np.ndarray:
        x = _feature_matrix(rows, self.base, self.features, self.kind)
        if not len(x):
            return np.empty(0, dtype=np.float64)
        x = np.asarray(
            self.scaler.transform(pd.DataFrame(x, columns=self.features)),
            dtype=np.float32,
        )
        with torch.inference_mode():
            score_z, positive_logit, selected_logit, kd_logit = self.model(torch.from_numpy(x))
            scores = score_z.cpu().numpy().astype(np.float64) * self.y_std + self.y_mean
            positive = torch.sigmoid(positive_logit).cpu().numpy()
            selected = torch.sigmoid(selected_logit).cpu().numpy()
            kd = torch.sigmoid(kd_logit).cpu().numpy()
        for row, score, pos, sel, kd_conf in zip(rows, scores, positive, selected, kd):
            row["candidate_confidence"] = float(score)
            row["predicted_candidate_score"] = float(score)
            row["positive_head_confidence"] = float(pos)
            row["selected_head_confidence"] = float(sel)
            row["kd_head_confidence"] = float(kd_conf)
        return scores

    def select(self, rows, scores, top_k):
        ranked = [(float(s), r) for r, s in zip(rows, scores) if float(s) > self.threshold]
        ranked.sort(key=lambda item: item[0], reverse=True)
        return [row for _, row in ranked[:max(0, int(top_k))]]


class OperationSummaryDNN(nn.Module):
    """Exact state-dict architecture of operation_student_dnn.pt."""
    def __init__(self, input_dim: int):
        super().__init__()
        self.trunk = nn.Sequential(
            nn.Linear(input_dim, 32), nn.LayerNorm(32), nn.SiLU(), nn.Dropout(0.05),
            nn.Linear(32, 16), nn.LayerNorm(16), nn.SiLU(), nn.Dropout(0.05),
        )
        self.action_head, self.utility_head = nn.Linear(16, 1), nn.Linear(16, 1)

    def forward(self, x):
        z = self.trunk(x)
        return self.action_head(z).squeeze(-1), self.utility_head(z).squeeze(-1)


class OperationPredictor:
    def __init__(self, model_dir: Path):
        checkpoint = _load_checkpoint(model_dir / "operation_student_dnn.pt")
        self.features = [str(x) for x in checkpoint["features"]]
        self.input_dim = int(checkpoint["input_dim"])
        if len(self.features) != self.input_dim:
            raise ValueError("operation features != input_dim")
        self.model = OperationSummaryDNN(self.input_dim)
        self.model.load_state_dict(_state_dict(checkpoint), strict=True)
        self.model.eval()
        self.scaler = joblib.load(model_dir / "operation_summary_scaler.joblib")
        self.host_reconstructor = joblib.load(model_dir / "host_score_reconstructor.joblib")
        self.route_reconstructor = joblib.load(model_dir / "route_score_reconstructor.joblib")
        self.threshold = float(checkpoint["threshold"])
        self.utility_mean = float(checkpoint.get("utility_mean", 0.0))
        self.utility_std = float(checkpoint.get("utility_std", 1.0))
        policy = checkpoint.get("teacher_policy", {})
        self.k_ip = int(policy.get("k_ip", 6)); self.k_route = int(policy.get("k_route", 20))
        self.budget = float(policy.get("defense_budget", 0.5))

    @staticmethod
    def _reconstructor_matrix(rows, model, label):
        names = [str(x) for x in getattr(model, "feature_names_in_", [])]
        if not names:
            raise ValueError(f"{label} reconstructor has no feature_names_in_")
        result, missing = [], set()
        for row in rows:
            current = []
            for feature in names:
                if feature in row:
                    value = _number(row[feature])
                elif "__x__" in feature:
                    left, right = feature.split("__x__", 1)
                    if left in row and right in row:
                        value = _number(row[left]) * _number(row[right])
                    else:
                        missing.add(feature); value = 0.0
                else:
                    missing.add(feature); value = 0.0
                current.append(value)
            result.append(current)
        if missing:
            raise KeyError(f"{label} operation inputs missing: {', '.join(sorted(missing))}")
        return pd.DataFrame(result, columns=names)

    @staticmethod
    def _pool_summary(rows, scores, prefix, top_k, budget, default_cost):
        positive = sorted([(float(s), r) for r, s in zip(rows, scores) if float(s) > 0.0],
                          key=lambda x: x[0], reverse=True)
        top, used, utility, count = positive[:top_k], 0.0, 0.0, 0
        top_scores = [score for score, _ in top]
        for score, row in top:
            cost = _number(row.get("cost", row.get("teacher_cost", default_cost)))
            cost = cost if cost > 0 else default_cost
            if used + cost <= budget + 1e-12:
                used += cost; utility += score; count += 1
        out = {
            f"{prefix}_positive_count": float(len(positive)),
            f"{prefix}_topk_sum": float(sum(top_scores)),
            f"{prefix}_topk_mean": float(np.mean(top_scores)) if top_scores else 0.0,
            f"{prefix}_budget_utility": float(utility),
            f"{prefix}_budget_count": float(count),
        }
        for rank in range(1, top_k + 1):
            out[f"{prefix}_top{rank}_score"] = top_scores[rank-1] if rank <= len(top_scores) else 0.0
        return out

    def _summary(self, hosts, routes):
        hx = self._reconstructor_matrix(hosts, self.host_reconstructor, "host")
        rx = self._reconstructor_matrix(routes, self.route_reconstructor, "route")
        hs = np.asarray(self.host_reconstructor.predict(hx)) if len(hx) else np.empty(0)
        rs = np.asarray(self.route_reconstructor.predict(rx)) if len(rx) else np.empty(0)
        summary = self._pool_summary(hosts, hs, "host", self.k_ip, self.budget, HOST_DEFAULT_COST)
        summary.update(self._pool_summary(routes, rs, "route", self.k_route, self.budget, ROUTE_DEFAULT_COST))
        hu, ru = summary["host_budget_utility"], summary["route_budget_utility"]
        diff, total = ru - hu, abs(ru) + abs(hu)
        summary.update(utility_diff=diff, utility_abs_sum=total,
                       utility_margin_norm=diff/(total+1e-12))
        return summary

    def predict(self, hosts, routes):
        summary = self._summary(hosts, routes)
        x = np.asarray([[summary[name] for name in self.features]], dtype=np.float32)
        x = np.asarray(self.scaler.transform(x), dtype=np.float32)
        with torch.inference_mode():
            action_logit, utility_z = self.model(torch.from_numpy(x))
            probability = float(torch.sigmoid(action_logit[0]).item())
            margin = float(utility_z[0].item()*self.utility_std+self.utility_mean)
        return probability, margin, summary


class MTDModel:
    REQUIRED = ["host_best_student.pt", "route_best_student.pt",
                "host_best_scaler.joblib", "route_best_scaler.joblib",
                "operation_student_dnn.pt", "operation_summary_scaler.joblib",
                "host_score_reconstructor.joblib", "route_score_reconstructor.joblib"]

    def __init__(self, model_dir: str | Path):
        requested = Path(model_dir).expanduser().resolve()
        if not requested.is_dir():
            raise FileNotFoundError(f"MTD model directory not found: {requested}")
        self.model_dir = self._resolve_root(requested)
        self.host = CandidatePredictor(self.model_dir/"host_best_student.pt",
                                       self.model_dir/"host_best_scaler.joblib", "host")
        self.route = CandidatePredictor(self.model_dir/"route_best_student.pt",
                                        self.model_dir/"route_best_scaler.joblib", "route")
        self.operation = OperationPredictor(self.model_dir)
        print(f"[MTD MODEL] verified bundle={self.model_dir} | operation_threshold="
              f"{self.operation.threshold:.4f} | host=>0/Top-{self.host.top_k} | "
              f"route=>0/Top-{self.route.top_k}")

    @classmethod
    def _resolve_root(cls, requested):
        for directory in [requested] + sorted(p for p in requested.rglob("*") if p.is_dir()):
            if all((directory/name).is_file() for name in cls.REQUIRED):
                return directory
        missing = [name for name in cls.REQUIRED if not any(requested.rglob(name))]
        raise FileNotFoundError(f"Incomplete verified model bundle; missing: {', '.join(missing)}")

    def decide(self, ip_candidates, route_candidates, *, k_ip=6, k_route=20):
        started = time.perf_counter(); hosts = list(ip_candidates or []); routes = list(route_candidates or [])
        host_scores, route_scores = self.host.predict(hosts), self.route.predict(routes)
        selected_hosts = self.host.select(hosts, host_scores, min(int(k_ip), self.host.top_k))
        selected_routes = self.route.select(routes, route_scores, min(int(k_route), self.route.top_k))
        if not selected_hosts and not selected_routes:
            return ACTION_NONE, [], [], time.perf_counter()-started, 0.0
        route_probability, predicted_margin, _ = self.operation.predict(hosts, routes)
        action = ACTION_ROUTE if route_probability >= self.operation.threshold else ACTION_IP
        if action == ACTION_ROUTE and not selected_routes:
            action = ACTION_IP if selected_hosts else ACTION_NONE
        elif action == ACTION_IP and not selected_hosts:
            action = ACTION_ROUTE if selected_routes else ACTION_NONE
        for row in hosts + routes:
            row["operation_route_probability"] = route_probability
            row["operation_predicted_utility_margin"] = predicted_margin
        host_names = [str(row["host"]) for row in selected_hosts] if action == ACTION_IP else []
        return action, host_names, selected_routes if action == ACTION_ROUTE else [], \
               time.perf_counter()-started, route_probability


__all__ = ["MTDModel", "ACTION_IP", "ACTION_ROUTE", "ACTION_NONE"]
