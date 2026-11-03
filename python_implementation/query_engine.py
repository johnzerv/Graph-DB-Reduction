from pathlib import Path

# Assuming the classes from the first file are imported. 
# Adjust the import statement to match your actual filename (e.g., from database import Graph, GraphDB)
from graph import Graph, GraphDB

class QueryEngine:
    def __init__(self, db_or_filepath, log_filepath=None):
        """Load graph and query data utilizing the GraphDB class"""
        if isinstance(db_or_filepath, GraphDB):
            self.db = db_or_filepath
        else:
            print(f"Loading Database from {db_or_filepath}...")
            self.db = GraphDB(database_file=Path(db_or_filepath))
            
        self.graphs = self.db.graphs
        
        log_file = log_filepath or self.db.log_file
        self.queries = self._parse_queries(log_file)

    def _parse_queries(self, filepath):
        """Read query-log lines and split each query into paths"""

        queries = []
        with open(filepath, 'r') as f:
            for line in f:
                if line.strip():
                    paths = [path.strip() for path in line.strip().split(',')]
                    queries.append(paths)
        return queries

    def _satisfies_path(self, graph: Graph, path: str):
        """Check whether a Graph object satisfies every step required by a query path"""
        parts = path.split('.')
        
        # Edge case: Path is just a single entity (node ID, edge label, or attribute value)
        if len(parts) == 1:
            source = parts[0]
            
            # Check if it's an node
            if source.isdigit() and int(source) in graph.nodes:
                return True
            
            # Check if it's an edge label
            if any(label == source for _, label, _ in graph.edges):
                return True
                
            # Check if it's an attribute name or value
            if any(attr == source or val == source for _, attr, val in graph.attributes):
                return True
                
            return False

        # Process the path in steps of 2 (Source Node + Edge/Attribute Label)
        for i in range(0, len(parts) - 1, 2):
            source = parts[i]
            predicate = parts[i+1]
            
            if not source.isdigit():
                return False
                
            src = int(source)
            
            if i + 2 < len(parts):
                destination = parts[i+2]
                match_found = False
                
                # Check against edges (where destination is another integer node)
                if destination.isdigit():
                    if (src, predicate, int(destination)) in graph.edges:
                        match_found = True
                
                # Check against attributes (where destination is a string value --> attribute value)
                if not match_found and (src, predicate, destination) in graph.attributes:
                    match_found = True
                    
                if not match_found:
                    return False
            else:
                # Path ends with a predicate, just verify the source has this predicate as an edge or attribute
                found = any(s == src and p == predicate for s, p, _ in graph.edges)
                if not found:
                    found = any(s == src and p == predicate for s, p, _ in graph.attributes)
                    
                if not found:
                    return False
                    
        return True

    def _satisfies_query(self, graph: Graph, query_paths):
        """Evaluate all paths in a query against one graph. Returns FULL, PARTIAL, or NONE based on the matches."""
        paths_satisfied = sum(
            1 for path in query_paths if self._satisfies_path(graph, path)
        )
        total_paths = len(query_paths)
                
        if paths_satisfied == total_paths:
            return 'FULL'
        elif paths_satisfied > 0:
            return 'PARTIAL'
        else:
            return 'NONE'

    def run(self):
        """Evaluate every query against every graph and collect non-empty matches

        Returns a mapping from query and graph index pairs to FULL or PARTIAL results
        """
        print("\n--- RUNNING QUERY ENGINE ---\n")

        # All dicts hold the same information, structured differently (from queries to graphs)
        graph_match_results = {}
        query_full_matches = {}
        query_partial_matches = {}

        # From graphs to queries
        graph_full_matches = {g_idx: [] for g_idx in range(len(self.graphs))}
        graph_partial_matches = {g_idx: [] for g_idx in range(len(self.graphs))}

        for q_idx, query in enumerate(self.queries):
            qfull_matches = []
            qpartial_matches = []
            
            for g_idx, graph in enumerate(self.graphs):
                result = self._satisfies_query(graph, query)
                
                if result == 'FULL':
                    qfull_matches.append(g_idx)
                    graph_full_matches[g_idx].append(q_idx)
                    graph_match_results[(q_idx, g_idx)] = 'FULL'
                elif result == 'PARTIAL':
                    qpartial_matches.append(g_idx)
                    graph_partial_matches[g_idx].append(q_idx)
                    graph_match_results[(q_idx, g_idx)] = 'PARTIAL'

            query_full_matches[q_idx] = qfull_matches
            query_partial_matches[q_idx] = qpartial_matches
                    
            # print(f"Query {q_idx} | {query}")
            # print(f"  -> FULL Matches: Graphs {qfull_matches}")
            # print(f"  -> PARTIAL Matches: Graphs {qpartial_matches}\n")
            
        return graph_match_results, query_full_matches, query_partial_matches, graph_full_matches, graph_partial_matches