import random
import re
import argparse
from pathlib import Path

from visualizers import visualize_database_matplotlib, visualize_database_html

class Graph:
    EDGE_LABELS = ["knows", "loves", "hates", "likes", "envies"]


    def __init__(self, num_graphs=10, num_queries=20, group_number="13", query_mode="skewed", hot_ratio=0.3):
        self.group_number = group_number
        self.dataset_dir = Path("datasets")
        self.database_file = self.dataset_dir / f"Database{group_number}_{num_graphs}.txt"
        self.log_file = self.dataset_dir / f"QLog{group_number}_{num_graphs}_{num_queries}_{query_mode}.txt"

        # Graph generation parameters
        self.num_graphs = num_graphs
        self.min_nodes = 5
        self.max_nodes = 15
        self.min_edges = 1
        self.max_edges = 3

        # Available edge labels and node attributes
        self.edge_labels = list(Graph.EDGE_LABELS)
        self.attributes = {
            "city": ["Utrecht", "Amsterdam", "Eindhoven", "Rotterdam"],
            "age": ["20", "25", "35", "42", "55"],
            "gender": ["male", "female", "non-binary"],
            "department": ["CS", "AI", "DS"],
        }

        self.num_queries = num_queries

        # Set a fixed random seed for reproducibility
        self.seed = 42
        self.random = random.Random(self.seed)

        self.query_mode = query_mode
        self.hot_ratio = hot_ratio

    def generate_single_graph(self):
        num_nodes = self.random.randint(self.min_nodes, self.max_nodes)
        triples = []
        edges_raw = []
        attrs_raw = []

        edges = {}
        for source in range(1, num_nodes + 1):
            num_edges = self.random.randint(self.min_edges, self.max_edges)
            destinations = self.random.sample(
                [node for node in range(1, num_nodes + 1) if node != source],
                num_edges,
            )
            for dest in destinations:
                pair = tuple(sorted((source, dest)))
                if pair not in edges:
                    edges[pair] = self.random.choice(self.edge_labels)

        for (source, dest), label in edges.items():
            triples.append(f"<{source},{label},{dest}>")
            edges_raw.append((source, label, dest))

        for node in range(1, num_nodes + 1):
            num_attrs = self.random.randint(0, 2)
            chosen_attrs = self.random.sample(list(self.attributes.keys()), num_attrs)
            for attr_name in chosen_attrs:
                attr_val = self.random.choice(self.attributes[attr_name])
                serialized_value = f'"{attr_val}"' if attr_val.isdigit() else attr_val
                triples.append(f'<{node},{attr_name},{serialized_value}>')
                attrs_raw.append((node, attr_name, serialized_value))

        self.random.shuffle(triples)
        return ",".join(triples), edges_raw, attrs_raw

    def generate_query(self, edges_raw, attrs_raw):
        edges = edges_raw.copy()
        self.random.shuffle(edges)

        for source, label, dest in edges:
            dest_attrs = [attr for attr in attrs_raw if attr[0] == dest]
            if dest_attrs:
                attr = self.random.choice(dest_attrs)
                return f"{source}.{label}.{dest}.{attr[1]}.{attr[2]}"

        edge = self.random.choice(edges)
        return f"{edge[0]}.{edge[1]}.{edge[2]}"

    def generate_database(self):
        print(f"Generating {self.num_graphs} graphs for {self.database_file}...")
        self.dataset_dir.mkdir(parents=True, exist_ok=True)

        all_edges = []
        all_attrs = []

        with open(self.database_file, "w") as db_file:
            for _ in range(self.num_graphs):
                graph_string, edges_raw, attrs_raw = self.generate_single_graph()
                db_file.write(graph_string + "\n")
                all_edges.append(edges_raw)
                all_attrs.append(attrs_raw)

        print(f"Database created: {self.database_file}\n")
        return all_edges, all_attrs

    def load_database_data(self):
        all_edges = []
        all_attrs = []

        with open(self.database_file, "r") as db_file:
            for line in db_file:
                edges_raw = []
                attrs_raw = []
                for triple in re.findall(r"<(.*?)>", line):
                    parts = [part.strip() for part in triple.split(",")]
                    if len(parts) != 3:
                        continue

                    source, predicate, obj = parts
                    if predicate in self.attributes:
                        attrs_raw.append((int(source), predicate, obj))
                    elif predicate in self.edge_labels:
                        edges_raw.append((int(source), predicate, int(obj)))

                all_edges.append(edges_raw)
                all_attrs.append(attrs_raw)

        return all_edges, all_attrs

    def generate_queries(self, all_edges=None, all_attrs=None, query_mode=None):
        if all_edges is None or all_attrs is None:
            all_edges, all_attrs = self.load_database_data()

        query_mode = query_mode or self.query_mode
        log_file = self.dataset_dir / f"QLog{self.group_number}_{self.num_graphs}_{self.num_queries}_{query_mode}.txt"
        print(f"Generating {self.num_queries} queries for {log_file}...")
        self.dataset_dir.mkdir(parents=True, exist_ok=True)

        query_targets = []
        if query_mode == "uniform":
            query_targets = [i % self.num_graphs for i in range(self.num_queries)]
            self.random.shuffle(query_targets)
        else:
            num_hot = max(1, int(self.num_graphs * self.hot_ratio))
            hot_graphs = self.random.sample(range(self.num_graphs), num_hot)
            cold_graphs = list(set(range(self.num_graphs)) - set(hot_graphs))
            
            print(f"  -> Hot Graphs chosen: {hot_graphs}")
            for _ in range(self.num_queries):
                if cold_graphs and self.random.random() > 0.85:
                    query_targets.append(self.random.choice(cold_graphs))
                else:
                    query_targets.append(self.random.choice(hot_graphs))

        with open(log_file, "w") as output_file:
            for target_idx in query_targets:
                paths = []
                num_paths_in_query = self.random.randint(1, 3)
                for _ in range(num_paths_in_query):
                    path = self.generate_query(all_edges[target_idx], all_attrs[target_idx])
                    paths.append(path)
                
                output_file.write(",".join(paths) + "\n")

            print(f"Queries created: {log_file}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate graphs or visualize a graph database.")
    parser.add_argument("-n", "--num-graphs", "--graphs", type=int, default=10, help="number of graphs in the database (default: 10)")
    parser.add_argument("--num-queries", type=int, default=20, help="number of queries to generate (default: 20)")
    parser.add_argument("--group-number", default="13", help="group number used in database and query filenames (default: 13)")
    parser.add_argument("-v", "--visualizer", choices=("python", "html"), default="html", help="visualize an existing database with the Python or HTML viewer")
    parser.add_argument("--no-visualize", action="store_true", help="do not visualize the database after generation")
    parser.add_argument("-rg", "--regenerate", action="store_true", help="regenerate the database even if it already exists")
    parser.add_argument("--query-mode", choices=("uniform", "skewed", "both"), default="uniform", help="How queries are distributed across graphs.")
    parser.add_argument("--hot-ratio", type=float, default=0.2, help="Percentage of graphs considered 'hot' (e.g., 0.2 for 20%).")

    args = parser.parse_args()

    configured_mode = "uniform" if args.query_mode == "both" else args.query_mode
    graph = Graph(num_graphs=args.num_graphs, num_queries=args.num_queries, group_number=args.group_number, query_mode=configured_mode, hot_ratio=args.hot_ratio)

    if args.regenerate or not Path(graph.database_file).exists():
        all_edges, all_attrs = graph.generate_database()
    else:
        all_edges, all_attrs = graph.load_database_data()

    query_modes = ("uniform", "skewed") if args.query_mode == "both" else (args.query_mode,)
    for query_mode in query_modes:
        query_file = graph.dataset_dir / f"QLog{graph.group_number}_{graph.num_queries}_{query_mode}.txt"
        if args.regenerate or not query_file.exists():
            graph.generate_queries(all_edges, all_attrs, query_mode)

    # Replaced class methods with function calls to visualizations.py
    if not args.no_visualize:
        if args.visualizer == "python":
            visualize_database_matplotlib(graph.database_file, graph.attributes)
        else:
            visualize_database_html(graph.database_file, graph.attributes)