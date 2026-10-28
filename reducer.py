from collections import Counter

from graph import GraphDB

class Reducer:
    def __init__(self, graphDB: GraphDB, retain_percentage=0.7):
        self.graphDB = graphDB
        self.num_graphs = graphDB.num_graphs
        self.retain_percentage = retain_percentage
        
    def reduce(self, **kwargs):
        pass

class BaselineReducer(Reducer):
    """
    A simple scoring system to rank graphs based on query results.
    """
    name = "BASELINE"

    def __init__(self, graphDB: GraphDB, **kwargs):
        super().__init__(graphDB, **kwargs)

        # Initialize all graphs with a score of 0
        self.graph_scores = {i: 0 for i in range(self.num_graphs)}

    def calculate_scores(self, match_results):
        """Calculates scores based on match results (2 points for FULL matches, 1 point for PARTIAL matches)"""
        for (_, g_idx), result in match_results.items():
            if result == 'FULL':
                self.graph_scores[g_idx] += 2
            elif result == 'PARTIAL':
                self.graph_scores[g_idx] += 1
                
        return self.graph_scores

    def print_ranking(self):
        print(f"--- {self.name} RANKING LIST ---")
        sorted_graphs = sorted(self.graph_scores.items(), key=lambda item: item[1], reverse=True)
        
        for rank, (g_idx, score) in enumerate(sorted_graphs):
            print(f"  Rank {rank+1}: Graph {g_idx} (Score: {score})")
            
        return sorted_graphs

    def reduce(self, **kwargs):
        """
        Removes lowest ranking graphs until the retain_percentage target is met.
        Returns the lists of retained and removed graph indices.
        """
        num_graphs_to_keep = max(1, int(self.num_graphs * self.retain_percentage))
        
        sorted_graphs = sorted(self.graph_scores.items(), key=lambda item: item[1], reverse=True)
        
        retained_graphs = sorted_graphs[:num_graphs_to_keep]
        removed_graphs = sorted_graphs[num_graphs_to_keep:]
        
        retained_graph_indices = [g_idx for g_idx, _ in retained_graphs]
        removed_graph_indices = [g_idx for g_idx, _ in removed_graphs]
        
        self.graph_scores = {g_idx: score for g_idx, score in retained_graphs}
        self.num_graphs = len(self.graph_scores)
        
        print(f"\n--- REDUCTION SUMMARY ---")
        print(f"Target Keep Percentage: {self.retain_percentage*100}%")
        print(f"Retained {len(retained_graph_indices)} graphs: {retained_graph_indices}")
        print(f"Removed {len(removed_graph_indices)} lowest-scoring graphs: {removed_graph_indices}")
        
        return self.graphDB.reduce(retained_graph_indices)


class RarityReducer(BaselineReducer):
    """
    Scores graphs by how rare their answers are. Each query gives away 1 point, split equally among the graphs that fully answer it
    """
    name = "RARITY"

    def __init__(self, graphDB: GraphDB, alpha=0.5, **kwargs):
        super().__init__(graphDB, **kwargs)
        self.alpha = alpha

    def calculate_scores(self, match_results):
        # Number of graphs that answer each query fully / partially
        full_count = Counter(q_idx for (q_idx, _), result in match_results.items() if result == 'FULL')
        partial_count = Counter(q_idx for (q_idx, _), result in match_results.items() if result == 'PARTIAL')

        for (q_idx, g_idx), result in match_results.items():
            if result == 'FULL':
                self.graph_scores[g_idx] += 1 / full_count[q_idx]
            elif result == 'PARTIAL':
                self.graph_scores[g_idx] += self.alpha / partial_count[q_idx]

        return self.graph_scores