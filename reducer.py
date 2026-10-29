from collections import Counter
from abc import ABC, abstractmethod
from graph import GraphDB

class Reducer(ABC):
    def __init__(self, graphDB: GraphDB, retain_percentage=0.7):
        self.graphDB = graphDB
        self.num_graphs = graphDB.num_graphs
        self.retain_percentage = retain_percentage
        
    @abstractmethod
    def reduce(self, **kwargs):
        pass

class ScoreReducer(Reducer, ABC):
    """ A generic base class for all score-based reducers """
    name = "ScoreReducer"

    def __init__(self, graphDB: GraphDB, **kwargs):
        super().__init__(graphDB, **kwargs)

        # Initialize all graphs with a score of 0
        self.graph_scores = {i: 0 for i in range(self.num_graphs)}

    @abstractmethod
    def calculate_scores(self, match_results):
        """ Scoring Strategy """
        pass

    def print_ranking(self):
        print(f"--- {self.name} RANKING LIST ---")
        sorted_graphs = sorted(self.graph_scores.items(), key=lambda item: item[1], reverse=True)
        
        for rank, (g_idx, score) in enumerate(sorted_graphs):
            print(f"  Rank {rank+1}: Graph {g_idx} (Score: {score:.4f})")
            
        return sorted_graphs

    def reduce(self, **kwargs):
        """ Removes lowest ranking graphs until the retain_percentage target is met """
        num_graphs_to_keep = max(1, int(self.num_graphs * self.retain_percentage))
        
        sorted_graphs = sorted(self.graph_scores.items(), key=lambda item: item[1], reverse=True)
        
        retained_graphs = sorted_graphs[:num_graphs_to_keep]
        removed_graphs = sorted_graphs[num_graphs_to_keep:]
        
        retained_graph_indices = [g_idx for g_idx, _ in retained_graphs]
        removed_graph_indices = [g_idx for g_idx, _ in removed_graphs]
        
        self.graph_scores = {g_idx: score for g_idx, score in retained_graphs}
        self.num_graphs = len(self.graph_scores)
        
        print(f"\n--- REDUCTION SUMMARY ({self.name}) ---")
        print(f"Target Keep Percentage: {self.retain_percentage*100}%")
        print(f"Retained {len(retained_graph_indices)} graphs: {retained_graph_indices}")
        print(f"Removed {len(removed_graph_indices)} lowest-scoring graphs: {removed_graph_indices}")
        
        return self.graphDB.reduce(retained_graph_indices)


class BaselineScoreReducer(ScoreReducer):
    """
    A simple scoring system to rank graphs based on query results.
    Each graph gets 2 points for every FULL match and 1 point for every PARTIAL match.
    """
    name = "BASELINE"

    def calculate_scores(self, match_results):
        """Calculates scores: 2 points for FULL matches, 1 point for PARTIAL matches."""
        for (_, g_idx), result in match_results.items():
            if result == 'FULL':
                self.graph_scores[g_idx] += 2
            elif result == 'PARTIAL':
                self.graph_scores[g_idx] += 1
                
        return self.graph_scores


class RarityReducer(ScoreReducer):
    """
    Scores graphs by how rare their answers are. Each query gives away 1 point, 
    split equally among the graphs that answer it. Full matches receive the
    complete share, while partial matches receive that share multiplied by
    alpha, which defaults to 0.5.
    """
    name = "RARITY"

    def __init__(self, graphDB: GraphDB, alpha=0.5, **kwargs):
        super().__init__(graphDB, **kwargs)
        self.alpha = alpha

    def calculate_scores(self, match_results):
        """Calculates scores based on the rarity of the match results."""
        # Number of graphs that answer each query fully / partially
        full_count = Counter(q_idx for (q_idx, _), result in match_results.items() if result == 'FULL')
        partial_count = Counter(q_idx for (q_idx, _), result in match_results.items() if result == 'PARTIAL')

        for (q_idx, g_idx), result in match_results.items():
            if result == 'FULL' and full_count[q_idx] > 0:
                self.graph_scores[g_idx] += 1 / full_count[q_idx]
            elif result == 'PARTIAL' and partial_count[q_idx] > 0:
                self.graph_scores[g_idx] += self.alpha / partial_count[q_idx]

        return self.graph_scores