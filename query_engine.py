import re

from graph import Graph

class QueryEngine:
    def __init__(self, db_filepath, log_filepath):
        """Load graph and query data from the supplied files"""

        print(f"Loading Database from {db_filepath}...")
        self.graphs = self._parse_database(db_filepath)
        
        print(f"Loading Queries from {log_filepath}...")
        self.queries = self._parse_queries(log_filepath)

    def _parse_database(self, filepath):
        """Read graph lines and convert each graph to a set of triples"""
        graphs = []
        with open(filepath, 'r') as f:
            for line in f:
                raw_triples = re.findall(r'<(.*?)>', line)
                graph_triples = set()
                for t in raw_triples:
                    parts = t.split(',')
                    if len(parts) == 3:
                        graph_triples.add((parts[0].strip(), parts[1].strip(), parts[2].strip()))
                graphs.append(graph_triples)
        return graphs

    def _parse_queries(self, filepath):
        """Read query-log lines and split each query into paths"""
        
        queries = []
        with open(filepath, 'r') as f:
            for line in f:
                if line.strip():
                    paths = [path.strip() for path in line.strip().split(',')]
                    queries.append(paths)
        return queries

    def _satisfies_path(self, graph_triples, path):
        """Check whether a graph contains every triple required by a query path"""

        parts = path.split('.')
        
        # Edge case: Path is just a single node ID (e.g., 5)
        if len(parts) == 1:
            single_node = parts[0]
            for (source, _, dest) in graph_triples:
                if (source == single_node and source.isdigit()) or \
                   (dest == single_node and dest.isdigit()) or \
                   single_node in Graph.EDGE_LABELS or \
                   type(single_node) == str:
                    return True
            return False

        # Process the path in steps of 2 (Source Node + Edge/Attribute Label)
        for i in range(0, len(parts) - 1, 2):
            source = parts[i]
            predicate = parts[i+1]
            
            if i + 2 < len(parts):
                destination = parts[i+2]
                if (source, predicate, destination) not in graph_triples:
                    return False
            else:
                found = False
                for (gs, gp, _) in graph_triples:
                    if gs == source and gp == predicate:
                        found = True
                        break
                if not found:
                    return False
                    
        return True

    def _evaluate_query_on_graph(self, graph_triples, query_paths):
        """Evaluate all paths in a query against one graph. Returns FULL, PARTIAL, or NONE based on the matches."""

        paths_satisfied = sum(
            1 for path in query_paths if self._satisfies_path(graph_triples, path)
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
        match_results = {}
        
        for q_idx, query in enumerate(self.queries):
            full_matches = []
            partial_matches = []
            
            for g_idx, graph in enumerate(self.graphs):
                result = self._evaluate_query_on_graph(graph, query)
                
                if result == 'FULL':
                    full_matches.append(g_idx)
                    match_results[(q_idx, g_idx)] = 'FULL'
                elif result == 'PARTIAL':
                    partial_matches.append(g_idx)
                    match_results[(q_idx, g_idx)] = 'PARTIAL'
                    
            print(f"Query {q_idx} | {query}")
            print(f"  -> FULL Matches: Graphs {full_matches}")
            print(f"  -> PARTIAL Matches: Graphs {partial_matches}\n")
            
        return match_results