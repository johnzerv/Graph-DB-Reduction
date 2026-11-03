import argparse
import csv
import os
import statistics
import sys
import time
from pathlib import Path
import matplotlib
from matplotlib import pyplot as plt
from matplotlib.lines import Line2D
import pyspark
from pyspark.sql import SparkSession

from spark_query_engine import SparkQueryEngine
from spark_reducer import SparkBaselineReducer, SparkRarityReducer
from spark_evaluator import SparkRetentionEvaluator

# Enviromental Setup
os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
os.environ.setdefault("PYSPARK_DRIVER_PYTHON", sys.executable)
os.environ.setdefault("SPARK_HOME", os.path.dirname(pyspark.__file__))

MATCH_TYPES = ("FULL", "PARTIAL")
METRICS = ("full_macro", "full_micro", "partial_macro", "partial_micro")

# Utitlity functions
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

def series_of(rows):
    """Distinct (method, alpha) lines: rarity alphas first, baseline last."""
    return sorted({(r["method"], r["alpha"]) for r in rows},
                  key=lambda s: (s[0] != "rarity", str(s[1])))

class SparkExperimentRunner:
    """Orchestrates the experiments utilizing the OO Spark modules."""
    
    def __init__(self, spark, args, out_dir):
        self.spark = spark
        self.args = args
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.evaluator = SparkRetentionEvaluator()

    def run_config(self, matches_df, num_graphs, num_queries, method, alpha, budget):
        """Performs scoring, reduction and evaluation for a single configuration (Used in Exp 2)."""
        t0 = time.perf_counter()
        
        if method == "rarity":
            reducer = SparkRarityReducer(self.spark, num_graphs, retain_percentage=budget, alpha=alpha)
        else:
            reducer = SparkBaselineReducer(self.spark, num_graphs, retain_percentage=budget)
            
        reducer.calculate_scores(matches_df)
        kept_df = reducer.reduce()
        kept_df.count() # Force Spark execution
        t_score = time.perf_counter() - t0

        t1 = time.perf_counter()
        ret = self.evaluator.evaluate(matches_df, kept_df, num_queries)
        t_eval = time.perf_counter() - t1

        kept_df.unpersist()
        return ret, t_score, t_eval

    def run_exp1_single_qlog(self, db_path, qlog_path, label):
        """Match once for this query log, compute scores once per method, then test budgets."""
        engine = SparkQueryEngine(self.spark, db_path, qlog_path, self.args.partitions)
        engine.load_data()
        
        t1 = time.perf_counter()
        matches_df = engine.run()
        num_matches = matches_df.count() # Force matching execution
        match_time = time.perf_counter() - t1

        print(f"Graphs: {engine.num_graphs} | Queries: {len(engine.queries)} | "
              f"Matches: {num_matches} | match time {match_time:.2f}s")

        configs = [("rarity", a) for a in self.args.alphas] + [("baseline", None)]
        rows = []
        
        for method, alpha in configs:
            alpha_val = alpha if alpha is not None else 0.5
            
            # Calculate and Cache Scores once per method/alpha
            t_score_start = time.perf_counter()
            if method == "rarity":
                reducer = SparkRarityReducer(self.spark, engine.num_graphs, alpha=alpha_val)
            else:
                reducer = SparkBaselineReducer(self.spark, engine.num_graphs)
                
            scores_df = reducer.calculate_scores(matches_df).cache()
            scores_df.count() # Force Spark execution
            base_score_time = time.perf_counter() - t_score_start

            for b in self.args.budgets:
                reducer.retain_percentage = b
                
                t_slice = time.perf_counter()
                kept_df = reducer.reduce()
                kept_df.count() # Force slice execution
                t_score = base_score_time + (time.perf_counter() - t_slice)

                t_eval_start = time.perf_counter()
                ret = self.evaluator.evaluate(matches_df, kept_df, len(engine.queries))
                t_eval = time.perf_counter() - t_eval_start

                row = {"qlog": label, "method": method,
                       "alpha": alpha if alpha is not None else "",
                       "budget": b, "num_queries": len(engine.queries),
                       "num_matches": num_matches,
                       "score_select_s": round(t_score, 4),
                       "eval_s": round(t_eval, 4)}
                row.update(retention_fields(ret))
                rows.append(row)
                
                print(f"{method:<8} alpha={alpha}  B={b:<4} "
                      f"FULL macro {row['full_macro']:.4f} micro {row['full_micro']:.4f} | "
                      f"PARTIAL macro {row['partial_macro']:.4f} micro {row['partial_micro']:.4f}")
                      
                kept_df.unpersist()
                
            scores_df.unpersist()

        engine.graphs_df.unpersist()
        matches_df.unpersist()
        return rows

    def run_experiment1(self):
        labels = qlog_labels(self.args)
        results = {}

        for label, qlog in zip(labels, self.args.qlogs):
            print(f"\n=== Experiment 1 | query log '{label}' ({qlog}) ===")
            rows = self.run_exp1_single_qlog(self.args.database, qlog, label)
            results[label] = rows

            # One query log keeps the original file names; two logs get one set each
            stem = "exp1_budget_alpha" if len(labels) == 1 else f"exp1_{safe_name(label)}"
            write_csv(rows, self.out_dir / f"{stem}.csv")
            plot_exp1(rows, self.out_dir / f"{stem}.png", title=label if len(labels) > 1 else None)

        if len(labels) == 2:
            compare_exp1(results[labels[0]], results[labels[1]], labels, self.out_dir)

    def run_experiment2(self):
        methods = [("rarity", self.args.alpha), ("baseline", 0.5)]
        rows = []
        
        for name, db, qlog in self.args.dataset:
            for rep in range(self.args.repeats):
                t0_total = time.perf_counter()
                
                # Load and match
                engine = SparkQueryEngine(self.spark, db, qlog, self.args.partitions)
                
                t_load_start = time.perf_counter()
                engine.load_data()
                load_time = time.perf_counter() - t_load_start
                
                t_match_start = time.perf_counter()
                matches_df = engine.run()
                num_matches = matches_df.count()
                match_time = time.perf_counter() - t_match_start

                # Reduce for each method
                for method, alpha in methods:
                    ret, t_score, t_eval = self.run_config(
                        matches_df, engine.num_graphs, len(engine.queries),
                        method, alpha, self.args.budget
                    )
                    row = {"dataset": name, "repeat": rep, "method": method,
                           "alpha": alpha if method == "rarity" else "",
                           "budget": self.args.budget,
                           "num_graphs": engine.num_graphs,
                           "num_queries": len(engine.queries),
                           "num_matches": num_matches,
                           "load_s": round(load_time, 4),
                           "matching_s": round(match_time, 4),
                           "score_select_s": round(t_score, 4),
                           "eval_s": round(t_eval, 4)}
                    row["total_s"] = round(row["load_s"] + row["matching_s"] + t_score + t_eval, 4)
                    row.update(retention_fields(ret))
                    rows.append(row)
                    
                engine.graphs_df.unpersist()
                matches_df.unpersist()
                print(f"{name} repeat {rep}: done in {time.perf_counter() - t0_total:.1f}s")

        write_csv(rows, self.out_dir / "exp2_datasets_raw.csv")

        # Summary: median over repeats
        summary = []
        keys = sorted({(r["dataset"], r["method"]) for r in rows},
                      key=lambda k: [d[0] for d in self.args.dataset].index(k[0]))
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
                  
        write_csv(summary, self.out_dir / "exp2_datasets_summary.csv")
        plot_exp2(summary, self.out_dir / "exp2_datasets.png")


# Plotting methods
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


def compare_exp1(rows_a, rows_b, labels, out_dir):
    """Compare the two query logs: side-by-side CSV, console summary, overlay plot."""
    la, lb = labels
    key = lambda r: (r["method"], r["alpha"], r["budget"])
    idx_a = {key(r): r for r in rows_a}
    idx_b = {key(r): r for r in rows_b}

    wide = []
    for k in idx_a:
        ra, rb = idx_a[k], idx_b[k]
        row = {"method": k[0], "alpha": k[1], "budget": k[2]}
        for m in METRICS:
            row[f"{m}_{la}"] = round(ra[m], 6)
            row[f"{m}_{lb}"] = round(rb[m], 6)
            row[f"{m}_diff"] = round(rb[m] - ra[m], 6)
        wide.append(row)
    write_csv(wide, out_dir / "exp1_comparison.csv")

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
                next((s[key] for s in summary if s["dataset"] == d and s["method"] == m), 0)
                for d in datasets
            ]
            ax.bar([x + i * width for x in range(len(datasets))], vals, width, label=m)

        ax.set_xticks([x + width * (len(methods) - 1) / 2 for x in range(len(datasets))])
        ax.set_xticklabels(datasets, rotation=20, ha="right")
        ax.set_title(title)
        ax.grid(axis="y", alpha=0.3)
        ax.set_axisbelow(True)

    axes[0].legend()
    fig.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved {path}")

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Experiments for graph DB reduction with Spark.")
    p.add_argument("--exp", type=int, choices=[1, 2], required=True)
    p.add_argument("--out-dir", default="results/experiments")
    p.add_argument("--master", default="local[*]")
    p.add_argument("--partitions", type=int, default=None)
    
    # Experiment 1 arguments
    p.add_argument("--database")
    p.add_argument("--qlogs", "--qlog", dest="qlogs", nargs="+", metavar="QLOG",
                   help="one query log, or two (e.g. uniform and skewed) to run and compare both")
    p.add_argument("--qlog-names", nargs="+", metavar="NAME",
                   help="labels for the query logs (default: file names)")
    p.add_argument("--budgets", type=float, nargs="+", default=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9])
    p.add_argument("--alphas", type=float, nargs="+", default=[0.0, 0.25, 0.5, 0.75, 1.0])
    
    # Experiment 2 arguments
    p.add_argument("--dataset", nargs=3, action="append", metavar=("NAME", "DB", "QLOG"))
    p.add_argument("--budget", type=float, default=0.5)
    p.add_argument("--alpha", type=float, default=0.5)
    p.add_argument("--repeats", type=int, default=3)
    
    args = p.parse_args()

    # Error handling over the cli arguments
    if args.exp == 1:
        if not (args.database and args.qlogs):
            p.error("--exp 1 needs --database and --qlogs")
        if len(args.qlogs) > 2:
            p.error("--qlogs accepts one or two query logs")
    if args.exp == 2 and not args.dataset:
        p.error("--exp 2 needs at least one --dataset NAME DB QLOG")


    # Spark Session Configuration
    spark = (SparkSession.builder.master(args.master).appName("GraphDBReduction")
            .config("spark.ui.showConsoleProgress", "false")
            .config("spark.sql.shuffle.partitions", "8")
            .getOrCreate())
    spark.sparkContext.setLogLevel("ERROR")

    try:
        spark.range(10).count()  
        
        runner = SparkExperimentRunner(spark, args, args.out_dir)
        
        if args.exp == 1:
            runner.run_experiment1()
        else:
            runner.run_experiment2()
    finally:
        spark.stop()
