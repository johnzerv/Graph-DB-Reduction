from pyspark.sql import functions as F

class SparkRetentionEvaluator:
    def evaluate(self, matches_df, kept_df, num_queries):
        """Return macro retention, micro retention, and skipped queries for FULL and PARTIAL matches."""
        kept_flag = kept_df.withColumn("kept", F.lit(1))
        
        # Join matches with the kept indicator
        per_query = (matches_df.join(kept_flag, "gid", "left").fillna(0, ["kept"])
                     .groupBy("type", "qid")
                     .agg(F.count("*").alias("orig"), F.sum("kept").alias("red")))
                     
        summary = per_query.groupBy("type").agg(
            F.avg(F.col("red") / F.col("orig")).alias("macro"),
            (F.sum("red") / F.sum("orig")).alias("micro"),
            F.count("*").alias("answerable")
        ).collect()

        result = {t: {"macro": 0.0, "micro": 0.0, "skipped": num_queries} for t in ("FULL", "PARTIAL")}
        for row in summary:
            result[row.type] = {
                "macro": row.macro, 
                "micro": row.micro, 
                "skipped": num_queries - row.answerable
            }
        return result