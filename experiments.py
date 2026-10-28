"""Compare the baseline and rarity methods for several budgets (B) and query logs.

Outputs (in results):
    compare_G<group>_<graphs>_<queries>.csv   one row per (log, method, B)
    compare_G<group>_<graphs>_<queries>.png   recall vs B charts
"""
import argparse
import contextlib
import csv
import io
from pathlib import Path

import matplotlib.pyplot as plt

from graph import GraphDB
from query_engine import QueryEngine
from reducer import BaselineReducer, RarityReducer
from evaluator import Evaluator

parser = argparse.ArgumentParser(description="Compare baseline and rarity reduction.")
parser.add_argument("-n", "--num-graphs", type=int, default=2000, help="number of graphs in the database (default: 2000)")
parser.add_argument("-q", "--num-queries", type=int, default=1000, help="number of queries in the query log (default: 1000)")
parser.add_argument("--group-number", default="13", help="group number used in filenames (default: 13)")
parser.add_argument("--modes", nargs="+", default=["uniform", "skewed"], help="query logs to test (default: uniform skewed)")
parser.add_argument("--budgets", nargs="+", type=float, default=[0.1, 0.3, 0.5, 0.7, 0.9], help="values of B to test")
parser.add_argument("--alpha", type=float, default=0.5, help="rarity weight for partial matches (default: 0.5)")
parser.add_argument("--out", default="results", help="output folder (default: results)")
args = parser.parse_args()

out_dir = Path(args.out)
out_dir.mkdir(exist_ok=True)
evaluator = Evaluator()
METRICS = ["full_macro", "full_micro", "partial_macro", "partial_micro"]


def keep_top(scores, budget):
    """Same selection rule as BaselineReducer.reduce(), without writing files."""
    k = max(1, int(len(scores) * budget))
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    return {g_idx for g_idx, _ in ranked[:k]}


def restrict(answers_by_query, kept):
    """Answers on the reduced database = original answers from the kept graphs
    (each graph is evaluated on its own so there is no need to re-run the queries)"""
    return {q: [g for g in answers if g in kept] for q, answers in answers_by_query.items()}


def evaluate(full, partial, kept):
    r_full = evaluator.evaluate(full, restrict(full, kept))
    r_part = evaluator.evaluate(partial, restrict(partial, kept))
    return {"full_macro": r_full["macro"], "full_micro": r_full["micro"],
            "partial_macro": r_part["macro"], "partial_micro": r_part["micro"]}


rows = []
for mode in args.modes:
    graphDB = GraphDB(num_graphs=args.num_graphs, num_queries=args.num_queries,
                      group_number=args.group_number, query_mode=mode, dataset_dir=Path("datasets"))
    if not graphDB.database_file.exists() or not graphDB.log_file.exists():
        raise SystemExit(f"Missing {graphDB.database_file} or {graphDB.log_file}. Generate them with graph.py first.")

    print(f"Running queries for the {mode} log ({graphDB.log_file.name})...")
    with contextlib.redirect_stdout(io.StringIO()):  # the engine prints every query
        engine = QueryEngine(graphDB.database_file, graphDB.log_file)
        pairs, full, partial = engine.run()

    # Score the graphs once per method; each B is just a different cut of the ranking
    methods = {
        "baseline": BaselineReducer(graphDB=graphDB).calculate_scores(pairs),
        "rarity": RarityReducer(graphDB=graphDB, alpha=args.alpha).calculate_scores(pairs),
    }
    for budget in args.budgets:
        for name, scores in methods.items():
            rows.append({"log": mode, "method": name, "B": budget, **evaluate(full, partial, keep_top(scores, budget))})

# Save the table
stem = f"compare_G{args.group_number}_{args.num_graphs}_{args.num_queries}"
csv_path = out_dir / f"{stem}.csv"
with open(csv_path, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["log", "method", "B", *METRICS])
    writer.writeheader()
    for row in rows:
        writer.writerow({k: (f"{v:.4f}" if k in METRICS else v) for k, v in row.items()})

# Print the table
print(f"\n{'log':<8} {'method':<9} {'B':>4}  {'full macro':>10} {'full micro':>10} {'part macro':>10} {'part micro':>10}")
for row in rows:
    print(f"{row['log']:<8} {row['method']:<9} {row['B']:>4}  " + " ".join(f"{row[m]:>10.2f}" for m in METRICS))

# Charts: one row per metric, one column per query log
styles = {
    "baseline": dict(color="#2a78d6", marker="o", markersize=6, linewidth=2),
    "rarity": dict(color="#eb6834", marker="s", markersize=6, linewidth=2),
}
titles = {"full_macro": "Full matches: macro recall", "full_micro": "Full matches: micro recall",
          "partial_macro": "Partial matches: macro recall", "partial_micro": "Partial matches: micro recall"}
fig, axes = plt.subplots(len(METRICS), len(args.modes), figsize=(5.5 * len(args.modes), 3.4 * len(METRICS)),
                         sharex=True, sharey=True, squeeze=False)
for col, mode in enumerate(args.modes):
    for r, metric in enumerate(METRICS):
        ax = axes[r][col]
        for name, style in styles.items():
            pts = [(row["B"], row[metric]) for row in rows if row["log"] == mode and row["method"] == name]
            ax.plot([p[0] for p in pts], [p[1] for p in pts], label=name, **style)
        ax.set_title(f"{mode} log - {titles[metric]}", fontsize=10, color="#333333")
        ax.set_ylim(0, 1.02)
        ax.set_xticks(args.budgets)
        ax.grid(True, color="#e6e6e3", linewidth=0.8)
        ax.spines[["top", "right"]].set_visible(False)
        ax.tick_params(colors="#555555", labelsize=9)
        if r == len(METRICS) - 1:
            ax.set_xlabel("B (fraction of graphs kept)", color="#555555")
        if col == 0:
            ax.set_ylabel("recall", color="#555555")
handles, labels = axes[0][0].get_legend_handles_labels()
fig.legend(handles, labels, loc="upper center", ncol=len(labels), frameon=False)
fig.tight_layout(rect=(0, 0, 1, 0.97))
png_path = out_dir / f"{stem}.png"
fig.savefig(png_path, dpi=150)

print(f"\nSaved {csv_path} and {png_path}")
