README - Data folder structure explanation.

We created synthetic graph databases consisting of randomly selected triples, as described in the project's description. We provide three graph databases of different sizes:

1. 100 graphs (Database13_1.txt)
2. 1,000 graphs (Database13_2.txt)
3. 10,000 graphs (Database13_3.txt)

Regarding the query logs, our idea was to create two types of query-answer distributions: uniform and skewed.

A uniform distribution means that all graphs contribute evenly to the query answers, with every graph answering at least one query. On the other hand, a skewed distribution means that some graphs are selected more frequently to contribute to query answers. Consequently, some graphs may not contribute to the query-answer set at all in skewed distribution.

For each graph database size, we provide two query logs, one for each distribution, with the following sizes:

1. 500 queries (QLog13_1_1.txt and QLog13_1_2.txt)
2. 5,000 queries (QLog13_2_1.txt and QLog13_2_2.txt)
3. 50,000 queries (QLog13_3_1.txt and QLog13_3_2.txt)

The last indicator (_1 or _2) corresponds to the query-answer distribution: uniform (_1) or skewed (_2).

The query generation process and the rationale behind this approach will be explained in the final report.