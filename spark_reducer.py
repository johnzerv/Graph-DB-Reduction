from abc import ABC, abstractmethod
from pyspark.sql import functions as F

class SparkReducer(ABC):
    def __init__(self, spark, num_graphs, retain_percentage=0.7):
        self.spark = spark
        self.num_graphs = num_graphs
        self.retain_percentage = retain_percentage
        self.scores_df = None

    @abstractmethod
    def calculate_scores(self, matches_df):
        """Scoring Strategy - must set self.scores_df"""
        pass

    def reduce(self):
        """Applies budget and returns a DataFrame of kept graph IDs."""
        if self.scores_df is None:
            raise ValueError("Scores have not been calculated yet.")
            
        num_graphs_to_keep = max(1, int(self.num_graphs * self.retain_percentage))
        
        kept_df = (self.scores_df
                   .orderBy(F.desc("score"), F.asc("gid"))
                   .limit(num_graphs_to_keep)
                   .select("gid")
                   .cache())
        return kept_df

class SparkBaselineReducer(SparkReducer):
    def calculate_scores(self, matches_df):
        weighted = matches_df.withColumn("w", F.when(F.col("type") == "FULL", 2.0).otherwise(1.0))
        per_graph = weighted.groupBy("gid").agg(F.sum("w").alias("score"))
        
        all_graphs = self.spark.range(self.num_graphs).withColumnRenamed("id", "gid")
        self.scores_df = (all_graphs.join(per_graph, "gid", "left")
                          .fillna(0.0, ["score"])
                          .withColumn("score", F.round("score", 9)))
        return self.scores_df

class SparkRarityReducer(SparkReducer):
    def __init__(self, spark, num_graphs, retain_percentage=0.7, alpha=0.5):
        super().__init__(spark, num_graphs, retain_percentage)
        self.alpha = alpha

    def calculate_scores(self, matches_df):
        counts = matches_df.groupBy("qid", "type").agg(F.count("*").alias("n"))
        weighted = matches_df.join(counts, ["qid", "type"]).withColumn(
            "w", F.when(F.col("type") == "FULL", 1.0 / F.col("n"))
                  .otherwise(F.lit(self.alpha) / F.col("n"))
        )
        
        per_graph = weighted.groupBy("gid").agg(F.sum("w").alias("score"))
        
        all_graphs = self.spark.range(self.num_graphs).withColumnRenamed("id", "gid")
        self.scores_df = (all_graphs.join(per_graph, "gid", "left")
                          .fillna(0.0, ["score"])
                          .withColumn("score", F.round("score", 9)))
        return self.scores_df