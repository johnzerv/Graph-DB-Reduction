import random
import re
import argparse
from pathlib import Path

from visualizers import visualize_database_matplotlib, visualize_database_html


class Graph:
    """Graph represents a single graph with its nodes, edges, and attributes."""
    def __init__(self, nodes, edges, attributes, triples):
        self.nodes = nodes
        self.edges = edges
        self.attributes = attributes
        self.triples = triples

    def __tostring__(self):
        """Return a string representation of the graph in the required format."""
        triples = []
        for source, label, dest in self.edges:
            triples.append(f"<{source},{label},{dest}>")
        for node, attr_name, attr_val in self.attributes:
            triples.append(f"<{node},{attr_name},{attr_val}>")
        return ",".join(triples)


class GraphDB:
    """GraphDB represents a collection of graphs and the associated query log."""
    def __init__(self, num_graphs=10, num_queries=20, group_number="13", query_mode="skewed", dataset_dir = Path("datasets"), database_file=None, log_file=None, graph_indices=None):
        self.num_graphs = num_graphs
        self.num_queries = num_queries
        self.group_number = group_number
        self.query_mode = query_mode
        
        self.dataset_dir = dataset_dir
        self.database_file = database_file or self.dataset_dir / f"Database{group_number}_{num_graphs}.txt"
        self.log_file = log_file or self.dataset_dir / f"QLog{group_number}_{num_graphs}_{num_queries}_{query_mode}.txt"
        
        self.graphs = []
        self.graph_indices = graph_indices

        if self.database_file.exists():
            self._load_database_data()

    def _save(self):
        """Save the graph database to the specified file."""
        self.dataset_dir.mkdir(parents=True, exist_ok=True)

        with open(self.database_file, "w") as db_file:
            for graph in self.graphs:
                db_file.write(graph.__tostring__() + "\n")

    def _load_database_data(self):
        """Load the existing graph database from disk."""
        self.graphs = []

        with open(self.database_file, "r") as db_file:
            for idx, line in enumerate(db_file):
                # Load only the retained graphs in case of a reduced database
                if self.graph_indices is not None and idx not in self.graph_indices:
                    continue

                nodes_set = set()
                edges_raw = []
                attrs_raw = []

                for triple in re.findall(r"<(.*?)>", line):
                    parts = [part.strip() for part in triple.split(",")]
                    if len(parts) != 3:
                        continue

                    source, predicate, obj = parts
                    nodes_set.add(int(source))

                    if predicate in GraphGenerator.EDGE_LABELS:
                        edges_raw.append((int(source), predicate, int(obj)))
                        nodes_set.add(int(obj))
                    else:
                        attrs_raw.append((int(source), predicate, obj))

                self.graphs.append(Graph(
                    nodes=list(nodes_set),
                    edges=edges_raw,
                    attributes=attrs_raw,
                    triples=[]
                ))

        if self.graph_indices is not None:
            self.num_graphs = len(self.graphs)
            self.database_file = self.dataset_dir / f"Database{self.group_number}_{self.num_graphs}.txt"

        return self

    def reduce(self, graph_indices_to_retain):
        """Return a new GraphDB containing only the selected graph indices"""

        reduced_db = GraphDB(
            num_graphs=self.num_graphs,
            num_queries=self.num_queries,
            group_number=self.group_number,
            query_mode=self.query_mode,
            dataset_dir=self.dataset_dir,
            database_file=self.dataset_dir / f"Database{self.group_number}_{self.num_graphs}.txt",
            log_file=self.dataset_dir / f"QLog{self.group_number}_{self.num_graphs}_{self.num_queries}_{self.query_mode}.txt",
            graph_indices=graph_indices_to_retain
        )
        reduced_db._save()

        return reduced_db


class GraphGenerator:
    """"GraphGenerator is responsible for generating a set of graphs and queries based on the specified parameters."""
    EDGE_LABELS = ["knows", "loves", "hates", "likes", "envies"]

    def __init__(self, num_graphs=10, num_queries=20, group_number="13", query_mode="skewed", hot_ratio=0.3):
        self.db = GraphDB(num_graphs, num_queries, group_number, query_mode)

        # Graph generation parameters
        self.min_nodes = 5
        self.max_nodes = 15
        self.min_edges = 1
        self.max_edges = 3

        # Available edge labels and node attributes
        self.edge_labels = list(self.EDGE_LABELS)
        self.attributes = {
            "city": ["Utrecht", "Amsterdam", "Eindhoven", "Rotterdam"],
            "age": ["20", "25", "35", "42", "55"],
            "gender": ["male", "female", "non-binary"],
            "department": ["CS", "AI", "DS"],
        }

        # Set a fixed random seed for reproducibility
        self.seed = 42
        self.random = random.Random(self.seed)
        self.hot_ratio = hot_ratio # Percentage of graphs considered "hot" for skewed query generation

    def generate_single_graph(self):
        # Randomly choose the number of nodes
        num_nodes = self.random.randint(self.min_nodes, self.max_nodes)
        nodes = list(range(1, num_nodes + 1))   # node indices
        
        triples = []
        edges_raw = []
        attrs_raw = []

        edges_dict = {}
        for source in nodes:
            # Randomly choose the number of edges
            num_edges = self.random.randint(self.min_edges, self.max_edges)

            # Sample the destination nodes
            destinations = self.random.sample(
                [node for node in nodes if node != source],
                num_edges,
            )

            # Treat the selected src and dest nodes as tuples in order to prevent having the same pair with different label
            for dest in destinations:
                pair = tuple(sorted((source, dest)))
                if pair not in edges_dict:
                    edges_dict[pair] = self.random.choice(self.edge_labels)

        for (source, dest), label in edges_dict.items():
            triples.append(f"<{source},{label},{dest}>")
            edges_raw.append((source, label, dest))

        # For each node randomly select 0 to 2 attributes
        for node in nodes:
            num_attrs = self.random.randint(0, 2)
            chosen_attrs = self.random.sample(list(self.attributes.keys()), num_attrs)
            for attr_name in chosen_attrs:
                attr_val = self.random.choice(self.attributes[attr_name])
                serialized_value = f'"{attr_val}"'
                triples.append(f'<{node},{attr_name},{serialized_value}>')
                attrs_raw.append((node, attr_name, serialized_value))

        self.random.shuffle(triples)
        
        graph_obj = Graph(nodes=nodes, edges=edges_raw, attributes=attrs_raw, triples=triples)
        
        return graph_obj
    
    def generate_database(self) -> GraphDB:
        print(f"Generating {self.db.num_graphs} graphs for {self.db.database_file}...")
        self.db.dataset_dir.mkdir(parents=True, exist_ok=True)

        self.db.graphs = []

        for _ in range(self.db.num_graphs):
            graph_obj = self.generate_single_graph()
            self.db.graphs.append(graph_obj)

        self.db._save()
        print(f"Database generated: {self.db.database_file}\n")

        return self.db

    def _load_database_data(self) -> GraphDB:
        self.db.graphs = []

        with open(self.db.database_file, "r") as db_file:
            for line in db_file:
                nodes_set = set()
                edges_raw = []
                attrs_raw = []
                triples = re.findall(r"<(>*?>)", line)
                
                for triple in triples:
                    parts = [part.strip() for part in triple.split(",")]
                    if len(parts) != 3:
                        continue

                    source, predicate, obj = parts
                    nodes_set.add(int(source))
                    
                    if predicate in self.attributes:
                        attrs_raw.append((int(source), predicate, obj))
                    elif predicate in self.edge_labels:
                        edges_raw.append((int(source), predicate, int(obj)))
                        nodes_set.add(int(obj))

                nodes = list(nodes_set)
                self.db.graphs.append(Graph(nodes=nodes, edges=edges_raw, attributes=attrs_raw, triples=triples))

        return self.db

    def generate_path(self, graph: Graph):
        edges = graph.edges.copy()
        self.random.shuffle(edges)

        for source, label, dest in edges:
            dest_attrs = [attr for attr in graph.attributes if attr[0] == dest]
            if dest_attrs:
                attr = self.random.choice(dest_attrs)
                return f"{source}.{label}.{dest}.{attr[1]}.{attr[2]}"

        edge = self.random.choice(edges)
        return f"{edge[0]}.{edge[1]}.{edge[2]}"

    def generate_queries(self, graph_db: GraphDB = None, query_mode=None):
        if graph_db is None:
            graph_db = self.db

        query_mode = query_mode or graph_db.query_mode
        log_file = graph_db.dataset_dir / f"QLog{graph_db.group_number}_{graph_db.num_graphs}_{graph_db.num_queries}_{query_mode}.txt"
        print(f"Generating {graph_db.num_queries} queries for {log_file}...")
        graph_db.dataset_dir.mkdir(parents=True, exist_ok=True)

        query_target_graphs = []
        if query_mode == "uniform":
            query_target_graphs = [i % graph_db.num_graphs for i in range(graph_db.num_queries)]
            self.random.shuffle(query_target_graphs)
        else:
            num_hot = max(1, int(graph_db.num_graphs * self.hot_ratio))
            hot_graphs = self.random.sample(range(graph_db.num_graphs), num_hot)
            cold_graphs = list(set(range(graph_db.num_graphs)) - set(hot_graphs))
            
            print(f"  -> Hot Graphs chosen: {hot_graphs}")
            for _ in range(graph_db.num_queries):
                if cold_graphs and self.random.random() > 0.85:
                    query_target_graphs.append(self.random.choice(cold_graphs))
                else:
                    query_target_graphs.append(self.random.choice(hot_graphs))

        with open(log_file, "w") as output_file:
            for target_idx in query_target_graphs:
                paths = []
                num_paths_in_query = self.random.randint(1, 3)
                for _ in range(num_paths_in_query):
                    path = self.generate_path(graph_db.graphs[target_idx])
                    paths.append(path)
                
                output_file.write(",".join(paths) + "\n")

            print(f"Queries created: {log_file}\n")

    def reduce_graphs(self, graph_indices, database_file=None):
        """Return the original graph triples for the selected graph indices"""
        if database_file is None:
            database_file = self.db.database_file

        selected_graphs = []
        indices_to_retain = set(graph_indices)

        with open(database_file, "r") as db_file:
            for idx, line in enumerate(db_file):
                if idx in indices_to_retain:
                    selected_graphs.append(line.strip())

        return selected_graphs

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate graphs or visualize a graph database.")
    parser.add_argument("-n", "--num-graphs", "--graphs", type=int, default=10, help="number of graphs in the database (default: 10)")
    parser.add_argument("--num-queries", type=int, default=20, help="number of queries to generate (default: 20)")
    parser.add_argument("--group-number", default="13", help="group number used in database and query filenames (default: 13)")
    parser.add_argument("-v", "--visualizer", choices=("python", "html"), default="html", help="visualize an existing database with the Python or HTML viewer")
    parser.add_argument("--no-visualize", action="store_true", help="do not visualize the database after generation")
    parser.add_argument("-rg", "--regenerate", action="store_true", help="regenerate the database even if it already exists")
    parser.add_argument("--query-mode", choices=("uniform", "skewed", "both"), default="uniform", help="How queries are distributed across graphs.")
    parser.add_argument("--hot-ratio", type=float, default=0.2, help="Percentage of graphs considered 'hot' (e.g., 0.2 for 20 percent).")

    args = parser.parse_args()

    configured_mode = "uniform" if args.query_mode == "both" else args.query_mode
    generator = GraphGenerator(
        num_graphs=args.num_graphs, 
        num_queries=args.num_queries, 
        group_number=args.group_number, 
        query_mode=configured_mode, 
        hot_ratio=args.hot_ratio
    )

    if args.regenerate or not Path(generator.db.database_file).exists():
        graph_db = generator.generate_database()
    else:
        graph_db = generator._load_database_data()

    query_modes = ("uniform", "skewed") if args.query_mode == "both" else (args.query_mode,)
    for query_mode in query_modes:
        query_file = graph_db.dataset_dir / f"QLog{graph_db.group_number}_{graph_db.num_graphs}_{graph_db.num_queries}_{query_mode}.txt"
        if args.regenerate or not query_file.exists():
            generator.generate_queries(graph_db, query_mode)

    # Replaced class methods with function calls to visualizations.py
    if not args.no_visualize:
        if args.visualizer == "python":
            visualize_database_matplotlib(graph_db.database_file, generator.attributes)
        else:
            visualize_database_html(graph_db.database_file, generator.attributes)