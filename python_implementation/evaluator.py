class RetentionEvaluator:
    """Evaluate answer retention: the fraction of a query's answers on the original
    database D that are still returned on the reduced database D'.
    """
    def _as_set(self, answers):
        if answers is None:
            return set()
        return set(answers)

    def _answerable_queries(self, answers_original_db_by_query):
        """Queries with at least one answer on the original database.
        Queries with no answers have nothing to lose, so they are left out."""
        return sorted(q for q, answers in answers_original_db_by_query.items() if answers)

    def retention_per_query(self, answers_original_db, answers_reduced_db):
        """Return retention for one query as |A_q(D')| / |A_q(D)|"""
        answers_original_db = self._as_set(answers_original_db)
        answers_reduced_db = self._as_set(answers_reduced_db)

        return len(answers_reduced_db) / len(answers_original_db)

    def macro_retention(self, answers_original_db_by_query, answers_reduced_db_by_query):
        """Average retention across answerable queries, giving each query the same weight"""
        queries = self._answerable_queries(answers_original_db_by_query)
        if not queries:
            return 0.0

        retentions = []
        for query in queries:
            original = self._as_set(answers_original_db_by_query.get(query, []))
            reduced = self._as_set(answers_reduced_db_by_query.get(query, []))
            retentions.append(self.retention_per_query(original, reduced))

        return sum(retentions) / len(queries)

    def micro_retention(self, answers_original_db_by_query, answers_reduced_db_by_query):
        """Pool all answers together and compute one global retention value"""
        total_original_answers = 0
        total_reduced_answers = 0

        for query in self._answerable_queries(answers_original_db_by_query):
            original = self._as_set(answers_original_db_by_query.get(query, []))
            reduced = self._as_set(answers_reduced_db_by_query.get(query, []))

            total_original_answers += len(original)
            total_reduced_answers += len(reduced)

        if total_original_answers == 0:
            return 0.0

        return total_reduced_answers / total_original_answers

    def evaluate(self, answers_original_db_by_query, answers_reduced_db_by_query):
        """Return per-query retention, macro retention, micro retention
        and the number of skipped queries (no answers on the original database)"""
        queries = self._answerable_queries(answers_original_db_by_query)
        per_query = {}

        for query in queries:
            original = self._as_set(answers_original_db_by_query.get(query, []))
            reduced = self._as_set(answers_reduced_db_by_query.get(query, []))
            per_query[query] = self.retention_per_query(original, reduced)

        return {
            "per_query": per_query,
            "macro": self.macro_retention(answers_original_db_by_query, answers_reduced_db_by_query),
            "micro": self.micro_retention(answers_original_db_by_query, answers_reduced_db_by_query),
            "skipped": len(answers_original_db_by_query) - len(queries),
        }