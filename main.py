import argparse
from pathlib import Path

from graph import Graph, GraphDB
from query_engine import QueryEngine
from reducer import BaselineReducer
from visualizers import visualize_query_graph_relations

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
query_answers = engine.run()

# Use the baseline reducer (score system) to create a ranking of graphs based on the query results
baseline_reducer = BaselineReducer(graphDB=graphDB)
graph_scores = baseline_reducer.calculate_scores(query_answers)

# Visualize the query-graph relationships
visualize_query_graph_relations(
    queries=engine.queries, 
    num_graphs=len(engine.graphs), 
    match_results=query_answers, 
    graph_scores=graph_scores,
    output_file=f"query_relations_G{graphDB.group_number}_{graphDB.num_graphs}_{graphDB.query_mode}.html"
)

baseline_reducer.print_ranking()

reduced_graphDB = baseline_reducer.reduce()

engine = QueryEngine(reduced_graphDB.database_file, graphDB.log_file)
query_answers = engine.run()

baseline_reducer = BaselineReducer(graphDB=reduced_graphDB)
graph_scores = baseline_reducer.calculate_scores(query_answers)
baseline_reducer.print_ranking()

