"""Graph database reduction with Apache Spark.

Steps:
    1. Load the graphs (one per line) and spread them over the workers
    2. Read the queries and give every worker a copy
    3. Each worker checks its graphs against all queries
    4. Give every graph a score (rarity or baseline)
    5. Keep the top B% of graphs
    6. Write the kept graphs to a file
    7. Measure how many query answers we kept (retention)
"""
import argparse
import os
import re
import sys
import time
from pathlib import Path


# Tell Spark which Python to use (avoids problems with spaces in the folder path)
os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
os.environ.setdefault("PYSPARK_DRIVER_PYTHON", sys.executable)
import pyspark 
os.environ.setdefault("SPARK_HOME", os.path.dirname(pyspark.__file__))

from pyspark.sql import SparkSession, Window, functions as F  

TRIPLE_RE = re.compile(r"<(.*?)>")


#Helpers that run on the workers

def parse_graph(line):
    """Turn one line of the database into sets we can look things up in.
    Third element is a number -> edge, otherwise -> attribute."""
    nodes, edges, attrs = set(), set(), set()
    for triple in TRIPLE_RE.findall(line):
        parts = [p.strip() for p in triple.split(",")]
        if len(parts) != 3:
            continue
        src, label, obj = parts
        src = int(src)
        nodes.add(src)
        if obj.isdigit():
            edges.add((src, label, int(obj)))
            nodes.add(int(obj))
        else:
            attrs.add((src, label, obj))
    return {
        "nodes": nodes,
        "edges": edges,
        "attrs": attrs,
        "edge_src_label": {(s, l) for s, l, _ in edges},
        "attr_src_name": {(s, n) for s, n, _ in attrs},
        "edge_labels": {l for _, l, _ in edges},
        "attr_names_values": {n for _, n, _ in attrs} | {v for _, _, v in attrs},
    }


def satisfies_path(g, path):
    """True if the graph contains this path"""
    parts = path.split(".")

    # Path with one element: just check it exists somewhere in the graph
    if len(parts) == 1:
        x = parts[0]
        return (x.isdigit() and int(x) in g["nodes"]) or x in g["edge_labels"] or x in g["attr_names_values"]

    # Walk the path two steps at a time: node -> label -> next node/value
    for i in range(0, len(parts) - 1, 2):
        source, predicate = parts[i], parts[i + 1]
        if not source.isdigit():
            return False
        src = int(source)
        if i + 2 < len(parts):
            # The next element must be reachable: an edge to a node or an attribute value
            dest = parts[i + 2]
            if not ((dest.isdigit() and (src, predicate, int(dest)) in g["edges"])
                    or (src, predicate, dest) in g["attrs"]):
                return False
        else:
            # Path ends with a label: the node just needs an edge or attribute with that name
            if (src, predicate) not in g["edge_src_label"] and (src, predicate) not in g["attr_src_name"]:
                return False
    return True


def match_graph(record, queries):
    """Check one graph against all queries. Returns FULL or PARTIAL matches only."""
    gid, line = record
    g = parse_graph(line)
    for qid, paths in enumerate(queries):
        hits = sum(1 for p in paths if satisfies_path(g, p))
        if hits == len(paths):
            yield (qid, gid, "FULL")
        elif hits > 0:
            yield (qid, gid, "PARTIAL")


# SPark steps

def create_spark(master="local[*]"):
    """Start Spark. local[*] = use all CPU cores of this machine."""
    spark = (SparkSession.builder.master(master).appName("GraphDBReduction")
             .config("spark.ui.showConsoleProgress", "false")
             .config("spark.sql.shuffle.partitions", "8")
             .getOrCreate())
    spark.sparkContext.setLogLevel("ERROR")
    return spark


def load_graphs(spark, db_path, partitions=None):
    """Step 1: read the database. Each graph gets a number (its line number)."""
    num_parts = partitions or spark.sparkContext.defaultParallelism
    lines = spark.read.text(str(db_path)).withColumn("pos", F.monotonically_increasing_id())
    # Number the lines 0, 1, 2, ... in file order
    gid = F.row_number().over(Window.orderBy("pos")) - 1
    graphs = lines.select(gid.cast("long").alias("gid"), F.col("value").alias("line"))
    # Split the graphs into equal parts, one per core
    return graphs.repartition(num_parts).cache()


def load_queries(qlog_path):
    """Step 2: read the query log."""
    with open(qlog_path) as f:
        return [[p.strip() for p in line.strip().split(",")] for line in f if line.strip()]


def run_matching(spark, graphs, queries):
    """Step 3: send the queries to every worker, each worker checks its own graphs."""
    queries_bc = spark.sparkContext.broadcast(queries)

    def match_partition(rows):
        qs = queries_bc.value
        for row in rows:
            yield from match_graph((row.gid, row.line), qs)

    rdd = graphs.rdd.mapPartitions(match_partition)
    # Result: one row per match -> (query, graph, FULL/PARTIAL)
    return spark.createDataFrame(rdd, "qid INT, gid LONG, type STRING").cache()


def compute_scores(spark, matches, num_graphs, method="rarity", alpha=0.5):
    """Step 4: give every graph a score.
    rarity:   full match = 1 / (graphs answering the query), partial = alpha / (graphs answering it)
    baseline: full match = 2, partial = 1"""
    if method == "rarity":
        # How many graphs answer each query
        counts = matches.groupBy("qid", "type").agg(F.count("*").alias("n"))
        weighted = matches.join(counts, ["qid", "type"]).withColumn(
            "w", F.when(F.col("type") == "FULL", 1.0 / F.col("n")).otherwise(F.lit(alpha) / F.col("n")))
    else:
        weighted = matches.withColumn("w", F.when(F.col("type") == "FULL", 2.0).otherwise(1.0))

    # Add up the points of each graph
    per_graph = weighted.groupBy("gid").agg(F.sum("w").alias("score"))
    # Graphs with no matches get score 0
    all_graphs = spark.range(num_graphs).withColumnRenamed("id", "gid")
    # Rounding so tiny decimal differences don't decide ties
    return (all_graphs.join(per_graph, "gid", "left").fillna(0.0, ["score"])
            .withColumn("score", F.round("score", 9)))


def select_top(scores, budget, num_graphs):
    """Step 5: keep the B% best graphs (on a tie, the lower graph number wins).
    The kept graphs stay inside Spark as a small table, so the next steps can reuse it."""
    k = max(1, int(num_graphs * budget))
    return scores.orderBy(F.desc("score"), F.asc("gid")).limit(k).select("gid").cache()


def write_reduced(graphs, kept_df, out_path):
    """Step 6: save the kept graphs, in their original order.
    Written with plain Python, because Spark's file writer needs extra tools on Windows."""
    rows = graphs.join(kept_df, "gid").orderBy("gid").select("line").collect()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        for row in rows:
            f.write(row.line + "\n")


def evaluate(matches, kept_df, num_queries):
    """Step 7: retention = answers we still have / answers we had before.
    macro = average over queries, micro = over all answers together.
    Queries with no answers at all are skipped."""
    kept_flag = kept_df.withColumn("kept", F.lit(1))
    # For each query: answers before (orig) and answers still kept (red)
    per_query = (matches.join(kept_flag, "gid", "left").fillna(0, ["kept"])
                 .groupBy("type", "qid").agg(F.count("*").alias("orig"), F.sum("kept").alias("red")))
    summary = per_query.groupBy("type").agg(
        F.avg(F.col("red") / F.col("orig")).alias("macro"),
        (F.sum("red") / F.sum("orig")).alias("micro"),
        F.count("*").alias("answerable")).collect()

    result = {t: {"macro": 0.0, "micro": 0.0, "skipped": num_queries} for t in ("FULL", "PARTIAL")}
    for row in summary:
        result[row.type] = {"macro": row.macro, "micro": row.micro, "skipped": num_queries - row.answerable}
    return result


def reduce_database(spark, db_path, qlog_path, budget, method="rarity", alpha=0.5, out_path=None, partitions=None):
    """Run all steps and measure how long each one takes."""
    timings = {}
    t = time.perf_counter()
    graphs = load_graphs(spark, db_path, partitions)
    num_graphs = graphs.count()
    queries = load_queries(qlog_path)
    timings["load"] = time.perf_counter() - t

    t = time.perf_counter()
    matches = run_matching(spark, graphs, queries)
    num_matches = matches.count()  # Spark is lazy: count() makes the matching actually run here
    timings["matching"] = time.perf_counter() - t

    t = time.perf_counter()
    scores = compute_scores(spark, matches, num_graphs, method, alpha)
    kept_df = select_top(scores, budget, num_graphs)
    kept = sorted(row.gid for row in kept_df.collect())
    timings["scoring+selection"] = time.perf_counter() - t

    if out_path is not None:
        t = time.perf_counter()
        write_reduced(graphs, kept_df, out_path)
        timings["write"] = time.perf_counter() - t

    t = time.perf_counter()
    retention = evaluate(matches, kept_df, len(queries))
    timings["evaluation"] = time.perf_counter() - t

    return {"num_graphs": num_graphs, "num_queries": len(queries), "num_matches": num_matches,
            "kept": kept, "retention": retention, "timings": timings}


def main():
    parser = argparse.ArgumentParser(description="Reduce a graph database with Apache Spark.")
    parser.add_argument("database", help="graph database file (one graph per line)")
    parser.add_argument("qlog", help="query log file (one query per line)")
    parser.add_argument("budget", type=float, help="B in [0,1]: fraction of graphs to keep")
    parser.add_argument("--method", choices=["rarity", "baseline"], default="rarity", help="scoring method (default: rarity)")
    parser.add_argument("--alpha", type=float, default=0.5, help="rarity weight for partial matches (default: 0.5)")
    parser.add_argument("--master", default="local[*]", help="Spark master (default: local[*] = all cores)")
    parser.add_argument("--partitions", type=int, default=None, help="number of partitions (default: one per core)")
    parser.add_argument("--out", default=None, help="reduced database file (default: results/<db>_<method>_B<B>.txt)")
    args = parser.parse_args()

    db_path, qlog_path = Path(args.database), Path(args.qlog)
    out_path = Path(args.out) if args.out else Path("results") / f"{db_path.stem}_{args.method}_B{args.budget}.txt"

    spark = create_spark(args.master)
    try:
        res = reduce_database(spark, db_path, qlog_path, args.budget, args.method, args.alpha, out_path, args.partitions)
    finally:
        spark.stop()

    print(f"\nMethod: {args.method}" + (f" (alpha={args.alpha})" if args.method == "rarity" else ""))
    print(f"Graphs: {res['num_graphs']} | Queries: {res['num_queries']} | Matches: {res['num_matches']}")
    print(f"Kept {len(res['kept'])} graphs (B={args.budget}) -> {out_path}")
    for match_type in ("FULL", "PARTIAL"):
        r = res["retention"][match_type]
        print(f"{match_type:<8} retention: macro {r['macro']:.4f} | micro {r['micro']:.4f} | skipped queries {r['skipped']}")
    print("Timings: " + ", ".join(f"{k} {v:.2f}s" for k, v in res["timings"].items()))


if __name__ == "__main__":
    main()
