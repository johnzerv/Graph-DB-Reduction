class BaselineReducer:
    """
    A simple scoring system to rank graphs based on query results."""
    def __init__(self, num_graphs):
        self.num_graphs = num_graphs
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