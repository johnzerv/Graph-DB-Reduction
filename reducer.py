class Reducer:
    def __init__(self, num_graphs, retain_percentage=0.7):
        self.num_graphs = num_graphs
        self.retain_percentage = retain_percentage
        
    def reduce(self, **kwargs):
        pass

class BaselineReducer(Reducer):
    """
    A simple scoring system to rank graphs based on query results.
    """
    def __init__(self, num_graphs, **kwargs):
        super().__init__(num_graphs, **kwargs)
        # Initialize all graphs with a score of 0
        self.graph_scores = {i: 0 for i in range(num_graphs)}

    def calculate_scores(self, match_results):
        """Calculates scores based on match results (2 points for FULL matches, 1 point for PARTIAL matches)"""
        for (_, g_idx), result in match_results.items():
            if result == 'FULL':
                self.graph_scores[g_idx] += 2
            elif result == 'PARTIAL':
                self.graph_scores[g_idx] += 1
                
        return self.graph_scores

    def print_ranking(self):
        print("--- BASELINE RANKING LIST ---")
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
        
        return retained_graph_indices, removed_graph_indices