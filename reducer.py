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
    other graphs in terms of query answers,and (2) their participation in the overall query set.

    Intuition: A graph that answers many queries but whose answers are largely covered by other
    graphs is less valuable than a graph that answers queries with unique answers.

    Removes graphs with no FULL or PARTIAL query matches first as the algorithm cannot provide overlap scores for these graphs.
    It then iteratively removes the graph whose maximizes the ratio between its overlap with other graphs and its participation
    in the query set, using weighted scores in order to take into account both FULL and PARTIAL matches.
    """
    def __init__(self, graphDB: GraphDB, **kwargs):
        super().__init__(graphDB, **kwargs)
        self.name = "Overlap Participation Ratio Reducer"

    def calculate_scores(self, full_matches_by_graph, partial_matches_by_graph):
        """
        Calculates scores/order of removal by simulating the iterative 
        removal process based on overlap-to-query ratios.
        """
        num_graphs_to_keep = max(1, int(self.num_graphs * self.retain_percentage))

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

        removal_step = self.num_graphs

        # Remove graphs with empty query answer sets
        for i in list(remaining.keys()):
            if len(remaining) <= num_graphs_to_keep:
                break

            if not remaining[i]["FULL"] and not remaining[i]["PARTIAL"]:
                del remaining[i]
                removed.append(i)
                self.graph_scores[i] = 0.0  # Lowest score
                removal_step -= 1

        # Iteratively calulate weighted overlap-participation ratios.
        while len(remaining) > num_graphs_to_keep:
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
                if query_counts[i] > 0
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
            
            # Assign score based on order of survival (later removal = higher score)
            self.graph_scores[graph_to_remove] = float(removal_step)
            removal_step -= 1

        # Assign highest scores to the final retained graphs so they stay at the top
        for i in remaining.keys():
            self.graph_scores[i] = float(removal_step)
            removal_step -= 1

        return self.graph_scores
    
class RecallGreedyReducer(Reducer):
    """
    Iteratively removes the graph whose removal maximizes
    the selected recall metric.

    metric: "macro" or "micro"
    match_type: "FULL" or "PARTIAL"
    """

    def __init__(
        self,
        graphDB: GraphDB,
        metric="macro",
        match_type="FULL",
        **kwargs
    ):
        super().__init__(graphDB, **kwargs)

        if metric not in {"macro", "micro"}:
            raise ValueError("metric must be 'macro' or 'micro'")

        if match_type not in {"FULL", "PARTIAL"}:
            raise ValueError("match_type must be 'FULL' or 'PARTIAL'")

        self.metric = metric
        self.match_type = match_type
        self.retained_graph_indices = list(range(self.num_graphs))

    def reduce(self, answers_original_by_query, **kwargs):
        from query_engine import QueryEngine
        from evaluator import Evaluator

        evaluator = Evaluator()

        num_graphs_to_keep = max(
            1, int(self.num_graphs * self.retain_percentage)
        )

        remaining = list(range(self.num_graphs))
        removed = []

        def calculate_recall(graph_indices):
            # Create the candidate reduced database.
            candidate_db = self.graphDB.reduce(graph_indices)

            # Run the original query log on this candidate.
            engine = QueryEngine(
                candidate_db,
                log_filepath=self.graphDB.log_file
            )

            _, full_matches, partial_matches = engine.run()

            # GraphDB assigns local indices when loading a reduced database.
            # Convert them back to the original database indices for recall.
            full_matches = {
                query: [graph_indices[i] for i in graph_ids]
                for query, graph_ids in full_matches.items()
            }
            partial_matches = {
                query: [graph_indices[i] for i in graph_ids]
                for query, graph_ids in partial_matches.items()
            }

            # Select the kind of answers we want to preserve.
            if self.match_type == "FULL":
                answers_reduced = full_matches
            else:
                answers_reduced = partial_matches

            result = evaluator.evaluate(
                answers_original_by_query,
                answers_reduced
            )

            return result[self.metric]

        current_recall = calculate_recall(remaining)

        print(
            f"Initial {self.match_type} {self.metric} recall: "
            f"{current_recall:.4f}"
        )

        while len(remaining) > num_graphs_to_keep:
            best_graph = None
            best_recall = float("-inf")

            # Try removing every remaining graph.
            for graph_idx in remaining:
                candidate_indices = [
                    i for i in remaining if i != graph_idx
                ]

                candidate_recall = calculate_recall(candidate_indices)

                # Choose the removal that preserves the most recall.
                if (
                    candidate_recall > best_recall
                    or (
                        candidate_recall == best_recall
                        and (
                            best_graph is None
                            or graph_idx < best_graph
                        )
                    )
                ):
                    best_graph = graph_idx
                    best_recall = candidate_recall

            remaining.remove(best_graph)
            removed.append(best_graph)
            current_recall = best_recall

            print(
                f"Removed graph {best_graph} | "
                f"{self.match_type} {self.metric} recall: "
                f"{current_recall:.4f} | "
                f"Remaining: {len(remaining)}"
            )

        print("\n--- RECALL GREEDY REDUCTION ---")
        print(f"Metric: {self.metric}")
        print(f"Match type: {self.match_type}")
        print(
            f"Target keep percentage: "
            f"{self.retain_percentage * 100:.1f}%"
        )
        print(f"Retained graphs: {remaining}")
        print(f"Removed graphs: {removed}")
        print(f"Final recall: {current_recall:.4f}")

        self.retained_graph_indices = remaining
        return self.graphDB.reduce(remaining)