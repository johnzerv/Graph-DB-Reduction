# Graph Datatabase Reduction Project

This project investigates graph database reduction techniques to improve query processing efficiency while preserving relevant results. It generates synthetic graph datasets and query logs to evaluate query matching, and different reduction methods based on recall evaluation.

### Project files

- `graph.py` class definitions and implementations for representing graphs and graph databases. Includes also a synthetic graph database and query-set generator. Generates a pair of graph database and query-set based on user-defined specifications.
- `query_engine.py` Implementation of the query engine. Parses a graph database and a query log and evaluates queries (path matching) classifying graph matches as `FULL`, `PARTIAL`, or `NONE`.
- `reducer.py` class definitions and implementations of reduction theories. 
- `evaluator.py` calculates per-query, macro, and micro average recall after a graph database reduction.
- `visualizers.py` creates interactive PyVis HTML views and Matplotlib graph views.
- `main.py` runs the graph evaluation, ranking, reduction, visualization, and recall reporting flow.
- `datasets/` contains generated datasets; `visualizations/` contains HTML output.
- `requirements.txt` lists the Python dependencies; `Makefile` provides a cleanup target.

### Set up

From the project directory, create and activate a virtual environment:

macOS/Linux:

```sh
python3 -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
```

Install the dependencies:

```sh
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### Generate the database and query logs

Generate a 10-graph database along with 50 queries and both query modes without opening a graph viewer:

```sh
python graph.py --num-graphs 10 --num-queries 50 --query-mode both --no-visualize
```

The repository includes data for this configuration: `datasets/Database13_10.txt` and 50-query uniform and skewed logs. To generate a different size, change the graph and query counts:

```sh
python graph.py --num-graphs 25 --num-queries 100 --query-mode both --no-visualize
```

Generated files are written to `datasets/` using these names:

- `Database<group>_<graphs>.txt`
- `QLog<group>_<graphs>_<queries>_<mode>.txt`

Existing database and log files are reused; pass `--regenerate` to recreate them. Use `--query-mode uniform` or `--query-mode skewed` to generate one mode, or `both` for both. The generator defaults to 10 graphs, 20 queries, and uniform mode.

Regarding query-set generation, two approaches are adopted:
- Uniform distribution: Queries are generated to distribute matches relatively evenly across the graphs in the database.
- Skewed distribution: Queries are generated so that matches are concentrated on a subset of graphs (which consists of so-called "hot-graphs"), while other receieve fewer matches (cold-graphs).

### Run the evaluation

`main.py` expects the database and matching query log to exist already; it does not generate them. For the checked-in 10-graph, 50-query sample data, run:

```sh
python main.py --num-graphs 10 --num-queries 50 --query-mode skewed
```

Use `--query-mode uniform` for the uniform log. Keep the graph count, query count, group number, and mode consistent with the input filenames. The defaults for `main.py` are 10 graphs, 20 queries, group `13`, and skewed mode.

The query engine is used by `main.py`; `query_engine.py` does not provide a standalone command-line interface. Each query-log line contains one or more comma-separated paths, with path elements separated by periods, for example `2.likes.4.department.AI`.

The evaluation prints full and partial matches, ranks graphs, then reduces the database to 70% of its graphs (7 of 10 with the sample size). It writes the reduced database to a separate file such as `datasets/Database13_7.txt`, leaving the original database file in place. It also reports per-query, macro, and micro recall and writes the query-to-graph HTML view to `visualizations/`.

### Visualize the database

Launch the interactive HTML graph selector:

```sh
python graph.py -v html
```

Or use the Matplotlib viewer:

```sh
python graph.py -v python
```

Enter a graph number when prompted, or `q` to quit. HTML output is written to `visualizations/`.

### Clean generated data

```sh
make clean
```

This removes the `datasets/` and `visualizations/` directory contents (graph databases, query sets, graph visualizations).

## TODOS:
1. Work queries (paths) that include variables (e.g., X.knows.Y). This should also increase partial matches. We need to understand how we can modelize graphs with such queries.
2. Create the deliverable dataset. Maybe one more distribution?
3. Implement other than only the baseline reduction strategies.
4. Move to PySpark.
