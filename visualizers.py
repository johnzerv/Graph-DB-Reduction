import re
from pathlib import Path
import networkx as nx
import matplotlib.pyplot as plt
from pyvis.network import Network

def visualize_query_graph_relations(queries, num_graphs, match_results, graph_scores, output_file="query_relations.html"):
    """
    Visualizes the bipartite relationship between Queries and Graphs.
    Queries are green boxes, Graphs are blue database cylinders.
    Full matches are thick green lines; Partial matches are dashed orange lines.
    """
    print(f"\nGenerating Query-Graph relation visualization: {output_file}...")
    
    net = Network(
        height="800px",
        width="100%",
        directed=False,
        bgcolor="#ffffff",
        font_color="black"
    )
    
    net.force_atlas_2based(
        gravity=-50,
        central_gravity=0.01,
        spring_length=200,
        spring_strength=0.08,
    )

    # 1. Add Query Nodes
    for q_idx, q_paths in enumerate(queries):
        hover_text = f"<b>Query {q_idx}</b><br>" + "<br>".join(q_paths)
        net.add_node(
            f"Q{q_idx}", 
            label=f"Q{q_idx}", 
            title=hover_text, 
            shape="box", 
            color="#a8d08d"
        )

    # 2. Add Graph Nodes
    for g_idx in range(num_graphs):
        score = graph_scores.get(g_idx, 0)
        hover_text = f"<b>Graph {g_idx}</b><br>Importance Score: {score}"
        net.add_node(
            f"G{g_idx}", 
            label=f"G{g_idx}", 
            title=hover_text, 
            shape="database", 
            color="#9bc2e6"
        )

    # 3. Add Edges based on match_results
    for (q_idx, g_idx), match_type in match_results.items():
        if match_type == 'FULL':
            net.add_edge(f"Q{q_idx}", f"G{g_idx}", color="#2e7d32", width=3, title="FULL Match")
        elif match_type == 'PARTIAL':
            net.add_edge(f"Q{q_idx}", f"G{g_idx}", color="#f57c00", width=1, dashes=True, title="PARTIAL Match")

    output_dir = Path("visualizations")
    output_dir.mkdir(exist_ok=True)
    out_path = output_dir / output_file
    net.show(str(out_path), notebook=False)
    print(f"Opening visualization in your browser: {out_path}")


# -------------------------------------------------------------------------
# Matplotlib / NetworkX Visualization Functions
# -------------------------------------------------------------------------

def parse_graph_line(line, attributes):
    """Parses a single graph line into a NetworkX MultiGraph."""
    graph = nx.MultiGraph()
    triples = re.findall(r"<(.*?)>", line)

    for triple in triples:
        parts = triple.split(",")
        if len(parts) != 3:
            continue

        source = int(parts[0])
        predicate = parts[1]
        obj = parts[2]
        graph.add_node(source)

        # Check if the predicate is a known attribute (from the dict keys)
        if predicate in attributes:
            graph.nodes[source][predicate] = obj
        else:
            graph.add_edge(source, int(obj), label=predicate)

    return graph

def visualize_graph_matplotlib(graph, graph_index, database_file):
    """Draws the NetworkX graph using Matplotlib."""
    plt.figure(figsize=(14, 10))
    plt.title(
        f"Visualization of Graph {graph_index} from {database_file}",
        fontsize=16,
        fontweight="bold",
    )
    pos = nx.spring_layout(graph, k=3.0, iterations=100, seed=42)

    node_labels = {}
    for node, attrs in graph.nodes(data=True):
        label_lines = [f"{node}"]
        label_lines.extend(f"{name}: {value}" for name, value in attrs.items())
        node_labels[node] = "\n".join(label_lines)

    nx.draw_networkx_nodes(graph, pos, node_color="lightblue", node_size=2500, alpha=0.9, edgecolors="black")
    nx.draw_networkx_labels(graph, pos, labels=node_labels, font_size=9, bbox=dict(facecolor="white", edgecolor="black", boxstyle="round,pad=0.3"))

    seen_pairs = {}
    for source, dest, _, data in graph.edges(keys=True, data=True):
        pair = tuple(sorted((source, dest)))
        seen_pairs[pair] = seen_pairs.get(pair, 0) + 1
        count = seen_pairs[pair]
        radius = 0.15 * ((count + 1) // 2)
        if count % 2 == 0:
            radius = -radius
        edge_curve = f"arc3,rad={radius}"

        nx.draw_networkx_edges(graph, pos, edgelist=[(source, dest)], arrows=False, edge_color="gray", width=1.5, connectionstyle=edge_curve)
        nx.draw_networkx_edge_labels(graph, pos, edge_labels={(source, dest): data["label"]}, font_size=10, font_color="red", label_pos=0.5, connectionstyle=edge_curve, bbox=dict(facecolor="white", edgecolor="none", alpha=0.8, pad=0.2))

    plt.axis("off")
    plt.tight_layout()
    plt.show()

def visualize_database_matplotlib(database_file, attributes):
    """Interactive loop to visualize database graphs using Matplotlib."""
    try:
        with open(database_file, "r") as file:
            lines = file.readlines()

        print(f"Loaded {len(lines)} graphs from {database_file}.")
        while True:
            user_input = input(f"Enter graph line number to visualize (0 to {len(lines) - 1}) or 'q' to quit: ")
            if user_input.lower() == "q":
                break

            try:
                index = int(user_input)
                if 0 <= index < len(lines):
                    graph = parse_graph_line(lines[index], attributes)
                    visualize_graph_matplotlib(graph, index, database_file)
                else:
                    print("Index out of bounds.")
            except ValueError:
                print("Please enter a valid number.")
    except FileNotFoundError:
        print(f"Could not find {database_file}. Make sure you ran the generator script first!")


# -------------------------------------------------------------------------
# PyVis / HTML Visualization Functions
# -------------------------------------------------------------------------

def visualize_graph_html(line, graph_index, attributes):
    """Draws a single graph line into an interactive HTML file using PyVis."""
    net = Network(height="800px", width="100%", directed=False, bgcolor="#ffffff", font_color="black")
    net.force_atlas_2based(gravity=-100, central_gravity=0.01, spring_length=200, spring_strength=0.08)

    triples = re.findall(r"<(.*?)>", line)
    nodes_attrs = {}
    edges = []

    for triple in triples:
        parts = triple.split(",")
        source, predicate, obj = int(parts[0]), parts[1].strip(), parts[2].strip()
        nodes_attrs.setdefault(source, [])

        if predicate in attributes:
            nodes_attrs[source].append(f"{predicate}: {obj}")
        else:
            dest = int(obj)
            edges.append((source, dest, predicate))
            nodes_attrs.setdefault(dest, [])

    for node_id, attrs_list in nodes_attrs.items():
        label_text = f"{node_id}\n" + "\n".join(attrs_list)
        net.add_node(node_id, label=label_text, shape="box", color="#97c2fc")

    for source, dest, label in edges:
        net.add_edge(source, dest, label=label, color="#e63946")

    output_dir = Path("visualizations")
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / f"graph_{graph_index}.html"
    print(f"Opening interactive view: {output_file}\n")
    net.show(str(output_file), notebook=False)

def visualize_database_html(database_file, attributes):
    """Interactive loop to visualize database graphs as HTML."""
    try:
        with open(database_file, "r") as file:
            lines = file.readlines()

        while True:
            user_input = input(f"Enter graph number to open in browser (0 to {len(lines) - 1}) or 'q' to quit: ")
            if user_input.lower() == "q":
                break

            try:
                index = int(user_input)
                if 0 <= index < len(lines):
                    visualize_graph_html(lines[index], index, attributes)
                else:
                    print("Index out of bounds.")
            except ValueError:
                print("Please enter a valid number.")
    except FileNotFoundError:
        print(f"Could not find {database_file}. Make sure you ran the generator script first!")