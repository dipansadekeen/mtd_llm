# mtd_model_decision.py
import os, time, joblib, torch, numpy as np, pandas as pd
import torch.nn as nn


class EntityEncoder(nn.Module):
    def __init__(self, n, d=32):
        super().__init__()
        self.network = nn.Sequential(
            nn.Linear(n, 64), nn.LayerNorm(64), nn.ReLU(), nn.Dropout(.10),
            nn.Linear(64, d), nn.ReLU()
        )
    def forward(self, x): return self.network(x)


class OperationDeepSets(nn.Module):
    def __init__(self, hn, rn, d=32):
        super().__init__()
        self.host_encoder = EntityEncoder(hn, d)
        self.route_encoder = EntityEncoder(rn, d)
        self.decision = nn.Sequential(
            nn.Linear(4*d, 64), nn.LayerNorm(64), nn.ReLU(), nn.Dropout(.20),
            nn.Linear(64, 32), nn.ReLU(), nn.Dropout(.10), nn.Linear(32, 1)
        )

    @staticmethod
    def pool(x, mask):
        b = mask.bool()
        f = b.unsqueeze(-1).float()
        mean = (x*f).sum(1) / f.sum(1).clamp(min=1)
        mx = x.masked_fill(~b.unsqueeze(-1), float("-inf")).max(1).values
        empty = ~b.any(1)
        mean[empty], mx[empty] = 0, 0
        return torch.cat([mean, mx], 1)

    def forward(self, h, hm, r, rm):
        h = self.pool(self.host_encoder(h), hm)
        r = self.pool(self.route_encoder(r), rm)
        return self.decision(torch.cat([h, r], 1)).squeeze(1)


class BinaryDNN(nn.Module):
    def __init__(self, n, hidden=(128, 64, 32), dropout=.20):
        super().__init__()
        layers = []
        for k in hidden:
            layers += [nn.Linear(n, k), nn.BatchNorm1d(k), nn.ReLU(), nn.Dropout(dropout)]
            n = k
        layers += [nn.Linear(n, 1)]
        self.network = nn.Sequential(*layers)
    def forward(self, x): return self.network(x).squeeze(1)


def matrix(rows, cols):
    d = pd.DataFrame(rows)
    missing = [c for c in cols if c not in d.columns]
    if missing:
        raise ValueError(f"Missing live model features: {missing}")
    return (
        d[cols].apply(pd.to_numeric, errors="coerce")
        .replace([np.inf, -np.inf], np.nan).fillna(0.0)
        .to_numpy(np.float32)
    )


def context(rows, cols, prefix):
    x = matrix(rows, cols) if rows else np.empty((0, len(cols)), np.float32)
    out = {f"{prefix}candidate_count": float(len(x))}
    for j, c in enumerate(cols):
        v = x[:, j] if len(x) else np.array([])
        out[f"{prefix}{c}_mean"] = float(v.mean()) if len(v) else 0.0
        out[f"{prefix}{c}_max"]  = float(v.max()) if len(v) else 0.0
        out[f"{prefix}{c}_std"]  = float(v.std(ddof=1)) if len(v) > 1 else 0.0
        out[f"{prefix}{c}_p90"]  = float(np.percentile(v, 90)) if len(v) else 0.0
    return out


class MTDModel:
    def __init__(self, model_dir="mtd_three_models"):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        load = lambda f: torch.load(
            os.path.join(model_dir, f), map_location=self.device, weights_only=False
        )

        self.oc = load("operation_deep_sets.pt")
        self.hc = load("host_candidate_dnn.pt")
        self.rc = load("route_candidate_dnn.pt")

        self.ohs = joblib.load(os.path.join(model_dir, "host_operation_scaler.joblib"))
        self.ors = joblib.load(os.path.join(model_dir, "route_operation_scaler.joblib"))
        self.hs  = joblib.load(os.path.join(model_dir, "host_candidate_scaler.joblib"))
        self.rs  = joblib.load(os.path.join(model_dir, "route_candidate_scaler.joblib"))

        self.op = OperationDeepSets(
            self.oc["host_input_dim"], self.oc["route_input_dim"], self.oc["embedding_dim"]
        ).to(self.device)
        self.op.load_state_dict(self.oc["state_dict"])
        self.op.eval()

        self.hm = BinaryDNN(
            self.hc["input_dim"], tuple(self.hc["hidden"]), self.hc["dropout"]
        ).to(self.device)
        self.hm.load_state_dict(self.hc["state_dict"])
        self.hm.eval()

        self.rm = BinaryDNN(
            self.rc["input_dim"], tuple(self.rc["hidden"]), self.rc["dropout"]
        ).to(self.device)
        self.rm.load_state_dict(self.rc["state_dict"])
        self.rm.eval()

        self.hbase = [c for c in self.hc["features"] if not c.startswith("ctx__")]
        self.rbase = [c for c in self.rc["features"] if not c.startswith("ctx__")]

    def _set(self, rows, features, scaler):
        a = scaler.transform(matrix(rows, features)) if rows else np.empty((0, len(features)), np.float32)
        n = max(1, len(a))
        x = np.zeros((1, n, len(features)), np.float32)
        m = np.zeros((1, n), np.float32)
        if len(a):
            x[0, :len(a)] = a
            m[0, :len(a)] = 1
        return (
            torch.tensor(x, dtype=torch.float32, device=self.device),
            torch.tensor(m, dtype=torch.float32, device=self.device),
        )

    def _rank(self, rows, ckpt, scaler, model, ctx, k):
        d = pd.DataFrame(rows).copy()
        for c, v in ctx.items():
            d[c] = v
        X = scaler.transform(matrix(d.to_dict("records"), ckpt["features"]))

        with torch.no_grad():
            conf = torch.sigmoid(
                model(torch.tensor(X, dtype=torch.float32, device=self.device))
            ).cpu().numpy()

        order = np.argsort(-conf)
        chosen = [i for i in order if conf[i] >= ckpt["threshold"]][:k]
        if not chosen and len(order):
            chosen = [int(order[0])]

        for i, p in enumerate(conf):
            rows[i]["candidate_confidence"] = float(p)

        return chosen

    def decide(self, hosts, routes, k_ip=None, k_route=None):
        t0 = time.perf_counter()

        hx, hm = self._set(hosts, self.oc["host_features"], self.ohs)
        rx, rm = self._set(routes, self.oc["route_features"], self.ors)

        with torch.no_grad():
            rm_conf = float(torch.sigmoid(self.op(hx, hm, rx, rm))[0])

        action = "route_mutation" if rm_conf >= self.oc["threshold"] else "ip_shuffle"

        if action == "ip_shuffle" and not hosts:
            action = "route_mutation" if routes else "no_mtd"
        elif action == "route_mutation" and not routes:
            action = "ip_shuffle" if hosts else "no_mtd"

        if action == "no_mtd":
            return action, [], [], time.perf_counter()-t0, rm_conf

        raw_ctx = {
            **context(hosts, self.hbase, "host_"),
            **context(routes, self.rbase, "route_"),
        }
        ctx = {"ctx__"+k: v for k, v in raw_ctx.items()}

        if action == "ip_shuffle":
            k = int(k_ip if k_ip is not None else self.hc["k"])
            idx = self._rank(hosts, self.hc, self.hs, self.hm, ctx, k)
            return action, [hosts[i]["host"] for i in idx], [], time.perf_counter()-t0, rm_conf

        k = int(k_route if k_route is not None else self.rc["k"])
        idx = self._rank(routes, self.rc, self.rs, self.rm, ctx, k)
        return action, [], [routes[i] for i in idx], time.perf_counter()-t0, rm_conf