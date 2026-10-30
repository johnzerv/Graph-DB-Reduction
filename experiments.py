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
from typing import List

import matplotlib.pyplot as plt

from graph import GraphDB
from query_engine import QueryEngine
from reducer import BaselineScoreReducer, RarityScoreReducer, OverlapParticipationRatioReducer
from evaluator import Evaluator

METRICS = ["full_macro", "full_micro", "partial_macro", "partial_micro"]

class ExperimentConfig:
    def __init__(self, num_graphs: int, num_queries: int, group_number: str,
                 modes: list[str], budgets: list[float], alpha: float,
                 out_dir: Path):
        self.num_graphs = num_graphs
        self.num_queries = num_queries
        self.group_number = group_number
        self.modes = modes
        self.budgets = budgets
        self.alpha = alpha
        self.out_dir = out_dir

    @property
    def file_stem(self) -> str:
        return f"compare_G{self.group_number}_{self.num_graphs}_{self.num_queries}"

class ExperimentRunner:
    def __init__(self, config: ExperimentConfig):
        self.config = config
        self.evaluator = Evaluator()

    def _restrict(self, answers_by_query: dict[str, list[int]], kept: set[int]) -> dict[str, list[int]]:
        """Answers on the reduced database = original answers from the kept graphs."""
        return {q: [g for g in answers if g in kept] for q, answers in answers_by_query.items()}

    def _evaluate(self, full: dict[str, list[int]], partial: dict[str, list[int]], kept: set[int]) -> dict[str, float]:
        r_full = self.evaluator.evaluate(full, self._restrict(full, kept))
        r_part = self.evaluator.evaluate(partial, self._restrict(partial, kept))
        return {
            "full_macro": r_full["macro"],
            "full_micro": r_full["micro"],
            "partial_macro": r_part["macro"],
            "partial_micro": r_part["micro"],
        }

    def _run_score_method(self, scores: dict[int, float], full: dict[str, list[int]], partial: dict[str, list[int]], budget: float) -> dict[str, float]:
        """Score-based methods runner (baseline, rarity, and overlap-participation ratio) across different "budgets" B."""
        k = max(1, int(len(scores) * budget))
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        kept = {g_idx for g_idx, _ in ranked[:k]}
        return self._evaluate(full, partial, kept)

    # def _run_recall_greedy(self, graph_db, full, partial, budget) -> dict[str, float]:
    #     """Runner for the iterative greedy reduction method."""
    #     reducer = RecallGreedyReducer(
    #         graphDB=graph_db,
    #         retain_percentage=budget,
    #         metric="macro",
    #         match_type="FULL",
    #     )
    #     reduced_db = reducer.reduce(answers_original_by_query=full)
    #     _, query_full_matches, query_partial_matches, _, _ = QueryEngine(
    #         reduced_db,
    #         log_filepath=graph_db.log_file,
    #     ).run()

    #     # Map reduced indices back to original graph indices
    #     query_full_matches = {
    #         query: [reducer.retained_graph_indices[i] for i in graph_ids]
    #         for query, graph_ids in query_full_matches.items()
    #     }
    #     query_partial_matches = {
    #         query: [reducer.retained_graph_indices[i] for i in graph_ids]
    #         for query, graph_ids in query_partial_matches.items()
    #     }
        
    #     full_result = self.evaluator.evaluate(full, query_full_matches)
    #     partial_result = self.evaluator.evaluate(partial, query_partial_matches)
    #     return {
    #         "full_macro": full_result["macro"],
    #         "full_micro": full_result["micro"],
    #         "partial_macro": partial_result["macro"],
    #         "partial_micro": partial_result["micro"],
    #     }

    def run_mode(self, mode: str) -> list[dict[str, float]]:
        graphDB = GraphDB(
            num_graphs=self.config.num_graphs,
            num_queries=self.config.num_queries,
            group_number=self.config.group_number,
            query_mode=mode,
            dataset_dir=Path("datasets")
        )
        if not graphDB.database_file.exists() or not graphDB.log_file.exists():
            raise SystemExit(f"Missing {graphDB.database_file} or {graphDB.log_file}. Generate them with graph.py first.")

        print(f"Running queries for the {mode} distribution ({graphDB.log_file.name})...")
        with contextlib.redirect_stdout(io.StringIO()):  # the engine prints every query
            engine = QueryEngine(graphDB.database_file, graphDB.log_file)
            pairs, full_by_query, partial_by_query, full_by_graph, partial_by_graph = engine.run()

        # Precompute scores once per query log
        methods_scores = {
            "baseline": BaselineScoreReducer(graphDB=graphDB).calculate_scores(pairs),
            "rarity": RarityScoreReducer(graphDB=graphDB, alpha=self.config.alpha).calculate_scores(pairs),
            "overlap_participation": OverlapParticipationRatioReducer(graphDB=graphDB).calculate_scores(
                full_matches_by_graph=full_by_graph, 
                partial_matches_by_graph=partial_by_graph
            ),
        }

        results = []
        for budget in self.config.budgets:
            # Run score-based methods
            for name, scores in methods_scores.items():
                results.append({
                    "query distribution": mode,
                    "method": name,
                    "B": budget,
                    **self._run_score_method(scores, full_by_query, partial_by_query, budget)
                })
            # Run greedy method
            # results.append({
            #     "query distribution": mode,
            #     "method": "recall-greedy",
            #     "B": budget,
            #     **self._run_recall_greedy(graphDB, full, partial, budget),
            # })
        return results

    def execute(self):
        results = []
        for mode in self.config.modes:
            results.extend(self.run_mode(mode))
        return results

    @staticmethod
    def save_csv(rows, path):
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["query distribution", "method", "B", *METRICS])
            writer.writeheader()
            for row in rows:
                writer.writerow({k: (f"{v:.4f}" if k in METRICS else v) for k, v in row.items()})

    @staticmethod
    def print_table(rows):
        print(f"\n{'query distribution':<20} {'method':<20} {'B':>4}  {'full macro':>10} {'full micro':>10} {'part macro':>10} {'part micro':>10}")
        for row in rows:
            print(f"{row['query distribution']:<20} {row['method']:<20} {row['B']:>4}  " + " ".join(f"{row[m]:>10.2f}" for m in METRICS))

    @staticmethod
    def plot_results(rows, config: ExperimentConfig):
        methods = list(dict.fromkeys(row["method"] for row in rows))  # keeps insertion order
        colors = plt.get_cmap("tab10").colors
        markers = ["o", "s", "^", "D", "v", "P"]
        linestyles = ["-", "--", "-.", (0, (5, 1)), (0, (3, 1, 1, 1)), ":"]
        styles = {
            m: dict(color=colors[i % len(colors)], marker=markers[i % len(markers)],
                    linestyle=linestyles[i % len(linestyles)], markersize=6, linewidth=2)
            for i, m in enumerate(methods)
        }
        col_titles = {
            "full_macro": "Full matches\nmacro recall",
            "full_micro": "Full matches\nmicro recall",
            "partial_macro": "Partial matches\nmacro recall",
            "partial_micro": "Partial matches\nmicro recall",
        }

        n_rows, n_cols = len(config.modes), len(METRICS)
        fig, axes = plt.subplots(n_rows, n_cols, figsize=(3.4 * n_cols, 3.2 * n_rows),
                                 sharex=True, sharey=True, squeeze=False)

        for r, mode in enumerate(config.modes):
            for c, metric in enumerate(METRICS):
                ax = axes[r][c]
                # Reference: keeping a random fraction B of graphs gives ~B recall
                ax.plot([0, 1], [0, 1], color="#999999", linestyle=":", linewidth=1.2,
                        label="random (recall ~ B)", zorder=1)
                for name in methods:
                    pts = sorted((row["B"], row[metric]) for row in rows
                                 if row["query distribution"] == mode and row["method"] == name)
                    ax.plot([p[0] for p in pts], [p[1] for p in pts], label=name, zorder=2, **styles[name])

                ax.set_xlim(0, 1)
                ax.set_ylim(0, 1.02)
                ax.set_xticks(config.budgets)
                ax.set_xticklabels([f"{int(round(b * 100))}%" for b in config.budgets])
                ax.grid(True, color="#e6e6e3", linewidth=0.8)
                ax.spines[["top", "right"]].set_visible(False)
                ax.tick_params(colors="#555555", labelsize=9)

                if r == 0:
                    ax.set_title(col_titles[metric], fontsize=10, color="#333333")
                if c == 0:
                    ax.set_ylabel(f"{mode} distribution\n\nrecall", color="#555555")
                if r == n_rows - 1:
                    ax.set_xlabel("B (graphs kept)", color="#555555")

        handles, labels = axes[0][0].get_legend_handles_labels()
        fig.legend(handles, labels, loc="upper center", ncol=len(labels), frameon=False)
        fig.tight_layout(rect=(0, 0, 1, 0.94))
        png_path = config.out_dir / f"{config.file_stem}.png"
        fig.savefig(png_path, dpi=150)
        print(f"\nSaved {config.out_dir / f'{config.file_stem}.csv'} and {png_path}")

def parse_arguments():
    parser = argparse.ArgumentParser(description="Compare baseline and rarity reduction.")
    parser.add_argument("-n", "--num-graphs", type=int, default=2000, help="number of graphs in the database (default: 2000)")
    parser.add_argument("-q", "--num-queries", type=int, default=1000, help="number of queries in the query log (default: 1000)")
    parser.add_argument("--group-number", default="13", help="group number used in filenames (default: 13)")
    parser.add_argument("--modes", nargs="+", default=["uniform", "skewed"], help="query distributions to test (default: uniform skewed)")
    parser.add_argument("--budgets", nargs="+", type=float, default=[0.1, 0.3, 0.5, 0.7, 0.9], help="values of B to test")
    parser.add_argument("--alpha", type=float, default=0.5, help="rarity weight for partial matches (default: 0.5)")
    parser.add_argument("--out", default="results", help="output folder (default: results)")

    args = parser.parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(exist_ok=True)
    
    return ExperimentConfig(
        num_graphs=args.num_graphs,
        num_queries=args.num_queries,
        group_number=args.group_number,
        modes=args.modes,
        budgets=args.budgets,
        alpha=args.alpha,
        out_dir=out_dir
    )

if __name__ == "__main__":
    config = parse_arguments()

    runner = ExperimentRunner(config)
    results = runner.execute()

    runner.save_csv(results, config.out_dir / f"{config.file_stem}.csv")
    runner.print_table(results)
    runner.plot_results(results, config)