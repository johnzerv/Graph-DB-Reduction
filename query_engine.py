import argparse
import re

from visualizers import visualize_query_graph_relations
from graph import Graph

def parse_database(filepath):
    """Reads the database file and converts each graph into a Set of Triples for O(1) lookups."""
    graphs = []
    with open(filepath, 'r') as f:
        for line in f:
            # Extract contents inside < >
            raw_triples = re.findall(r'<(.*?)>', line)
            
            # Convert to a set of tuples: { ('1', 'knows', '2'), ('2', 'city', '"Utrecht"') }
            graph_triples = set()
            for t in raw_triples:
                parts = t.split(',')
                if len(parts) == 3:
                    graph_triples.add((parts[0].strip(), parts[1].strip(), parts[2].strip()))
            
            graphs.append(graph_triples)
    return graphs

def parse_queries(filepath):
    """Reads the query log. Returns a list of queries, where each query is a list of paths."""
    queries = []
    with open(filepath, 'r') as f:
        for line in f:
            if line.strip():
                # Split paths by comma
                paths = [path.strip() for path in line.strip().split(',')]
                queries.append(paths)
    return queries

def satisfies_path(graph_triples, path):
    parts = path.split('.')
    
    # Edge case: Path is just a single node ID (e.g., 5)
    if len(parts) == 1:
        single_node = parts[0]
        for (source, _, dest) in graph_triples:
            if (source == single_node and source.isdigit()) or (dest == single_node and dest.isdigit()) or single_node in Graph.EDGE_LABELS or type(single_node) == str:
                return True
        return False

    # Process the path in steps of 2 (Source Node + Edge/Attribute Label)
    # Example: '5.married.7.city."Amsterdam"'
    for i in range(0, len(parts) - 1, 2):
        source = parts[i]       # Source Node
        predicate = parts[i+1]     # Edge Label or Attribute Name
        
        # Check if we parse an edge or an attribute based on the next part
        if i + 2 < len(parts):
            destination = parts[i+2]
            
            # The exact triple MUST exist in the graph
            if (source, predicate, destination) not in graph_triples:
                return False
        else:
            # The path ends prematurely on a label (e.g., "5.married")
            # We just need to check if ANY triple starts with <5, married, ...>
            found = False
            for (gs, gp, _) in graph_triples:
                if gs == source and gp == predicate:
                    found = True
                    break
            
            if not found:
                return False
                
    return True

def evaluate_query_on_graph(graph_triples, query_paths):
    """
    Evaluates a full query (multiple paths) against a single graph.
    Returns: 'FULL', 'PARTIAL', or 'NONE'
    """
    paths_satisfied = 0
    total_paths = len(query_paths)
    
    for path in query_paths:
        if satisfies_path(graph_triples, path):
            paths_satisfied += 1
            
    if paths_satisfied == total_paths:
        return 'FULL'
    elif paths_satisfied > 0:
        return 'PARTIAL'
    else:
        return 'NONE'

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Evaluate the query log against a generated graph database."
    )
    parser.add_argument(
        "-n",
        "--num-graphs",
        "--graphs",
        type=int,
        default=10,
        help="number of graphs in the database (default: 10)",
    )
    parser.add_argument(
        "--num-queries",
        "-q",
        type=int,
        default=20,
        help="number of queries in the query log (default: 20)",
    )
    parser.add_argument(
        "--query-mode",
        choices=["uniform", "skewed"],
        default="skewed",
        help="query generation mode: 'uniform' or 'skewed' (default: skewed)",
    )
    parser.add_argument(
        "--group-number",
        default="13",
        help="group number used in database and query filenames (default: 13)",
    )
    args = parser.parse_args()
    if args.num_graphs < 1:
        parser.error("--num-graphs must be at least 1")
    if args.num_queries < 1:
        parser.error("--num-queries must be at least 1")

    graph_config = Graph(
        num_graphs=args.num_graphs,
        num_queries=args.num_queries,
        group_number=args.group_number,
        query_mode=args.query_mode
    )

    print(f"Loading Database from {graph_config.database_file}...")
    graphs = parse_database(graph_config.database_file)
    
    print(f"Loading Queries from {graph_config.log_file}...")
    queries = parse_queries(graph_config.log_file)
    
    print("\n--- RUNNING QUERY ENGINE ---\n")
    
    graph_scores = {i: 0 for i in range(len(graphs))}
    
    # Format: {(q_idx, g_idx): 'FULL' or 'PARTIAL'}
    match_results = {}
    
    for q_idx, query in enumerate(queries):
        full_matches = []
        partial_matches = []
        
        for g_idx, graph in enumerate(graphs):
            result = evaluate_query_on_graph(graph, query)
            
            if result == 'FULL':
                full_matches.append(g_idx)
                graph_scores[g_idx] += 2
                match_results[(q_idx, g_idx)] = 'FULL'       # Record Full Match
                
            elif result == 'PARTIAL':
                partial_matches.append(g_idx)
                graph_scores[g_idx] += 1
                match_results[(q_idx, g_idx)] = 'PARTIAL'    # Record Partial Match
                
        print(f"Query {q_idx} | {query}")
        print(f"  -> FULL Matches: Graphs {full_matches}")
        print(f"  -> PARTIAL Matches: Graphs {partial_matches}\n")
        
    print("--- PRELIMINARY GRAPH IMPORTANCE SCORES ---")
    sorted_graphs = sorted(graph_scores.items(), key=lambda item: item[1], reverse=True)
    for rank in range(min(5, len(sorted_graphs))):
        g_idx, score = sorted_graphs[rank]
        print(f"  Rank {rank+1}: Graph {g_idx} (Score: {score})")

    visualize_query_graph_relations(
        queries=queries, 
        num_graphs=len(graphs), 
        match_results=match_results, 
        graph_scores=graph_scores,
        output_file=f"query_relations_G{graph_config.group_number}_{graph_config.num_graphs}_{graph_config.query_mode}.html"
    )