import re
from pyspark.sql import Window, functions as F

TRIPLE_REGEX = re.compile(r"<(.*?)>")

def parse_graph(line):
    nodes, edges, attrs = set(), set(), set()
    for triple in TRIPLE_REGEX.findall(line):
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
    parts = path.split(".")
    if len(parts) == 1:
        x = parts[0]
        return (x.isdigit() and int(x) in g["nodes"]) or x in g["edge_labels"] or x in g["attr_names_values"]

    for i in range(0, len(parts) - 1, 2):
        source, predicate = parts[i], parts[i + 1]
        if not source.isdigit():
            return False
        src = int(source)
        if i + 2 < len(parts):
            dest = parts[i + 2]
            if not ((dest.isdigit() and (src, predicate, int(dest)) in g["edges"])
                    or (src, predicate, dest) in g["attrs"]):
                return False
        else:
            if (src, predicate) not in g["edge_src_label"] and (src, predicate) not in g["attr_src_name"]:
                return False
    return True

def match_graph(record, queries):
    gid, line = record
    g = parse_graph(line)
    for qid, paths in enumerate(queries):
        hits = sum(1 for p in paths if satisfies_path(g, p))
        if hits == len(paths):
            yield (qid, gid, "FULL")
        elif hits > 0:
            yield (qid, gid, "PARTIAL")

# Factory function strictly outside the class avoids capturing `self`
def get_match_partition_func(queries_bc):
    def match_partition(rows):
        qs = queries_bc.value
        for row in rows:
            yield from match_graph((row.gid, row.line), qs)
    return match_partition

class SparkQueryEngine:
    def __init__(self, spark, db_path, qlog_path, partitions=None):
        self.spark = spark
        self.db_path = str(db_path)
        self.qlog_path = str(qlog_path)
        self.partitions = partitions or self.spark.sparkContext.defaultParallelism
        
        self.graphs_df = None
        self.queries = []
        self.num_graphs = 0

    def load_data(self):
        lines = self.spark.read.text(self.db_path).withColumn("pos", F.monotonically_increasing_id())
        gid = F.row_number().over(Window.orderBy("pos")) - 1
        self.graphs_df = lines.select(gid.cast("long").alias("gid"), F.col("value").alias("line"))
        self.graphs_df = self.graphs_df.repartition(self.partitions).cache()
        self.num_graphs = self.graphs_df.count()

        with open(self.qlog_path) as f:
            self.queries = [[p.strip() for p in line.strip().split(",")] for line in f if line.strip()]

    def run(self):
        if self.graphs_df is None:
            self.load_data()

        queries_bc = self.spark.sparkContext.broadcast(self.queries)
        
        # Uses the top-level factory to ensure clean serialization
        mapper_func = get_match_partition_func(queries_bc)
        rdd = self.graphs_df.rdd.mapPartitions(mapper_func)
        
        return self.spark.createDataFrame(rdd, "qid INT, gid LONG, type STRING").cache()