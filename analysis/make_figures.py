"""Phase 7: turn results/A, results/B and results/C into figures and tables.

    python analysis/make_figures.py

Reads   results/A/summary.csv, results/B/summary.csv + *_server.csv,
        results/C/summary.csv + *_timeline.csv + sim_replicas_metric.json
Writes  results/figures/*.png   (for the report and slides)
        results/tables/*.csv    (the numbers behind every figure)
        results/RESULTS.md      (headline numbers in one page)
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results"
FIG = RES / "figures"
TAB = RES / "tables"

# Azure Container Apps consumption list prices (USD per second, active usage).
# Express environments are billed on the same per-second model. Check the
# current East Asia rate in the Azure pricing calculator; every configuration
# uses the same rates, so the ranking between configurations does not depend on them.
USD_PER_VCPU_S = 0.000024
USD_PER_GIB_S = 0.000003

# Resources kept running in each Experiment B configuration (vCPU, GiB).
# Microservices: API gateway (0.5, 1) + N simulation replicas (0.5, 1);
# the optimizer receives no traffic in this test and scales to zero.
B_RESOURCES = {"mono_r1": (1.5, 3), "mono_r2": (3.0, 6),
               "micro_sim1": (1.0, 2), "micro_sim2": (1.5, 3), "micro_sim3": (2.0, 4)}
SIM_REPLICA = (0.5, 1.0)          # one simulation replica in Experiment C
P95_TARGET_MS = 500               # latency target used to compare costs

# Colours: categorical slots from a colour-blind-checked palette, fixed order.
BLUE, ORANGE, AQUA, YELLOW, MAGENTA = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"
ARCH = {"mono": BLUE, "micro": ORANGE}
POLICY = {"fixed3": BLUE, "http_min0": ORANGE, "http_min1": AQUA,
          "http_min2": YELLOW, "cpu_min1": MAGENTA}
INK, INK2, GRID, AXIS = "#0b0b0b", "#52514e", "#e1e0d9", "#c3c2b7"

plt.rcParams.update({
    "figure.facecolor": "#fcfcfb", "axes.facecolor": "#fcfcfb", "savefig.facecolor": "#fcfcfb",
    "font.size": 10, "axes.titlesize": 11, "axes.titleweight": "bold", "axes.labelcolor": INK2,
    "axes.edgecolor": AXIS, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
    "axes.spines.top": False, "axes.spines.right": False, "xtick.color": INK2, "ytick.color": INK2,
    "text.color": INK, "legend.frameon": False, "lines.linewidth": 2, "lines.markersize": 6,
})


def usd_per_s(vcpu, gib):
    return vcpu * USD_PER_VCPU_S + gib * USD_PER_GIB_S


def save(fig, name):
    fig.tight_layout()
    fig.savefig(FIG / name, dpi=180)
    plt.close(fig)
    print("  figure:", FIG / name)


# ----------------------------------------------------------------- Experiment A
def experiment_a():
    a = pd.read_csv(RES / "A" / "summary.csv")
    a["arch"] = a.label.str.split("_").str[0]
    a["size"] = a.label.str.split("_").str[1]
    a["p95_ms"] = pd.to_numeric(a.p95_ms, errors="coerce")
    a["failed"] = (a.error_rate.fillna(1) > 0.10) | (a.requests == 0)
    # Count only successful requests: a crashing service can return errors very fast,
    # which would otherwise look like high throughput.
    a["ok_rps"] = (a.rps * (1 - a.error_rate.fillna(1))).round(2)
    sizes = [("small", "Small problem (10 × 50)"), ("medium", "Medium (40 × 200)"),
             ("large", "Large (100 × 600)")]
    a.to_csv(TAB / "A_breakeven.csv", index=False)

    for metric, ylabel, fname, log in [("ok_rps", "Successful requests/s", "A_throughput.png", False),
                                       ("p95_ms", "p95 latency (ms, log scale)", "A_latency_p95.png", True)]:
        fig, axes = plt.subplots(1, 3, figsize=(12, 3.8))
        for ax, (size, title) in zip(axes, sizes):
            for arch, name in [("mono", "Monolith"), ("micro", "Microservices")]:
                d = a[(a["size"] == size) & (a.arch == arch)].sort_values("users")
                ok, bad = d[~d.failed], d[d.failed]
                ax.plot(d.users, d[metric], color=ARCH[arch], marker="o", label=name)
                # Runs where >10% of requests failed: hollow marker
                ax.scatter(bad.users, bad[metric], s=60, facecolor="#fcfcfb",
                           edgecolor=ARCH[arch], linewidth=2, zorder=3)
            ax.set_title(title, loc="left")
            ax.set_xlabel("Concurrent users")
            ax.set_xticks([10, 50, 100, 250])
            if log:
                ax.set_yscale("log")
        axes[0].set_ylabel(ylabel)
        axes[0].legend(loc="upper left")
        fig.suptitle("Experiment A: monolith vs microservices, equal budget (1.5 vCPU)"
                     + "   (hollow marker = more than 10% of requests failed)",
                     x=0.01, ha="left", fontsize=11, color=INK2)
        save(fig, fname)

    peak = a[~a.failed].groupby(["size", "arch"]).rps.max().unstack()
    peak["mono_over_micro"] = (peak["mono"] / peak["micro"]).round(2)
    peak.to_csv(TAB / "A_peak_throughput.csv")
    return peak


# ----------------------------------------------------------------- Experiment B
def experiment_b():
    b = pd.read_csv(RES / "B" / "summary.csv")
    b["arch"] = b.label.str.split("_").str[0]
    b["vcpu"] = b.label.map(lambda l: B_RESOURCES[l][0])
    b["gib"] = b.label.map(lambda l: B_RESOURCES[l][1])
    b["usd_per_hour"] = (usd_per_s(b.vcpu, b.gib) * 3600).round(4)
    b["usd_per_1k_requests"] = (usd_per_s(b.vcpu, b.gib) / b.rps * 1000).round(6)
    b["meets_target"] = b.p95_ms <= P95_TARGET_MS

    # Per-route latency from the server logs: light vs heavy requests
    rows = []
    for _, r in b.iterrows():
        s = pd.read_csv(RES / "B" / f"{r.label}_u{r.users}_server.csv")
        rows.append({"light_p95_ms": s[s.route == "/instances/summary"].client_ms.quantile(.95),
                     "heavy_p95_ms": s[s.route == "/simulate"].client_ms.quantile(.95)})
    b = pd.concat([b, pd.DataFrame(rows).round(0)], axis=1)
    b.to_csv(TAB / "B_cost.csv", index=False)

    order = ["mono_r1", "mono_r2", "micro_sim1", "micro_sim2", "micro_sim3"]
    names = {"mono_r1": "Mono ×1", "mono_r2": "Mono ×2", "micro_sim1": "Micro sim×1",
             "micro_sim2": "Micro sim×2", "micro_sim3": "Micro sim×3"}

    # Cost per 1,000 requests; hatched = missed the p95 target
    loads = sorted(b.users.unique())
    fig, axes = plt.subplots(1, len(loads), figsize=(12, 4), sharey=True)
    for ax, users in zip(axes, loads):
        d = b[b.users == users].set_index("label").loc[order]
        x = range(len(order))
        for i, (lab, r) in enumerate(d.iterrows()):
            ax.bar(i, r.usd_per_1k_requests * 1000, width=0.7, color=ARCH[r.arch],
                   hatch=None if r.meets_target else "////", edgecolor="#fcfcfb", linewidth=2)
            ax.text(i, r.usd_per_1k_requests * 1000, f"p95\n{r.p95_ms / 1000:.1f}s" if r.p95_ms >= 1000
                    else f"p95\n{r.p95_ms:.0f}ms", ha="center", va="bottom", fontsize=8, color=INK2)
        ax.set_xticks(list(x), [names[l] for l in order], rotation=30, ha="right")
        ax.set_title(f"{users} users", loc="left")
        ax.grid(axis="x", visible=False)
    axes[0].set_ylabel("Cost per 1,000 requests (USD × 1000)")
    fig.suptitle(f"Experiment B: cost per request (blue = monolith, orange = microservices; "
                 f"hatched = p95 above {P95_TARGET_MS} ms)", x=0.01, ha="left", fontsize=11, color=INK2)
    save(fig, "B_cost_per_request.png")

    # Fault isolation: latency of LIGHT requests when the heavy part is overloaded
    users = max(loads)
    d = b[b.users == users].set_index("label").loc[order]
    fig, ax = plt.subplots(figsize=(7, 3.8))
    for i, (lab, r) in enumerate(d.iterrows()):
        ax.bar(i, r.light_p95_ms, width=0.7, color=ARCH[r.arch])
        ax.text(i, r.light_p95_ms, f"{r.light_p95_ms:.0f} ms", ha="center", va="bottom", fontsize=9)
    ax.set_xticks(range(len(order)), [names[l] for l in order], rotation=20, ha="right")
    ax.set_ylabel("p95 of light requests (ms)")
    ax.set_title(f"Light requests stay fast in microservices when the heavy service is overloaded "
                 f"({users} users)", loc="left", fontsize=10)
    ax.grid(axis="x", visible=False)
    save(fig, "B_fault_isolation.png")
    return b


# ----------------------------------------------------------------- Experiment C
def read_metric_json(path):
    raw = path.read_bytes()
    for enc in ("utf-16", "utf-8-sig", "utf-8"):
        try:
            return json.loads(raw.decode(enc))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
    raise ValueError(f"cannot read {path}")


def experiment_c():
    c = pd.read_csv(RES / "C" / "summary.csv", parse_dates=["start_utc", "end_utc"])
    metric = RES / "C" / "sim_replicas_metric.json"
    if metric.exists():
        pts = pd.DataFrame(read_metric_json(metric)["value"][0]["timeseries"][0]["data"])
        pts["timeStamp"] = pd.to_datetime(pts.timeStamp)
        pts["maximum"] = pts["maximum"].fillna(0)
        rm = []
        for _, r in c.iterrows():
            w = pts[(pts.timeStamp >= r.start_utc.floor("min")) & (pts.timeStamp <= r.end_utc)]
            rm.append(int(w["maximum"].sum()))
        c["replica_minutes"] = rm
        c["usd_per_test"] = (c.replica_minutes * 60 * usd_per_s(*SIM_REPLICA)).round(4)
    c.to_csv(TAB / "C_autoscaling.csv", index=False)

    # Timeline: replicas and latency over time, spike shaded
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 6.5), sharex=True)
    for lab in c.label:
        t = pd.read_csv(RES / "C" / f"{lab}_timeline.csv")
        ax1.step(t.window, t.sim_replicas.fillna(0), where="post", color=POLICY[lab], label=lab)
        ax2.plot(t.window, t.p95_ms, color=POLICY[lab], label=lab)
    for ax in (ax1, ax2):
        ax.axvspan(60, 300, color=GRID, alpha=0.6, lw=0)
    ax1.text(62, 5.2, "spike: 150 users", fontsize=9, color=INK2, va="bottom")
    ax1.set_ylabel("Simulation replicas\nanswering")
    ax1.set_ylim(0, 5.8)
    ax1.legend(ncol=5, loc="lower center", bbox_to_anchor=(0.5, 1.0), fontsize=9)
    ax2.set_yscale("log")
    ax2.set_ylabel("p95 latency, all\nrequests (ms, log)")
    ax2.set_xlabel("Seconds since test start (10 users → 150 users at 60 s → 10 users at 300 s)")
    fig.suptitle("Experiment C: how each autoscaling policy reacts to a traffic spike "
                 "(http_min0 and http_min1 overlap at 1 replica)", x=0.01, ha="left", fontsize=11, color=INK2)
    save(fig, "C_timeline.png")

    # Trade-off: latency during the spike vs replica-minutes (two panels, one axis each)
    if "replica_minutes" in c:
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 3.8))
        for i, r in c.reset_index().iterrows():
            ax1.bar(i, r.spike_p95_ms / 1000, color=POLICY[r.label], width=0.7)
            ax1.text(i, r.spike_p95_ms / 1000, f"{r.spike_p95_ms / 1000:.1f}s", ha="center", va="bottom", fontsize=9)
            ax2.bar(i, r.replica_minutes, color=POLICY[r.label], width=0.7)
            ax2.text(i, r.replica_minutes, f"{r.replica_minutes}", ha="center", va="bottom", fontsize=9)
        for ax in (ax1, ax2):
            ax.set_xticks(range(len(c)), c.label, rotation=20, ha="right")
            ax.grid(axis="x", visible=False)
        ax1.set_title("p95 latency during the spike (s), lower is better", loc="left", fontsize=10)
        ax2.set_title("Replica-minutes used in the 8-minute test (cost)", loc="left", fontsize=10)
        save(fig, "C_tradeoff.png")
    return c


def write_summary(peak, b, c):
    lines = ["# Results summary", "", "Generated by `analysis/make_figures.py`.", "",
             "## Experiment A: break-even (equal 1.5 vCPU budget)", "",
             "| Problem size | Monolith peak req/s | Microservices peak req/s | Monolith / micro |",
             "|---|---|---|---|"]
    for size in ["small", "medium", "large"]:
        if size in peak.index:
            p = peak.loc[size]
            lines.append(f"| {size} | {p['mono']:.1f} | {p['micro']:.1f} | {p['mono_over_micro']:.1f}× |")
    lines += ["", f"## Experiment B: cheapest configuration meeting p95 ≤ {P95_TARGET_MS} ms", "",
              "| Users | Configuration | p95 (ms) | USD per 1,000 requests |", "|---|---|---|---|"]
    for users, d in b.groupby("users"):
        ok = d[d.meets_target].sort_values("usd_per_1k_requests")
        if len(ok):
            r = ok.iloc[0]
            lines.append(f"| {users} | {r.label} | {r.p95_ms:.0f} | {r.usd_per_1k_requests:.6f} |")
        else:
            r = d.sort_values("p95_ms").iloc[0]
            lines.append(f"| {users} | none met target (best: {r.label}) | {r.p95_ms:.0f} | {r.usd_per_1k_requests:.6f} |")
    lines += ["", "## Experiment C: autoscaling policies under a spike", "",
              "| Policy | Spike p95 (ms) | Max replicas | Scale-out lag (s) | Replica-minutes |",
              "|---|---|---|---|---|"]
    for _, r in c.iterrows():
        lag = "" if pd.isna(r.scale_out_lag_s) else r.scale_out_lag_s
        lines.append(f"| {r.label} | {r.spike_p95_ms:.0f} | {r.max_sim_replicas} | {lag} | "
                     f"{r.get('replica_minutes', '')} |")
    (RES / "RESULTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("  summary:", RES / "RESULTS.md")


def main():
    FIG.mkdir(parents=True, exist_ok=True)
    TAB.mkdir(parents=True, exist_ok=True)
    print("Experiment A"); peak = experiment_a()
    print("Experiment B"); b = experiment_b()
    print("Experiment C"); c = experiment_c()
    write_summary(peak, b, c)


if __name__ == "__main__":
    main()
