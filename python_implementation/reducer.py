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
    """ 
    A generic base class for all score-based reducers.
    A score-based reducer calculate a scor e for each graph based on the query results,
    ranks them, and removes the lowest scoring graphs until the target retain_percentage is met.
    """
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
        """ The method for actual reduction of the graph database based on the calculated scores. """
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
    A simple scoring system to rank graphs based their participation in query results.
    Each graph gets 2 points for every FULL match and 1 point for every PARTIAL match.
    """
    def calculate_scores(self, match_results):
        """Calculates scores: 2 points for FULL matches, 1 point for PARTIAL matches."""
        for (_, g_idx), result in match_results.items():
            if result == 'FULL':
                self.graph_scores[g_idx] += 2
            elif result == 'PARTIAL':
                self.graph_scores[g_idx] += 1
                
        return self.graph_scores


class RarityScoreReducer(ScoreReducer):
    """
    Scores graphs by how rare their answers are. Each query gives away 1 point, 
    split equally among the graphs that answer it. Full matches receive the
    complete share, while partial matches receive that share multiplied by
    alpha, which defaults to 0.5.
    """

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

class OverlapParticipationRatioReducer(ScoreReducer):
    """
    A scoring system that ranks graphs based on two factors: (1) their overlap with 
    other graphs in terms of query answers, and (2) their participation in the overall query set.

    Intuition: A graph that answers many queries but whose answers are largely covered by other
    graphs is less valuable than a graph that answers queries with unique answers.

    Graphs with no FULL or PARTIAL matches are removed first. It then iteratively removes the
    graph that maximizes the ratio between its overlap with other graphs and its participation
    in the query set, using weighted scores to account for both FULL and PARTIAL matches.
    """
    def __init__(self, graphDB: GraphDB, **kwargs):
        super().__init__(graphDB, **kwargs)
        self.name = "Overlap Participation Ratio Reducer"

    def calculate_scores(self, full_matches_by_graph, partial_matches_by_graph):
        """
        Calculates scores by simulating the full iterative removal process
        based on overlap-to-participation ratios.
        """
        FULL_WEIGHT = 2
        PARTIAL_WEIGHT = 1

        remaining = {
            i: {
                "FULL": set(full_matches_by_graph.get(i, [])),
                "PARTIAL": set(partial_matches_by_graph.get(i, [])),
            }
            for i in range(self.num_graphs)
        }

        removed = []

        # Score = position in the removal order. First removed gets 0 (less important graph),
        # last removed (most important graph) gets the highest score.
        removal_rank = 0

        # Remove graphs with empty query answer sets first
        for i in list(remaining.keys()):
            if not remaining[i]["FULL"] and not remaining[i]["PARTIAL"]:
                del remaining[i]
                removed.append(i)
                self.graph_scores[i] = float(removal_rank)
                removal_rank += 1

        # Iteratively calculate weighted overlap-participation ratios.
        while remaining:
            overlap_scores = {}

            for i, matches_i in remaining.items():
                overlap = 0

                for j, matches_j in remaining.items():
                    if i == j:
                        continue

                    overlap += FULL_WEIGHT * len(
                        matches_i["FULL"] & matches_j["FULL"]
                    )

                    overlap += FULL_WEIGHT * (
                        len(matches_i["FULL"] & matches_j["PARTIAL"])
                        + len(matches_i["PARTIAL"] & matches_j["FULL"])
                    )

                    overlap += PARTIAL_WEIGHT * len(
                        matches_i["PARTIAL"] & matches_j["PARTIAL"]
                    )

                overlap_scores[i] = overlap

            query_counts = {
                i: (
                    FULL_WEIGHT * len(matches["FULL"])
                    + PARTIAL_WEIGHT * len(matches["PARTIAL"])
                )
                for i, matches in remaining.items()
            }

            overlap_ratios = {
                i: overlap_scores[i] / query_counts[i]
                for i in remaining
            }

            max_ratio = max(overlap_ratios.values())

            candidates = [
                i for i, ratio in overlap_ratios.items()
                if ratio == max_ratio
            ]

            # Tie-break: lower participation
            graph_to_remove = min(
                candidates,
                key=lambda i: (query_counts[i], i)
            )

            del remaining[graph_to_remove]
            removed.append(graph_to_remove)

            self.graph_scores[graph_to_remove] = float(removal_rank)
            removal_rank += 1

        return self.graph_scores