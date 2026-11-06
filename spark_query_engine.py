import re
from pyspark.sql import Window, functions as F

TRIPLE_REGEX = re.compile(r"<(.*?)>")
VAR_REGEX = re.compile(r"^[A-Z][A-Za-z0-9_]*$")   # X, Y, City ...

def is_var(tok):
    return bool(VAR_REGEX.match(tok))

def parse_graph(line):
    nodes, edges, attrs = set(), set(), set()
    out_edges, out_attrs = {}, {}          # added: adjacency indexes for variable traversal
    for triple in TRIPLE_REGEX.findall(line):
        parts = [p.strip() for p in triple.split(",")]
        if len(parts) != 3:
            continue
        src, label, obj = parts
        src = int(src)
        nodes.add(src)
        
        # If it explicitly has quotes, it's definitely an attribute
        if obj.startswith('"') and obj.endswith('"'):
            attrs.add((src, label, obj))
            out_attrs.setdefault(src, []).append((label, obj))
            
        # If it has no quotes but is a digit, it's an edge (as per assignment rules)
        elif obj.isdigit():
            edges.add((src, label, int(obj)))
            out_edges.setdefault(src, []).append((label, int(obj)))
            nodes.add(int(obj))
            
        # If it has no quotes and is NOT a digit, it's an unquoted string attribute
        else:
            fixed_obj = f'"{obj}"'
            attrs.add((src, label, fixed_obj))
            out_attrs.setdefault(src, []).append((label, fixed_obj))
            
    return {
        "nodes": nodes,
        "edges": edges,
        "attrs": attrs,
        "out_edges": out_edges,
        "out_attrs": out_attrs,
        "edge_src_label": {(s, l) for s, l, _ in edges},
        "attr_src_name": {(s, n) for s, n, _ in attrs},
        "edge_labels": {l for _, l, _ in edges},
        "attr_names_values": {n for _, n, _ in attrs} | {v for _, _, v in attrs},
    }

def satisfies_path(g, path):
    parts = path.split(".")
    if len(parts) == 1:
        x = parts[0]
        return (is_var(x)
                or (x.isdigit() and int(x) in g["nodes"])
                or x in g["edge_labels"]
                or x in g["attr_names_values"])
    return _walk(g, parts, 0, {})

def _walk(graph, parts, index, bindings):
    source, predicate = parts[index], parts[index + 1]

    # Determine possible source nodes
    if source.isdigit():
        source_nodes = [int(source)]
    elif is_var(source):
        source_nodes = [bindings[source]] if source in bindings else graph["nodes"]
    else:
        return False

    for source_node in source_nodes:
        current_bindings = {**bindings, source: source_node} if is_var(source) else bindings

        if index + 2 >= len(parts):  # Path ends with a predicate: existence check
            if ((source_node, predicate) in graph["edge_src_label"]
                    or (source_node, predicate) in graph["attr_src_name"]):
                return True
            continue

        destination = parts[index + 2]
        is_last_step = index + 2 == len(parts) - 1

        # Check outgoing edges
        for edge_label, target_node in graph["out_edges"].get(source_node, []):
            if edge_label != predicate:
                continue

            if is_var(destination):
                if destination in current_bindings and current_bindings[destination] != target_node:
                    continue
                next_bindings = {**current_bindings, destination: target_node}
            elif destination.isdigit() and int(destination) == target_node:
                next_bindings = current_bindings
            else:
                continue

            if is_last_step or _walk(graph, parts, index + 2, next_bindings):
                return True

        # Check attributes at the end of the path
        if is_last_step:
            for attribute_name, attribute_value in graph["out_attrs"].get(source_node, []):
                if attribute_name != predicate:
                    continue

                if is_var(destination):
                    if destination in current_bindings and current_bindings[destination] != attribute_value:
                        continue
                    return True
                elif destination == attribute_value or f'"{destination}"' == attribute_value:
                    return True

    return False

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