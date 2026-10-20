class Evaluator:
    """Evaluate recall for query answers when the reduced database keeps only correct answers"""

    def _as_set(self, answers):
        if answers is None:
            return set()
        return set(answers)

    def recall_per_query(self, answers_original_graph, answers_reduced_graph):
        """Return recall for one query as |A_q(D')| / |A_q(D)|"""
        answers_original_graph = self._as_set(answers_original_graph)
        answers_reduced_graph = self._as_set(answers_reduced_graph)

        if not answers_original_graph:
            return 1.0 if not answers_reduced_graph else 0.0

        return len(answers_reduced_graph) / len(answers_original_graph)

    def macro_recall(self, answers_original_graph_by_query, answers_reduced_graph_by_query):
        """Average recall across queries, giving each query the same weight"""
        queries = sorted(set(answers_original_graph_by_query) | set(answers_reduced_graph_by_query))
        if not queries:
            return 0.0

        recalls = []
        for query in queries:
            original = self._as_set(answers_original_graph_by_query.get(query, []))
            reduced = self._as_set(answers_reduced_graph_by_query.get(query, []))
            recalls.append(self.recall_per_query(original, reduced))

        return sum(recalls) / len(queries)

    def micro_recall(self, answers_original_graph_by_query, answers_reduced_graph_by_query):
        """Aggregate all items together and compute one global recall value"""
        total_original_answers = 0
        total_reducted_answers = 0

        for query in sorted(set(answers_original_graph_by_query) | set(answers_reduced_graph_by_query)):
            original = self._as_set(answers_original_graph_by_query.get(query, []))
            reduced = self._as_set(answers_reduced_graph_by_query.get(query, []))

            total_original_answers += len(original)
            total_reducted_answers += len(reduced)

        if total_original_answers == 0:
            return 1.0 if total_reducted_answers == 0 else 0.0

        return total_reducted_answers / total_original_answers

    def evaluate(self, answers_original_graph_by_query, answers_reduced_graph_by_query):
        """Return per-query recall, macro recall and micro recall"""
        queries = sorted(set(answers_original_graph_by_query) | set(answers_reduced_graph_by_query))
        per_query = {}

        for query in queries:
            original = self._as_set(answers_original_graph_by_query.get(query, []))
            reduced = self._as_set(answers_reduced_graph_by_query.get(query, []))
            per_query[query] = self.recall_per_query(original, reduced)

        return {
            "per_query": per_query,
            "macro": self.macro_recall(answers_original_graph_by_query, answers_reduced_graph_by_query),
            "micro": self.micro_recall(answers_original_graph_by_query, answers_reduced_graph_by_query),
        }
