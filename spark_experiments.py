import argparse
import csv
import statistics
import time
from pathlib import Path
import matplotlib
from matplotlib import pyplot as plt
from matplotlib.lines import Line2D

import spark_reducer as sr  # Spark module (kept separate, imported only)

MATCH_TYPES = ("FULL", "PARTIAL")
METRICS = ("full_macro", "full_micro", "partial_macro", "partial_micro")

# ---------------------------------------------------------------- helpers
def load_data_and_run_match(spark, db_path, qlog_path, partitions=None):
    """Load graphs + queries and run the matching once. Returns a context dict."""
    timings = {}

    # Load graphs and queries
    t = time.perf_counter()
    graphs = sr.load_graphs(spark, db_path, partitions)
    num_graphs = graphs.count()          # force loading
    queries = sr.load_queries(qlog_path)
    timings["load"] = time.perf_counter() - t

    # Perform matching
    t = time.perf_counter()
    matches = sr.run_matching(spark, graphs, queries)
    num_matches = matches.count()        # force matching
    timings["matching"] = time.perf_counter() - t

    return {"graphs": graphs, "matches": matches, "queries": queries,
            "num_graphs": num_graphs, "num_matches": num_matches,
            "timings": timings}

def release(ctx):
    """ Uncaches spark DataFrames (used for experimenting with multiple databases)."""
    ctx["graphs"].unpersist()
    ctx["matches"].unpersist()


def run_config(spark, ctx, method, alpha, budget):
    """Performs scoring, reduction and evaluation for certain method, alpha and budget B."""

    # Compute scores and reduce graphs
    t = time.perf_counter()
    scores = sr.compute_scores(spark, ctx["matches"], ctx["num_graphs"], method, alpha)
    kept_df = sr.select_top(scores, budget, ctx["num_graphs"])
    kept_df.count()
    t_score = time.perf_counter() - t

    # Evaluate retention quality
    t = time.perf_counter()
    ret = sr.evaluate(ctx["matches"], kept_df, len(ctx["queries"]))
    t_eval = time.perf_counter() - t

    kept_df.unpersist()
    return ret, t_score, t_eval

def retention_fields(ret):
    out = {}
    for match_type in MATCH_TYPES:
        out[f"{match_type.lower()}_macro"] = ret[match_type]["macro"]
        out[f"{match_type.lower()}_micro"] = ret[match_type]["micro"]
        out[f"{match_type.lower()}_skipped"] = ret[match_type]["skipped"]
    return out

def write_csv(rows, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"Saved {path}")

def safe_name(label):
    """Make a label usable inside a file name."""
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in label)

def qlog_labels(args):
    """Short names for the query logs: --qlog-names if given, else the file stems."""
    if args.qlog_names:
        if len(args.qlog_names) != len(args.qlogs):
            raise SystemExit("--qlog-names must have the same number of names as --qlogs")
        return list(args.qlog_names)
    labels = [Path(q).stem for q in args.qlogs]
    if len(set(labels)) != len(labels):      # e.g. two files both called queries.log
        labels = [f"qlog{i + 1}" for i in range(len(labels))]
    return labels


# Experiment 1: we use different B's and alpha's with a fixed datbase in order to obtain the retention trend.

def run_experiment1_on_certain_qlog(spark, args, qlog_path, label):
    """Match once for this query log, then try every (method, alpha, B)."""
    ctx = load_data_and_run_match(spark, Path(args.database), Path(qlog_path), args.partitions)
    print(f"Graphs: {ctx['num_graphs']} | Queries: {len(ctx['queries'])} | "
          f"Matches: {ctx['num_matches']} | match time {ctx['timings']['matching']:.2f}s")

    configs = [("rarity", a) for a in args.alphas] + [("baseline", None)]
    rows = []
    for method, alpha in configs:
        for b in args.budgets:
            ret, t_score, t_eval = run_config(
                spark, ctx, method, alpha if alpha is not None else 0.5, b)
            row = {"qlog": label, "method": method,
                   "alpha": alpha if alpha is not None else "",
                   "budget": b, "num_queries": len(ctx["queries"]),
                   "num_matches": ctx["num_matches"],
                   "score_select_s": round(t_score, 4),
                   "eval_s": round(t_eval, 4)}
            row.update(retention_fields(ret))
            rows.append(row)
            print(f"{method:<8} alpha={alpha}  B={b:<4} "
                  f"FULL macro {row['full_macro']:.4f} micro {row['full_micro']:.4f} | "
                  f"PARTIAL macro {row['partial_macro']:.4f} micro {row['partial_micro']:.4f}")
    release(ctx)
    return rows


def experiment1(spark, args, out_dir):
    labels = qlog_labels(args)
    results = {}

    for label, qlog in zip(labels, args.qlogs):
        print(f"\n=== Experiment 1 | query log '{label}' ({qlog}) ===")
        rows = run_experiment1_on_certain_qlog(spark, args, qlog, label)
        results[label] = rows

        # One query log keeps the original file names; two logs get one set each
        stem = "exp1_budget_alpha" if len(labels) == 1 else f"exp1_{safe_name(label)}"
        write_csv(rows, out_dir / f"{stem}.csv")
        plot_exp1(rows, out_dir / f"{stem}.png", title=label if len(labels) > 1 else None)

    if len(labels) == 2:
        compare_exp1(results[labels[0]], results[labels[1]], labels, out_dir)


def series_of(rows):
    """Distinct (method, alpha) lines: rarity alphas first, baseline last."""
    return sorted({(r["method"], r["alpha"]) for r in rows},
                  key=lambda s: (s[0] != "rarity", str(s[1])))


def plot_exp1(rows, path, title=None):
    fig, axes = plt.subplots(2, 2, figsize=(11, 8), sharex=True)
    panels = [("full_macro", "FULL - macro"), ("full_micro", "FULL - micro"),
              ("partial_macro", "PARTIAL - macro"), ("partial_micro", "PARTIAL - micro")]
    for ax, (key, panel_title) in zip(axes.flat, panels):
        for method, alpha in series_of(rows):
            pts = sorted((r["budget"], r[key]) for r in rows
                         if r["method"] == method and r["alpha"] == alpha)
            label = f"rarity a={alpha}" if method == "rarity" else "baseline"
            ax.plot(*zip(*pts), marker="o", linestyle="--" if method == "baseline" else "-",
                    color="black" if method == "baseline" else None, label=label)
        ax.set_title(panel_title)
        ax.set_ylabel("retention")
        ax.grid(alpha=0.3)
    for ax in axes[1]:
        ax.set_xlabel("budget B")
    axes[0][0].legend(fontsize=8)
    if title:
        fig.suptitle(f"Query log: {title}")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"Saved {path}")


# ------------------------------------------- experiment 1: log comparison

def compare_exp1(rows_a, rows_b, labels, out_dir):
    """Compare the two query logs: side-by-side CSV, console summary, overlay plot."""
    la, lb = labels
    key = lambda r: (r["method"], r["alpha"], r["budget"])
    idx_a = {key(r): r for r in rows_a}
    idx_b = {key(r): r for r in rows_b}

    # Wide table: one row per (method, alpha, B) with both logs and the difference
    wide = []
    for k in idx_a:
        ra, rb = idx_a[k], idx_b[k]
        row = {"method": k[0], "alpha": k[1], "budget": k[2]}
        for m in METRICS:
            row[f"{m}_{la}"] = round(ra[m], 6)
            row[f"{m}_{lb}"] = round(rb[m], 6)
            row[f"{m}_diff"] = round(rb[m] - ra[m], 6)   # second log minus first log
        wide.append(row)
    write_csv(wide, out_dir / "exp1_comparison.csv")

    # Console summary: mean retention over all budgets, per method/alpha
    print(f"\n=== Comparison: mean retention over all B  (diff = {lb} - {la}) ===")
    print(f"{'':<17}{'FULL micro':<34}{'PARTIAL micro':<34}")
    print(f"{'method':<10}{'alpha':<7}" + f"{la} | {lb} | diff".ljust(34) * 2)
    for method, alpha in series_of(rows_a):
        cells = []
        for m in ("full_micro", "partial_micro"):
            va = statistics.mean(r[m] for r in rows_a if (r["method"], r["alpha"]) == (method, alpha))
            vb = statistics.mean(r[m] for r in rows_b if (r["method"], r["alpha"]) == (method, alpha))
            cells.append(f"{va:.4f} | {vb:.4f} | {vb - va:+.4f}".ljust(34))
        print(f"{method:<10}{str(alpha):<7}" + "".join(cells))

    plot_compare_exp1(rows_a, rows_b, labels, out_dir / "exp1_comparison.png")


def plot_compare_exp1(rows_a, rows_b, labels, path):
    """Same 2x2 panels as plot_exp1, colour = method/alpha, line style = query log."""
    styles = [("-", "o"), (":", "s")]
    all_series = series_of(rows_a)
    palette = plt.get_cmap("tab10")
    colors = {}
    for i, s in enumerate(all_series):
        colors[s] = "black" if s[0] == "baseline" else palette(i % 10)

    fig, axes = plt.subplots(2, 2, figsize=(12, 8.5), sharex=True)
    panels = [("full_macro", "FULL - macro"), ("full_micro", "FULL - micro"),
              ("partial_macro", "PARTIAL - macro"), ("partial_micro", "PARTIAL - micro")]
    for ax, (key, panel_title) in zip(axes.flat, panels):
        for rows, (ls, mk) in zip((rows_a, rows_b), styles):
            for s in all_series:
                pts = sorted((r["budget"], r[key]) for r in rows
                             if (r["method"], r["alpha"]) == s)
                ax.plot(*zip(*pts), color=colors[s], linestyle=ls, marker=mk, markersize=4)
        ax.set_title(panel_title)
        ax.set_ylabel("retention")
        ax.grid(alpha=0.3)
    for ax in axes[1]:
        ax.set_xlabel("budget B")

    # Two-part legend: colours = methods, line styles = query logs
    method_handles = [Line2D([0], [0], color=colors[s],
                             label=f"rarity a={s[1]}" if s[0] == "rarity" else "baseline")
                      for s in all_series]
    log_handles = [Line2D([0], [0], color="gray", linestyle=ls, marker=mk, label=lab)
                   for (ls, mk), lab in zip(styles, labels)]
    fig.legend(handles=method_handles + log_handles, loc="lower center",
               ncol=len(method_handles) + 2, fontsize=8)
    fig.suptitle(f"Query log comparison: {labels[0]} (solid) vs {labels[1]} (dotted)")
    fig.tight_layout(rect=(0, 0.05, 1, 0.97))
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"Saved {path}")


# Experiment 2: Running reduction over databases of different size to measure the performance in terms of latency with fixed B and alpha.
def experiment2(spark, args, out_dir):
    methods = [("rarity", args.alpha), ("baseline", 0.5)]
    rows = []
    for name, db, qlog in args.dataset:
        for rep in range(args.repeats):
            t0 = time.perf_counter()
            ctx = load_data_and_run_match(spark, Path(db), Path(qlog), args.partitions)
            for method, alpha in methods:
                ret, t_score, t_eval = run_config(spark, ctx, method, alpha, args.budget)
                row = {"dataset": name, "repeat": rep, "method": method,
                       "alpha": alpha if method == "rarity" else "",
                       "budget": args.budget,
                       "num_graphs": ctx["num_graphs"],
                       "num_queries": len(ctx["queries"]),
                       "num_matches": ctx["num_matches"],
                       "load_s": round(ctx["timings"]["load"], 4),
                       "matching_s": round(ctx["timings"]["matching"], 4),
                       "score_select_s": round(t_score, 4),
                       "eval_s": round(t_eval, 4)}
                row["total_s"] = round(row["load_s"] + row["matching_s"] + t_score + t_eval, 4)
                row.update(retention_fields(ret))
                rows.append(row)
            release(ctx)
            print(f"{name} repeat {rep}: done in {time.perf_counter() - t0:.1f}s")

    write_csv(rows, out_dir / "exp2_datasets_raw.csv")

    # Summary: median over repeats
    summary = []
    keys = sorted({(r["dataset"], r["method"]) for r in rows},
                  key=lambda k: [d[0] for d in args.dataset].index(k[0]))
    numeric = ["load_s", "matching_s", "score_select_s", "eval_s", "total_s",
               "full_macro", "full_micro", "partial_macro", "partial_micro"]
    for ds, method in keys:
        grp = [r for r in rows if r["dataset"] == ds and r["method"] == method]
        s = {k: grp[0][k] for k in ("dataset", "method", "alpha", "budget",
                                    "num_graphs", "num_queries", "num_matches")}
        for k in numeric:
            s[k] = round(statistics.median(r[k] for r in grp), 4)
        summary.append(s)
        print(f"{ds:<10} {method:<8} total {s['total_s']:.2f}s (match {s['matching_s']:.2f}s) | "
              f"FULL macro {s['full_macro']:.4f} micro {s['full_micro']:.4f} | "
              f"PARTIAL macro {s['partial_macro']:.4f} micro {s['partial_micro']:.4f}")
    write_csv(summary, out_dir / "exp2_datasets_summary.csv")
    plot_exp2(summary, out_dir / "exp2_datasets.png")


def plot_exp2(summary, path):
    datasets = list(dict.fromkeys(s["dataset"] for s in summary))
    methods = list(dict.fromkeys(s["method"] for s in summary))
    width = 0.8 / len(methods)

    fig, axes = plt.subplots(1, 5, figsize=(23, 4.5))

    panels = [
        ("full_macro", "FULL macro retention"),
        ("full_micro", "FULL micro retention"),
        ("partial_macro", "PARTIAL macro retention"),
        ("partial_micro", "PARTIAL micro retention"),
        ("total_s", "Total time (s)")
    ]

    for ax, (key, title) in zip(axes, panels):
        for i, m in enumerate(methods):
            vals = [
                next(
                    (s[key] for s in summary
                     if s["dataset"] == d and s["method"] == m),
                    0
                )
                for d in datasets
            ]

            ax.bar(
                [x + i * width for x in range(len(datasets))],
                vals,
                width,
                label=m
            )

        ax.set_xticks([
            x + width * (len(methods) - 1) / 2
            for x in range(len(datasets))
        ])
        ax.set_xticklabels(datasets, rotation=20, ha="right")
        ax.set_title(title)
        ax.grid(axis="y", alpha=0.3)
        ax.set_axisbelow(True)

    axes[0].legend()
    fig.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)

    print(f"Saved {path}")

def main():
    p = argparse.ArgumentParser(description="Experiments for graph DB reduction with Spark.")
    p.add_argument("--exp", type=int, choices=[1, 2], required=True)
    p.add_argument("--out-dir", default="results/experiments")
    p.add_argument("--master", default="local[*]")
    p.add_argument("--partitions", type=int, default=None)
    # experiment 1
    p.add_argument("--database")
    p.add_argument("--qlogs", "--qlog", dest="qlogs", nargs="+", metavar="QLOG",
                   help="one query log, or two (e.g. uniform and skewed) to run and compare both")
    p.add_argument("--qlog-names", nargs="+", metavar="NAME",
                   help="labels for the query logs (default: file names)")
    p.add_argument("--budgets", type=float, nargs="+", default=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9])
    p.add_argument("--alphas", type=float, nargs="+", default=[0.0, 0.25, 0.5, 0.75, 1.0])
    # experiment 2
    p.add_argument("--dataset", nargs=3, action="append", metavar=("NAME", "DB", "QLOG"))
    p.add_argument("--budget", type=float, default=0.5)
    p.add_argument("--alpha", type=float, default=0.5)
    p.add_argument("--repeats", type=int, default=3)
    args = p.parse_args()

    if args.exp == 1:
        if not (args.database and args.qlogs):
            p.error("--exp 1 needs --database and --qlogs")
        if len(args.qlogs) > 2:
            p.error("--qlogs accepts one or two query logs")
    if args.exp == 2 and not args.dataset:
        p.error("--exp 2 needs at least one --dataset NAME DB QLOG")

    out_dir = Path(args.out_dir)
    spark = sr.create_spark(args.master)
    try:
        spark.range(10).count()  # warm-up: JVM start-up must not pollute the first timing
        if args.exp == 1:
            experiment1(spark, args, out_dir)
        else:
            experiment2(spark, args, out_dir)
    finally:
        spark.stop()


if __name__ == "__main__":
    main()