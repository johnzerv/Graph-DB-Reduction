import argparse
from pathlib import Path

from graph import Graph, GraphDB
from query_engine import QueryEngine
from reducer import BaselineReducer
from visualizers import visualize_query_graph_relations
from evaluator import Evaluator


def print_recall_summary(title, result):
    query_summary = ", ".join(
        f"{query}={score:.2f}" for query, score in result["per_query"].items()
    )
    print(f"{title}")
    print(f"Query recall: {query_summary}")
    print(f"Macro recall: {result['macro']:.2f}")
    print(f"Micro recall: {result['micro']:.2f}")

parser = argparse.ArgumentParser(
    description="Evaluate the query log against a generated graph database."
)
parser.add_argument("-n", "--num-graphs", "--graphs", type=int, default=10, help="number of graphs in the database (default: 10)")
parser.add_argument("--num-queries", "-q", type=int, default=20, help="number of queries in the query log (default: 20)")
parser.add_argument("--query-mode", choices=["uniform", "skewed"], default="skewed", help="query generation mode (default: skewed)")
parser.add_argument("--group-number", default="13", help="group number used in database and query filenames (default: 13)")
args = parser.parse_args()

# Load the graph database and query log
graphDB = GraphDB(
    num_graphs=args.num_graphs,
    num_queries=args.num_queries,
    group_number=args.group_number,
    query_mode=args.query_mode,
    dataset_dir=Path("datasets"),
    database_file=Path(f"datasets/Database{args.group_number}_{args.num_graphs}.txt"),
    log_file=Path(f"datasets/QLog{args.group_number}_{args.num_graphs}_{args.num_queries}_{args.query_mode}.txt")
)

# Execute all queries to obtain the query answers
engine = QueryEngine(graphDB.database_file, graphDB.log_file)
query_answers, query_full_matches, query_partial_matches = engine.run()
# print(query_answers, query_full_matches, query_partial_matches)

# Use the baseline reducer (score system) to create a ranking of graphs based on the query results
baseline_reducer = BaselineReducer(graphDB=graphDB)
graph_scores = baseline_reducer.calculate_scores(query_answers)
baseline_reducer.print_ranking()

# Visualize the query-graph relationships
visualize_query_graph_relations(
    queries=engine.queries, 
    num_graphs=len(engine.graphs), 
    match_results=query_answers, 
    graph_scores=graph_scores,
    output_file=f"query_relations_G{graphDB.group_number}_{graphDB.num_graphs}_{graphDB.query_mode}.html"
)

# Proceed to the graph database reduction based on the baseline approach
reduced_graphDB = baseline_reducer.reduce()

# Re-execute the same query-set on the reduced graph database
engine = QueryEngine(reduced_graphDB.database_file, graphDB.log_file)
query_answers_reduced, query_full_matches_reduced, query_partial_matches_reduced = engine.run()

# Calculate recalls per-query, micro and macro average metrics for full matches
e = Evaluator()
result_full = e.evaluate(query_full_matches, query_full_matches_reduced)
print_recall_summary("--- FULL MATCH RECALL ---", result_full)

# Same for partial matches
result_partial = e.evaluate(query_partial_matches, query_partial_matches_reduced)
print_recall_summary("\n--- PARTIAL MATCH RECALL ---", result_partial)


