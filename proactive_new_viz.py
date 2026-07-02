# # mtd_visualization.py
# #
# # Interactive dashboard for the proactive MTD decision engine
# # (proactive_ilp_decision_compact.decide_ilp).
# #
# # It visualises:
# #   * Every IP (host) candidate  -> colour = score, with cost/benefit breakdown
# #   * Every route candidate       -> colour = score, cost-vs-benefit scatter
# #   * The MILP-selected action    -> selected hosts / routes highlighted
# #
# # Usage A (live, with ONOS reachable):
# #     python mtd_visualization.py
# #         -> calls decide_ilp() itself, writes mtd_dashboard.html
# #
# # Usage B (decoupled from ONOS):
# #     # inside your main script, after decide_ilp():
# #     from mtd_visualization import dump_details
# #     dump_details(action, hosts, routes, details, "mtd_run.json")
# #     # then, anywhere:
# #     python mtd_visualization.py mtd_run.json
# #
# # Usage C (offline preview):
# #     python mtd_visualization.py --demo
# #
# # Requires: plotly  ->  pip install plotly

# import os
# import sys
# import json
# import webbrowser
# import plotly
# import plotly.graph_objects as go


# # =========================
# # THEME
# # =========================

# # Score colour scale: low score (not worth defending) -> cool/blue,
# # high score (high-priority defence target) -> hot/red.
# SCORE_SCALE = "Turbo"

# SELECT_EDGE = "#FFD400"      # gold outline for MILP-selected items
# COST_COLOR = "#d9534f"       # red  (cost)
# BENEFIT_COLOR = "#5cb85c"    # green (benefit)
# GRID_BG = "#0e1117"
# PANEL_BG = "#161b22"
# TEXT_COLOR = "#e6edf3"

# COMPONENT_COLORS = {
#     "traffic_risk":  "#4e79a7",
#     "monitor_score": "#f28e2b",
#     "grid_priority": "#59a14f",
#     "ip_exposure":   "#e15759",
#     "p_host":        "#b07aa1",
#     "link_usage":    "#4e79a7",
#     "link_monitor":  "#f28e2b",
#     "route_exposure":"#e15759",
#     "p_route":       "#b07aa1",
# }


# def _base_layout(title, height=420):
#     return dict(
#         title=dict(text=title, font=dict(size=16, color=TEXT_COLOR)),
#         paper_bgcolor=PANEL_BG,
#         plot_bgcolor=GRID_BG,
#         font=dict(color=TEXT_COLOR, family="Inter, Segoe UI, sans-serif"),
#         margin=dict(l=60, r=30, t=60, b=80),
#         height=height,
#         legend=dict(bgcolor="rgba(0,0,0,0)"),
#     )


# def _axis():
#     return dict(gridcolor="#30363d", zerolinecolor="#484f58", linecolor="#484f58")


# # =========================
# # HOST (IP) FIGURES
# # =========================

# def host_costbenefit_figure(ip_candidates, selected_hosts):
#     """Diverging bar: benefit (up) vs cost (down), net score overlaid.
#     Bars coloured by score; selected hosts get a gold outline + star."""
#     if not ip_candidates:
#         return _empty("No IP candidates")

#     cands = sorted(ip_candidates, key=lambda c: c["score"], reverse=True)
#     sel = set(selected_hosts or [])

#     hosts = [c["host"] for c in cands]
#     benefit = [c["benefit"] for c in cands]
#     cost = [-c["cost"] for c in cands]          # plotted downward
#     score = [c["score"] for c in cands]

#     edge_w = [3 if h in sel else 0 for h in hosts]
#     hover = [
#         f"<b>{c['host']}</b>{' ⭐SELECTED' if c['host'] in sel else ''}<br>"
#         f"score={c['score']:.4f}<br>benefit={c['benefit']:.4f}<br>"
#         f"cost={c['cost']:.4f}<br>p_host={c['p_host']:.3f}<br>"
#         f"traffic_risk={c['traffic_risk']:.3f}<br>monitor={c['monitor_score']:.3f}<br>"
#         f"grid={c['grid_priority']:.3f}<br>ip_exposure={c['ip_exposure']:.3f}<br>"
#         f"tx_pps={c.get('tx_pps',0):.1f} rx_pps={c.get('rx_pps',0):.1f}<extra></extra>"
#         for c in cands
#     ]

#     fig = go.Figure()
#     fig.add_bar(
#         x=hosts, y=benefit, name="benefit",
#         marker=dict(color=score, colorscale=SCORE_SCALE, showscale=True,
#                     colorbar=dict(title="score"),
#                     line=dict(color=SELECT_EDGE, width=edge_w)),
#         hovertext=hover, hovertemplate="%{hovertext}",
#     )
#     fig.add_bar(
#         x=hosts, y=cost, name="cost",
#         marker=dict(color=COST_COLOR, line=dict(color=SELECT_EDGE, width=edge_w)),
#         hovertemplate="<b>%{x}</b><br>cost=%{customdata:.4f}<extra></extra>",
#         customdata=[c["cost"] for c in cands],
#     )
#     fig.add_scatter(
#         x=hosts, y=score, name="net score", mode="lines+markers",
#         line=dict(color=TEXT_COLOR, width=1.5, dash="dot"),
#         marker=dict(size=6, color=TEXT_COLOR),
#         hovertemplate="<b>%{x}</b><br>net score=%{y:.4f}<extra></extra>",
#     )

#     # star annotations for selected hosts
#     for c in cands:
#         if c["host"] in sel:
#             fig.add_annotation(x=c["host"], y=c["benefit"], text="⭐",
#                                showarrow=False, yshift=14, font=dict(size=14))

#     lay = _base_layout("Host (IP-shuffle) candidates — cost / benefit / score")
#     lay.update(barmode="relative", xaxis=dict(**_axis(), tickangle=-45),
#                yaxis=dict(**_axis(), title="benefit (+) / cost (−)"))
#     fig.update_layout(lay)
#     return fig


# def host_components_figure(ip_candidates, selected_hosts):
#     """Grouped bars of the four risk components that build p_host."""
#     if not ip_candidates:
#         return _empty("No IP candidates")

#     cands = sorted(ip_candidates, key=lambda c: c["score"], reverse=True)
#     sel = set(selected_hosts or [])
#     hosts = [c["host"] + (" ⭐" if c["host"] in sel else "") for c in cands]

#     fig = go.Figure()
#     for comp in ["traffic_risk", "monitor_score", "grid_priority", "ip_exposure"]:
#         fig.add_bar(x=hosts, y=[c[comp] for c in cands], name=comp,
#                     marker_color=COMPONENT_COLORS[comp])

#     lay = _base_layout("Host risk components (inputs to p_host & benefit)")
#     lay.update(barmode="group", xaxis=dict(**_axis(), tickangle=-45),
#                yaxis=dict(**_axis(), title="normalised value [0–1]"))
#     fig.update_layout(lay)
#     return fig


# def host_scatter_figure(ip_candidates, selected_hosts):
#     """Priority vs exposure bubble map, colour = score, size = benefit."""
#     if not ip_candidates:
#         return _empty("No IP candidates")

#     sel = set(selected_hosts or [])
#     scores = [c["score"] for c in ip_candidates]
#     benefits = [max(c["benefit"], 0) for c in ip_candidates]
#     smax = max(benefits) or 1.0
#     sizes = [12 + 38 * (b / smax) for b in benefits]
#     edge_w = [3 if c["host"] in sel else 0.5 for c in ip_candidates]

#     hover = [
#         f"<b>{c['host']}</b>{' ⭐' if c['host'] in sel else ''}<br>"
#         f"score={c['score']:.4f}<br>p_host={c['p_host']:.3f}<br>"
#         f"ip_exposure={c['ip_exposure']:.3f}<br>benefit={c['benefit']:.4f}<extra></extra>"
#         for c in ip_candidates
#     ]

#     fig = go.Figure(go.Scatter(
#         x=[c["p_host"] for c in ip_candidates],
#         y=[c["ip_exposure"] for c in ip_candidates],
#         mode="markers+text",
#         text=[c["host"] for c in ip_candidates],
#         textposition="top center", textfont=dict(size=9, color=TEXT_COLOR),
#         marker=dict(size=sizes, color=scores, colorscale=SCORE_SCALE,
#                     showscale=True, colorbar=dict(title="score"),
#                     line=dict(color=SELECT_EDGE, width=edge_w)),
#         hovertext=hover, hovertemplate="%{hovertext}",
#     ))
#     lay = _base_layout("Host map — priority (p_host) vs IP exposure  ·  size = benefit")
#     lay.update(xaxis=dict(**_axis(), title="p_host (defence priority)"),
#                yaxis=dict(**_axis(), title="ip_exposure"))
#     fig.update_layout(lay)
#     return fig


# # =========================
# # ROUTE FIGURES
# # =========================

# def route_costbenefit_figure(route_candidates, selected_routes):
#     """Cost-vs-benefit scatter for route mutations. Above the y=x line => score>0."""
#     if not route_candidates:
#         return _empty("No route candidates (no active pairs?)")

#     sel = {(r["src"], r["dst"]) for r in (selected_routes or [])}
#     labels = [f"{c['src']}→{c['dst']}" for c in route_candidates]
#     costs = [c["cost"] for c in route_candidates]
#     bens = [c["benefit"] for c in route_candidates]
#     scores = [c["score"] for c in route_candidates]
#     edge_w = [3 if (c["src"], c["dst"]) in sel else 0.5 for c in route_candidates]

#     hover = [
#         f"<b>{c['src']}→{c['dst']}</b>{' ⭐SELECTED' if (c['src'],c['dst']) in sel else ''}<br>"
#         f"current_option={c.get('current_option','?')}<br>"
#         f"score={c['score']:.4f}<br>benefit={c['benefit']:.4f}<br>cost={c['cost']:.4f}<br>"
#         f"p_route={c['p_route']:.3f}<br>link_usage={c['link_usage']:.3f}<br>"
#         f"link_monitor={c['link_monitor']:.3f}<br>route_exposure={c['route_exposure']:.3f}<br>"
#         f"path={str(c.get('path',''))[:80]}<extra></extra>"
#         for c in route_candidates
#     ]

#     fig = go.Figure(go.Scatter(
#         x=costs, y=bens, mode="markers+text", text=labels,
#         textposition="top center", textfont=dict(size=9, color=TEXT_COLOR),
#         marker=dict(size=16, color=scores, colorscale=SCORE_SCALE,
#                     showscale=True, colorbar=dict(title="score"),
#                     line=dict(color=SELECT_EDGE, width=edge_w)),
#         hovertext=hover, hovertemplate="%{hovertext}",
#     ))
#     # break-even line: benefit == cost  (score == 0)
#     lo = min(costs + bens + [0]); hi = max(costs + bens + [0.01])
#     fig.add_scatter(x=[lo, hi], y=[lo, hi], mode="lines", name="break-even (score=0)",
#                     line=dict(color="#8b949e", width=1, dash="dash"),
#                     hoverinfo="skip")

#     lay = _base_layout("Route candidates — cost vs benefit  (above dashed line ⇒ worth doing)")
#     lay.update(xaxis=dict(**_axis(), title="cost"),
#                yaxis=dict(**_axis(), title="benefit"))
#     fig.update_layout(lay)
#     return fig


# def route_components_figure(route_candidates, selected_routes):
#     """Grouped bars of the values that build each route's p_route."""
#     if not route_candidates:
#         return _empty("No route candidates")

#     cands = sorted(route_candidates, key=lambda c: c["score"], reverse=True)
#     sel = {(r["src"], r["dst"]) for r in (selected_routes or [])}
#     labels = [f"{c['src']}→{c['dst']}" + (" ⭐" if (c['src'], c['dst']) in sel else "")
#               for c in cands]

#     fig = go.Figure()
#     for comp in ["link_usage", "link_monitor", "route_exposure"]:
#         fig.add_bar(x=labels, y=[c[comp] for c in cands], name=comp,
#                     marker_color=COMPONENT_COLORS[comp])
#     fig.add_scatter(x=labels, y=[c["score"] for c in cands], name="score",
#                     mode="lines+markers", line=dict(color=TEXT_COLOR, dash="dot"),
#                     hovertemplate="%{x}<br>score=%{y:.4f}<extra></extra>")

#     lay = _base_layout("Route components (link usage / monitor / exposure) + score")
#     lay.update(barmode="group", xaxis=dict(**_axis(), tickangle=-45),
#                yaxis=dict(**_axis(), title="value"))
#     fig.update_layout(lay)
#     return fig


# # =========================
# # UTILITIES
# # =========================

# def _empty(msg):
#     fig = go.Figure()
#     fig.add_annotation(text=msg, showarrow=False,
#                        font=dict(size=16, color=TEXT_COLOR), x=0.5, y=0.5,
#                        xref="paper", yref="paper")
#     fig.update_layout(_base_layout("", height=200))
#     return fig


# def _summary_html(action, selected_hosts, selected_routes, details):
#     n_hosts = len(details.get("ip_candidates", []))
#     n_routes = len(details.get("route_candidates", []))
#     used_ip = sum(c["cost"] for c in details.get("ip_candidates", [])
#                   if c["host"] in set(selected_hosts or []))
#     sel_pairs = {(r["src"], r["dst"]) for r in (selected_routes or [])}
#     used_rt = sum(c["cost"] for c in details.get("route_candidates", [])
#                   if (c["src"], c["dst"]) in sel_pairs)
#     budget_used = used_ip + used_rt

#     badge = {"ip_shuffle": "#f28e2b", "route_mutation": "#4e79a7",
#              "no_mtd": "#8b949e"}.get(action, "#8b949e")

#     hosts_txt = ", ".join(selected_hosts) if selected_hosts else "—"
#     routes_txt = ", ".join(f"{r['src']}→{r['dst']}(opt {r.get('current_option','?')})"
#                            for r in (selected_routes or [])) or "—"
#     pairs = ", ".join(f"{a}–{b}" for a, b in details.get("active_pairs", [])) or "—"

#     def card(label, value, color=TEXT_COLOR):
#         return (f"<div style='background:{PANEL_BG};border:1px solid #30363d;"
#                 f"border-radius:10px;padding:14px 18px;min-width:150px'>"
#                 f"<div style='font-size:12px;color:#8b949e'>{label}</div>"
#                 f"<div style='font-size:20px;font-weight:600;color:{color};"
#                 f"margin-top:4px'>{value}</div></div>")

#     return f"""
#     <div style='display:flex;flex-wrap:wrap;gap:14px;margin-bottom:8px'>
#       {card("Selected action", action.upper(), badge)}
#       {card("Defence cost used", f"{budget_used:.3f}")}
#       {card("IP candidates", n_hosts)}
#       {card("Route candidates", n_routes)}
#       {card("Selected hosts", hosts_txt, "#f28e2b")}
#       {card("Selected routes", routes_txt, "#4e79a7")}
#     </div>
#     <div style='color:#8b949e;font-size:13px;margin-bottom:18px'>
#       Active host pairs: {pairs}
#     </div>"""


# def build_dashboard(action, selected_hosts, selected_routes, details,
#                     output_html="mtd_dashboard.html", auto_open=True):
#     ipc = details.get("ip_candidates", [])
#     rtc = details.get("route_candidates", [])

#     figs = [
#         host_costbenefit_figure(ipc, selected_hosts),
#         host_components_figure(ipc, selected_hosts),
#         host_scatter_figure(ipc, selected_hosts),
#         route_costbenefit_figure(rtc, selected_routes),
#         route_components_figure(rtc, selected_routes),
#     ]

#     blocks = [f.to_html(full_html=False, include_plotlyjs=("cdn" if i == 0 else False))
#               for i, f in enumerate(figs)]

#     html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
# <title>MTD Decision Dashboard</title>
# <style>
#   body{{background:{GRID_BG};color:{TEXT_COLOR};
#        font-family:Inter,'Segoe UI',sans-serif;margin:0;padding:24px}}
#   h1{{font-size:22px;margin:0 0 4px}}
#   .sub{{color:#8b949e;font-size:13px;margin-bottom:18px}}
#   .fig{{background:{PANEL_BG};border:1px solid #30363d;border-radius:12px;
#         padding:8px;margin-bottom:22px}}
#   .section{{font-size:14px;color:#8b949e;letter-spacing:1px;
#            text-transform:uppercase;margin:8px 0}}
# </style></head><body>
#   <h1>Proactive MTD — Decision Dashboard</h1>
#   <div class="sub">IP-shuffle &amp; route-mutation candidate scoring · gold outline + ⭐ = MILP selected</div>
#   {_summary_html(action, selected_hosts, selected_routes, details)}
#   <div class="section">Hosts (IP shuffle)</div>
#   <div class="fig">{blocks[0]}</div>
#   <div class="fig">{blocks[1]}</div>
#   <div class="fig">{blocks[2]}</div>
#   <div class="section">Routes (route mutation)</div>
#   <div class="fig">{blocks[3]}</div>
#   <div class="fig">{blocks[4]}</div>
# </body></html>"""

#     with open(output_html, "w", encoding="utf-8") as f:
#         f.write(html)
#     print(f"[OK] Dashboard written -> {os.path.abspath(output_html)}")

#     if auto_open:
#         try:
#             webbrowser.open("file://" + os.path.abspath(output_html))
#         except Exception:
#             pass
#     return output_html


# # =========================
# # JSON BRIDGE (decouple from ONOS)
# # =========================

# def _sanitize(obj):
#     """Make tuples JSON-safe (active_pairs, pair keys, etc.)."""
#     if isinstance(obj, dict):
#         return {k: _sanitize(v) for k, v in obj.items()}
#     if isinstance(obj, (list, tuple)):
#         return [_sanitize(v) for v in obj]
#     return obj


# def dump_details(action, selected_hosts, selected_routes, details, path="mtd_run.json"):
#     """Call this from your main script to export a run for offline visualisation."""
#     payload = {
#         "action": action,
#         "selected_hosts": list(selected_hosts or []),
#         "selected_routes": _sanitize(selected_routes or []),
#         "details": _sanitize(details or {}),
#     }
#     with open(path, "w", encoding="utf-8") as f:
#         json.dump(payload, f, indent=2)
#     print(f"[OK] Run exported -> {os.path.abspath(path)}")
#     return path


# def load_run(path):
#     with open(path, encoding="utf-8") as f:
#         p = json.load(f)
#     # restore tuple shape where the figures expect it
#     det = p["details"]
#     det["active_pairs"] = [tuple(x) for x in det.get("active_pairs", [])]
#     return p["action"], p["selected_hosts"], p["selected_routes"], det


# # =========================
# # DEMO DATA (offline preview)
# # =========================

# def _demo():
#     import random
#     random.seed(7)
#     ipc = []
#     for hid in [3, 7, 12, 18, 25, 30, 35, 39]:
#         tr, ms, gp, ex = (random.random() for _ in range(4))
#         p = 0.40 * tr + 0.35 * ms + 0.25 * gp
#         ben = p * ex * 0.70
#         cost = 0.15 * (2830 / 3000)
#         ipc.append(dict(host=f"h{hid}", score=ben - cost, benefit=ben, cost=cost,
#                         p_host=p, traffic_risk=tr, monitor_score=ms,
#                         grid_priority=gp, ip_exposure=ex,
#                         rx_pps=random.uniform(0, 150), tx_pps=random.uniform(0, 150),
#                         rx_mbps=random.random()*0.1, tx_mbps=random.random()*0.1))
#     rtc = []
#     for a, b in [("h1", "h35"), ("h2", "h30"), ("h1", "h12"), ("h7", "h25")]:
#         lu, lm, ex = random.random(), random.random(), random.random()
#         p = 0.60 * lu + 0.40 * lm
#         ben = p * ex * 0.60
#         cost = 0.05 + 0.10 * lu
#         rtc.append(dict(pair=(a, b), src=a, dst=b, current_option=random.randint(0, 3),
#                         score=ben - cost, benefit=ben, cost=cost, p_route=p,
#                         route_exposure=ex, link_usage=lu, link_monitor=lm,
#                         path=f"of:..{a}->of:..{b}"))
#     best = max(ipc, key=lambda c: c["score"])
#     details = dict(active_pairs=[("h1", "h35"), ("h2", "h30")],
#                    active_hosts=["h1", "h2", "h30", "h35"],
#                    ip_candidates=sorted(ipc, key=lambda c: c["score"], reverse=True),
#                    route_candidates=sorted(rtc, key=lambda c: c["score"], reverse=True),
#                    selected_routes=[])
#     return "ip_shuffle", [best["host"]], [], details


# # =========================
# # ENTRY POINT
# # =========================

# if __name__ == "__main__":
#     args = sys.argv[1:]

#     if "--demo" in args:
#         action, hosts, routes, details = _demo()
#     elif args and args[0].endswith(".json"):
#         action, hosts, routes, details = load_run(args[0])
#     else:
#         # live: run the decision engine directly
#         from proactive_new_scoring import decide_ilp
#         action, hosts, routes, details = decide_ilp()

#     build_dashboard(action, hosts, routes, details)


# mtd_visualization.py
#
# Interactive dashboard for the proactive MTD decision engine
# (proactive_new_scoring.decide_ilp).
#
# It visualises:
#   * Every IP (host) candidate  -> colour = score, with cost/benefit breakdown
#   * Every route candidate       -> colour = score, cost-vs-benefit scatter
#   * The MILP-selected action    -> selected hosts / routes highlighted
#
# --- Updated for the latest scoring formula -------------------------------
#   IP:    p_host = 0.35*traffic_risk + 0.30*monitor_score
#                 + 0.25*grid_priority + 0.10*flow_suspicion
#   ROUTE: p_route = 0.55*link_usage + 0.35*link_monitor
#                  + 0.10*route_grid_priority
#          score   = benefit - cost - hop_cost
#                    (hop_cost = LAMBDA_HOP * hop_penalty)
# --------------------------------------------------------------------------
#
# Usage A (live, with ONOS reachable):
#     python mtd_visualization.py
#         -> calls decide_ilp() itself, writes mtd_dashboard.html
#
# Usage B (decoupled from ONOS):
#     from mtd_visualization import dump_details
#     dump_details(action, hosts, routes, details, "mtd_run.json")
#     python mtd_visualization.py mtd_run.json
#
# Usage C (offline preview):
#     python mtd_visualization.py --demo
#
# Requires: plotly  ->  pip install plotly

import os
import sys
import json
import webbrowser
import plotly
import plotly.graph_objects as go


# =========================
# THEME
# =========================

# Score colour scale: low score (not worth defending) -> cool/blue,
# high score (high-priority defence target) -> hot/red.
SCORE_SCALE = "Turbo"

SELECT_EDGE = "#FFD400"      # gold outline for MILP-selected items
COST_COLOR = "#d9534f"       # red  (cost)
HOP_COLOR = "#c97b3a"        # amber (hop penalty / hop cost)
BENEFIT_COLOR = "#5cb85c"    # green (benefit)
GRID_BG = "#0e1117"
PANEL_BG = "#161b22"
TEXT_COLOR = "#e6edf3"

COMPONENT_COLORS = {
    # host components
    "traffic_risk":       "#4e79a7",
    "monitor_score":      "#f28e2b",
    "grid_priority":      "#59a14f",
    "ip_exposure":        "#e15759",
    "flow_suspicion":     "#76b7b2",
    "p_host":             "#b07aa1",
    # route components
    "link_usage":         "#4e79a7",
    "link_monitor":       "#f28e2b",
    "route_grid_priority":"#59a14f",
    "route_exposure":     "#e15759",
    "hop_penalty":        HOP_COLOR,
    "p_route":            "#b07aa1",
    "overlap_pressure": "#76b7b2", # new
}


def _base_layout(title, height=420):
    return dict(
        title=dict(text=title, font=dict(size=16, color=TEXT_COLOR)),
        paper_bgcolor=PANEL_BG,
        plot_bgcolor=GRID_BG,
        font=dict(color=TEXT_COLOR, family="Inter, Segoe UI, sans-serif"),
        margin=dict(l=60, r=30, t=60, b=80),
        height=height,
        legend=dict(bgcolor="rgba(0,0,0,0)"),
    )


def _axis():
    return dict(gridcolor="#30363d", zerolinecolor="#484f58", linecolor="#484f58")


# =========================
# HOST (IP) FIGURES
# =========================

def host_costbenefit_figure(ip_candidates, selected_hosts):
    """Diverging bar: benefit (up) vs cost (down), net score overlaid.
    Bars coloured by score; selected hosts get a gold outline + star."""
    if not ip_candidates:
        return _empty("No IP candidates")

    cands = sorted(ip_candidates, key=lambda c: c["score"], reverse=True)
    sel = set(selected_hosts or [])

    hosts = [c["host"] for c in cands]
    benefit = [c["benefit"] for c in cands]
    cost = [-c["cost"] for c in cands]          # plotted downward
    score = [c["score"] for c in cands]

    edge_w = [3 if h in sel else 0 for h in hosts]
    hover = [
        f"<b>{c['host']}</b>{' ⭐SELECTED' if c['host'] in sel else ''}<br>"
        f"score={c['score']:.4f}<br>benefit={c['benefit']:.4f}<br>"
        f"cost={c['cost']:.4f}<br>p_host={c['p_host']:.3f}<br>"
        f"traffic_risk={c['traffic_risk']:.3f}<br>monitor={c['monitor_score']:.3f}<br>"
        f"grid={c['grid_priority']:.3f}<br>ip_exposure={c['ip_exposure']:.3f}<br>"
        f"flow_suspicion={c.get('flow_suspicion',0):.3f}<br>"
        f"tx_pps={c.get('tx_pps',0):.1f} rx_pps={c.get('rx_pps',0):.1f}<extra></extra>"
        for c in cands
    ]

    fig = go.Figure()
    fig.add_bar(
        x=hosts, y=benefit, name="benefit",
        marker=dict(color=score, colorscale=SCORE_SCALE, showscale=True,
                    colorbar=dict(title="score"),
                    line=dict(color=SELECT_EDGE, width=edge_w)),
        hovertext=hover, hovertemplate="%{hovertext}",
    )
    fig.add_bar(
        x=hosts, y=cost, name="cost",
        marker=dict(color=COST_COLOR, line=dict(color=SELECT_EDGE, width=edge_w)),
        hovertemplate="<b>%{x}</b><br>cost=%{customdata:.4f}<extra></extra>",
        customdata=[c["cost"] for c in cands],
    )
    fig.add_scatter(
        x=hosts, y=score, name="net score", mode="lines+markers",
        line=dict(color=TEXT_COLOR, width=1.5, dash="dot"),
        marker=dict(size=6, color=TEXT_COLOR),
        hovertemplate="<b>%{x}</b><br>net score=%{y:.4f}<extra></extra>",
    )

    # star annotations for selected hosts
    for c in cands:
        if c["host"] in sel:
            fig.add_annotation(x=c["host"], y=c["benefit"], text="⭐",
                               showarrow=False, yshift=14, font=dict(size=14))

    lay = _base_layout("Host (IP-shuffle) candidates — cost / benefit / score")
    lay.update(barmode="relative", xaxis=dict(**_axis(), tickangle=-45),
               yaxis=dict(**_axis(), title="benefit (+) / cost (−)"))
    fig.update_layout(lay)
    return fig


def host_components_figure(ip_candidates, selected_hosts):
    """Grouped bars of the risk components that build p_host (+ ip_exposure)."""
    if not ip_candidates:
        return _empty("No IP candidates")

    cands = sorted(ip_candidates, key=lambda c: c["score"], reverse=True)
    sel = set(selected_hosts or [])
    hosts = [c["host"] + (" ⭐" if c["host"] in sel else "") for c in cands]

    fig = go.Figure()
    # p_host inputs: traffic_risk, monitor_score, grid_priority, flow_suspicion
    # ip_exposure shown too (multiplies benefit, not part of p_host)
    for comp in ["traffic_risk", "monitor_score", "grid_priority",
                 "flow_suspicion", "ip_exposure"]:
        fig.add_bar(x=hosts, y=[c.get(comp, 0.0) for c in cands], name=comp,
                    marker_color=COMPONENT_COLORS[comp])

    lay = _base_layout("Host risk components (inputs to p_host & benefit)")
    lay.update(barmode="group", xaxis=dict(**_axis(), tickangle=-45),
               yaxis=dict(**_axis(), title="normalised value [0–1]"))
    fig.update_layout(lay)
    return fig


def host_scatter_figure(ip_candidates, selected_hosts):
    """Priority vs exposure bubble map, colour = score, size = benefit."""
    if not ip_candidates:
        return _empty("No IP candidates")

    sel = set(selected_hosts or [])
    scores = [c["score"] for c in ip_candidates]
    benefits = [max(c["benefit"], 0) for c in ip_candidates]
    smax = max(benefits) or 1.0
    sizes = [12 + 38 * (b / smax) for b in benefits]
    edge_w = [3 if c["host"] in sel else 0.5 for c in ip_candidates]

    hover = [
        f"<b>{c['host']}</b>{' ⭐' if c['host'] in sel else ''}<br>"
        f"score={c['score']:.4f}<br>p_host={c['p_host']:.3f}<br>"
        f"ip_exposure={c['ip_exposure']:.3f}<br>"
        f"flow_suspicion={c.get('flow_suspicion',0):.3f}<br>"
        f"benefit={c['benefit']:.4f}<extra></extra>"
        for c in ip_candidates
    ]

    fig = go.Figure(go.Scatter(
        x=[c["p_host"] for c in ip_candidates],
        y=[c["ip_exposure"] for c in ip_candidates],
        mode="markers+text",
        text=[c["host"] for c in ip_candidates],
        textposition="top center", textfont=dict(size=9, color=TEXT_COLOR),
        marker=dict(size=sizes, color=scores, colorscale=SCORE_SCALE,
                    showscale=True, colorbar=dict(title="score"),
                    line=dict(color=SELECT_EDGE, width=edge_w)),
        hovertext=hover, hovertemplate="%{hovertext}",
    ))
    lay = _base_layout("Host map — priority (p_host) vs IP exposure  ·  size = benefit")
    lay.update(xaxis=dict(**_axis(), title="p_host (defence priority)"),
               yaxis=dict(**_axis(), title="ip_exposure"))
    fig.update_layout(lay)
    return fig


# =========================
# ROUTE FIGURES
# =========================

def route_costbenefit_figure(route_candidates, selected_routes):
    """Cost-vs-benefit scatter for route mutations.

    X-axis is TOTAL cost = cost + hop_cost, so the break-even line
    (benefit == total cost) again matches score = benefit - cost - hop_cost.
    Points above the dashed line ⇒ score > 0.
    """
    if not route_candidates:
        return _empty("No route candidates (no active pairs?)")

    sel = {(r["src"], r["dst"]) for r in (selected_routes or [])}
    labels = [f"{c['src']}→{c['dst']}" for c in route_candidates]
    total_cost = [c["cost"] + c.get("hop_cost", 0.0) for c in route_candidates]
    bens = [c["benefit"] for c in route_candidates]
    scores = [c["score"] for c in route_candidates]
    edge_w = [3 if (c["src"], c["dst"]) in sel else 0.5 for c in route_candidates]

    hover = [
        f"<b>{c['src']}→{c['dst']}</b>{' ⭐SELECTED' if (c['src'],c['dst']) in sel else ''}<br>"
        f"current_option={c.get('current_option','?')}<br>"
        f"score={c['score']:.4f}<br>benefit={c['benefit']:.4f}<br>"
        f"cost={c['cost']:.4f}<br>hop_cost={c.get('hop_cost',0):.4f}<br>"
        f"total_cost={c['cost']+c.get('hop_cost',0):.4f}<br>"
        f"p_route={c['p_route']:.3f}<br>link_usage={c['link_usage']:.3f}<br>"
        f"link_monitor={c['link_monitor']:.3f}<br>"
        f"max_flow_overlap={c.get('max_flow_overlap',0):.0f}<br>" #new
        f"overlap_pressure={c.get('overlap_pressure',0):.3f}<br>" #new
        f"route_grid_priority={c.get('route_grid_priority',0):.3f}<br>"
        f"route_exposure={c['route_exposure']:.3f}<br>"
        f"hop_count={c.get('current_hop_count',0):.0f} (penalty={c.get('hop_penalty',0):.3f})<br>"
        f"path={str(c.get('path',''))[:80]}<extra></extra>"
        for c in route_candidates
    ]

    fig = go.Figure(go.Scatter(
        x=total_cost, y=bens, mode="markers+text", text=labels,
        textposition="top center", textfont=dict(size=9, color=TEXT_COLOR),
        marker=dict(size=16, color=scores, colorscale=SCORE_SCALE,
                    showscale=True, colorbar=dict(title="score"),
                    line=dict(color=SELECT_EDGE, width=edge_w)),
        hovertext=hover, hovertemplate="%{hovertext}",
    ))
    # break-even line: benefit == total_cost  (score == 0)
    lo = min(total_cost + bens + [0]); hi = max(total_cost + bens + [0.01])
    fig.add_scatter(x=[lo, hi], y=[lo, hi], mode="lines", name="break-even (score=0)",
                    line=dict(color="#8b949e", width=1, dash="dash"),
                    hoverinfo="skip")

    lay = _base_layout("Route candidates — total cost (cost + hop) vs benefit  "
                       "(above dashed line ⇒ worth doing)")
    lay.update(xaxis=dict(**_axis(), title="total cost (cost + hop_cost)"),
               yaxis=dict(**_axis(), title="benefit"))
    fig.update_layout(lay)
    return fig


def route_components_figure(route_candidates, selected_routes):
    """Grouped bars of the values that build each route's p_route,
    plus route_exposure (multiplies benefit) and hop_penalty (cost side).
    Net score overlaid as a dotted line."""
    if not route_candidates:
        return _empty("No route candidates")

    cands = sorted(route_candidates, key=lambda c: c["score"], reverse=True)
    sel = {(r["src"], r["dst"]) for r in (selected_routes or [])}
    labels = [f"{c['src']}→{c['dst']}" + (" ⭐" if (c['src'], c['dst']) in sel else "")
              for c in cands]

    fig = go.Figure()
    # p_route inputs: link_usage, link_monitor, route_grid_priority
    # route_exposure multiplies benefit; hop_penalty drives hop_cost
    # for comp in ["link_usage", "link_monitor", "route_grid_priority",
    #              "route_exposure", "hop_penalty"]:

    for comp in ["link_usage", "link_monitor", "overlap_pressure", 
                "route_grid_priority", "route_exposure", "hop_penalty"]: #new
        fig.add_bar(x=labels, y=[c.get(comp, 0.0) for c in cands], name=comp,
                    marker_color=COMPONENT_COLORS[comp])
    fig.add_scatter(x=labels, y=[c["score"] for c in cands], name="score",
                    mode="lines+markers", line=dict(color=TEXT_COLOR, dash="dot"),
                    hovertemplate="%{x}<br>score=%{y:.4f}<extra></extra>")

    lay = _base_layout("Route components (usage / monitor / grid / exposure / hop) + score")
    lay.update(barmode="group", xaxis=dict(**_axis(), tickangle=-45),
               yaxis=dict(**_axis(), title="value [0–1]"))
    fig.update_layout(lay)
    return fig


# =========================
# UTILITIES
# =========================

def _empty(msg):
    fig = go.Figure()
    fig.add_annotation(text=msg, showarrow=False,
                       font=dict(size=16, color=TEXT_COLOR), x=0.5, y=0.5,
                       xref="paper", yref="paper")
    fig.update_layout(_base_layout("", height=200))
    return fig


def _summary_html(action, selected_hosts, selected_routes, details):
    n_hosts = len(details.get("ip_candidates", []))
    n_routes = len(details.get("route_candidates", []))
    used_ip = sum(c["cost"] for c in details.get("ip_candidates", [])
                  if c["host"] in set(selected_hosts or []))
    sel_pairs = {(r["src"], r["dst"]) for r in (selected_routes or [])}
    # NOTE: budget uses c["cost"] only (matches the MILP budget constraint).
    used_rt = sum(c["cost"] for c in details.get("route_candidates", [])
                  if (c["src"], c["dst"]) in sel_pairs)
    # hop_cost is an objective penalty, not budgeted — surfaced separately.
    used_hop = sum(c.get("hop_cost", 0.0) for c in details.get("route_candidates", [])
                   if (c["src"], c["dst"]) in sel_pairs)
    budget_used = used_ip + used_rt

    badge = {"ip_shuffle": "#f28e2b", "route_mutation": "#4e79a7",
             "no_mtd": "#8b949e"}.get(action, "#8b949e")

    hosts_txt = ", ".join(selected_hosts) if selected_hosts else "—"
    routes_txt = ", ".join(f"{r['src']}→{r['dst']}(opt {r.get('current_option','?')})"
                           for r in (selected_routes or [])) or "—"
    pairs = ", ".join(f"{a}–{b}" for a, b in details.get("active_pairs", [])) or "—"

    def card(label, value, color=TEXT_COLOR):
        return (f"<div style='background:{PANEL_BG};border:1px solid #30363d;"
                f"border-radius:10px;padding:14px 18px;min-width:150px'>"
                f"<div style='font-size:12px;color:#8b949e'>{label}</div>"
                f"<div style='font-size:20px;font-weight:600;color:{color};"
                f"margin-top:4px'>{value}</div></div>")

    return f"""
    <div style='display:flex;flex-wrap:wrap;gap:14px;margin-bottom:8px'>
      {card("Selected action", action.upper(), badge)}
      {card("Defence cost used", f"{budget_used:.3f}")}
      {card("Hop penalty (obj)", f"{used_hop:.3f}", HOP_COLOR)}
      {card("IP candidates", n_hosts)}
      {card("Route candidates", n_routes)}
      {card("Selected hosts", hosts_txt, "#f28e2b")}
      {card("Selected routes", routes_txt, "#4e79a7")}
    </div>
    <div style='color:#8b949e;font-size:13px;margin-bottom:18px'>
      Active host pairs: {pairs}
    </div>"""


def build_dashboard(action, selected_hosts, selected_routes, details,
                    output_html="mtd_dashboard.html", auto_open=True):
    ipc = details.get("ip_candidates", [])
    rtc = details.get("route_candidates", [])

    figs = [
        host_costbenefit_figure(ipc, selected_hosts),
        host_components_figure(ipc, selected_hosts),
        host_scatter_figure(ipc, selected_hosts),
        route_costbenefit_figure(rtc, selected_routes),
        route_components_figure(rtc, selected_routes),
    ]

    blocks = [f.to_html(full_html=False, include_plotlyjs=("cdn" if i == 0 else False))
              for i, f in enumerate(figs)]

    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>MTD Decision Dashboard</title>
<style>
  body{{background:{GRID_BG};color:{TEXT_COLOR};
       font-family:Inter,'Segoe UI',sans-serif;margin:0;padding:24px}}
  h1{{font-size:22px;margin:0 0 4px}}
  .sub{{color:#8b949e;font-size:13px;margin-bottom:18px}}
  .fig{{background:{PANEL_BG};border:1px solid #30363d;border-radius:12px;
        padding:8px;margin-bottom:22px}}
  .section{{font-size:14px;color:#8b949e;letter-spacing:1px;
           text-transform:uppercase;margin:8px 0}}
</style></head><body>
  <h1>Proactive MTD — Decision Dashboard</h1>
  <div class="sub">IP-shuffle &amp; route-mutation candidate scoring · gold outline + ⭐ = MILP selected</div>
  {_summary_html(action, selected_hosts, selected_routes, details)}
  <div class="section">Hosts (IP shuffle)</div>
  <div class="fig">{blocks[0]}</div>
  <div class="fig">{blocks[1]}</div>
  <div class="fig">{blocks[2]}</div>
  <div class="section">Routes (route mutation)</div>
  <div class="fig">{blocks[3]}</div>
  <div class="fig">{blocks[4]}</div>
</body></html>"""

    with open(output_html, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[OK] Dashboard written -> {os.path.abspath(output_html)}")

    if auto_open:
        try:
            webbrowser.open("file://" + os.path.abspath(output_html))
        except Exception:
            pass
    return output_html


# =========================
# JSON BRIDGE (decouple from ONOS)
# =========================

def _sanitize(obj):
    """Make tuples JSON-safe (active_pairs, pair keys, etc.)."""
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]
    return obj


def dump_details(action, selected_hosts, selected_routes, details, path="mtd_run.json"):
    """Call this from your main script to export a run for offline visualisation."""
    payload = {
        "action": action,
        "selected_hosts": list(selected_hosts or []),
        "selected_routes": _sanitize(selected_routes or []),
        "details": _sanitize(details or {}),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"[OK] Run exported -> {os.path.abspath(path)}")
    return path


def load_run(path):
    with open(path, encoding="utf-8") as f:
        p = json.load(f)
    # restore tuple shape where the figures expect it
    det = p["details"]
    det["active_pairs"] = [tuple(x) for x in det.get("active_pairs", [])]
    return p["action"], p["selected_hosts"], p["selected_routes"], det


# =========================
# DEMO DATA (offline preview)
# =========================

def _demo():
    import random
    random.seed(7)

    # ---- IP candidates (with flow_suspicion) ----
    ipc = []
    for hid in [3, 7, 12, 18, 25, 30, 35, 39]:
        tr, ms, gp, ex, fs = (random.random() for _ in range(5))
        p = 0.35 * tr + 0.30 * ms + 0.25 * gp + 0.10 * fs
        ben = p * ex * 0.70
        cost = 0.15 * (2830 / 3000)
        ipc.append(dict(host=f"h{hid}", score=ben - cost, benefit=ben, cost=cost,
                        p_host=p, traffic_risk=tr, monitor_score=ms,
                        grid_priority=gp, ip_exposure=ex, flow_suspicion=fs,
                        short_flow_ratio=random.random(),
                        sender_mac_diversity=random.random(),
                        rx_pps=random.uniform(0, 150), tx_pps=random.uniform(0, 150),
                        rx_mbps=random.random()*0.1, tx_mbps=random.random()*0.1))

    # ---- Route candidates (with grid + hop terms) ----
    LAMBDA_HOP = 0.03
    rtc = []
    for a, b in [("h1", "h35"), ("h2", "h30"), ("h1", "h12"), ("h7", "h25")]:
        lu, lm, ex, rgp = (random.random() for _ in range(4))
        hop_penalty = random.random()
        p = 0.55 * lu + 0.35 * lm + 0.10 * rgp
        ben = p * ex * 0.60
        cost = 0.05
        hop_cost = LAMBDA_HOP * hop_penalty
        rtc.append(dict(pair=(a, b), src=a, dst=b, current_option=random.randint(0, 3),
                        score=ben - cost - hop_cost, benefit=ben, cost=cost,
                        hop_cost=hop_cost, p_route=p, route_exposure=ex,
                        link_usage=lu, link_monitor=lm, route_grid_priority=rgp,
                        current_hop_count=random.randint(2, 8), hop_penalty=hop_penalty,
                        path=f"of:..{a}->of:..{b}"))

    best = max(ipc, key=lambda c: c["score"])
    details = dict(active_pairs=[("h1", "h35"), ("h2", "h30")],
                   active_hosts=["h1", "h2", "h30", "h35"],
                   ip_candidates=sorted(ipc, key=lambda c: c["score"], reverse=True),
                   route_candidates=sorted(rtc, key=lambda c: c["score"], reverse=True),
                   selected_routes=[])
    return "ip_shuffle", [best["host"]], [], details


# =========================
# ENTRY POINT
# =========================

if __name__ == "__main__":
    args = sys.argv[1:]

    if "--demo" in args:
        action, hosts, routes, details = _demo()
    elif args and args[0].endswith(".json"):
        action, hosts, routes, details = load_run(args[0])
    else:
        # live: run the decision engine directly
        from proactive_new_scoring import decide_ilp
        action, hosts, routes, details = decide_ilp()

    build_dashboard(action, hosts, routes, details)