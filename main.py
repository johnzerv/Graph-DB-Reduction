import argparse

from graph import Graph
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
graph_config = Graph(
    num_graphs=args.num_graphs,
    num_queries=args.num_queries,
    group_number=args.group_number,
    query_mode=args.query_mode
)

# Execute all queries to obtain the query answers
engine = QueryEngine(graph_config.database_file, graph_config.log_file)
match_results = engine.run()

# Use the baseline reducer (score system) to create a ranking of graphs based on the query results
baseline_reducer = BaselineReducer(num_graphs=len(engine.graphs))
graph_scores = baseline_reducer.calculate_scores(match_results)

# Visualize the query-graph relationships
visualize_query_graph_relations(
    queries=engine.queries, 
    num_graphs=len(engine.graphs), 
    match_results=match_results, 
    graph_scores=graph_scores,
    output_file=f"query_relations_G{graph_config.group_number}_{graph_config.num_graphs}_{graph_config.query_mode}.html"
)


baseline_reducer.print_ranking()

retained_graphs, removed_graphs = baseline_reducer.reduce()