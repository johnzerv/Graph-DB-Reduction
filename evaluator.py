class Evaluator:
    """Evaluate recall for query answers when the reduced database keeps only correct answers"""

    def _as_set(self, answers):
        if answers is None:
            return set()
        return set(answers)

    def _answerable_queries(self, answers_original_graph_by_query):
        """Queries with at least one answer in the original database.
        Queries with no answers have nothing to lose so they are left out of recall."""
        return sorted(q for q, answers in answers_original_graph_by_query.items() if answers)

    def recall_per_query(self, answers_original_graph, answers_reduced_graph):
        """Return recall for one query as |A_q(D')| / |A_q(D)|"""
        answers_original_graph = self._as_set(answers_original_graph)
        answers_reduced_graph = self._as_set(answers_reduced_graph)

        return len(answers_reduced_graph) / len(answers_original_graph)

    def macro_recall(self, answers_original_graph_by_query, answers_reduced_graph_by_query):
        """Average recall across queries that have answers giving each query the same weight"""
        queries = self._answerable_queries(answers_original_graph_by_query)
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

        for query in self._answerable_queries(answers_original_graph_by_query):
            original = self._as_set(answers_original_graph_by_query.get(query, []))
            reduced = self._as_set(answers_reduced_graph_by_query.get(query, []))

            total_original_answers += len(original)
            total_reducted_answers += len(reduced)

        if total_original_answers == 0:
            return 0.0

        return total_reducted_answers / total_original_answers

    def evaluate(self, answers_original_graph_by_query, answers_reduced_graph_by_query):
        """Return per-query recall, macro recall, micro recall and the number of skipped queries (no answers)"""
        queries = self._answerable_queries(answers_original_graph_by_query)
        per_query = {}

        for query in queries:
            original = self._as_set(answers_original_graph_by_query.get(query, []))
            reduced = self._as_set(answers_reduced_graph_by_query.get(query, []))
            per_query[query] = self.recall_per_query(original, reduced)

        return {
            "per_query": per_query,
            "macro": self.macro_recall(answers_original_graph_by_query, answers_reduced_graph_by_query),
            "micro": self.micro_recall(answers_original_graph_by_query, answers_reduced_graph_by_query),
            "skipped": len(answers_original_graph_by_query) - len(queries),
        }
