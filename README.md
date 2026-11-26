# Graph Datatabase Reduction Project

This project investigates graph database reduction techniques to improve query processing efficiency while preserving relevant results. It generates synthetic graph datasets and query logs to evaluate query matching, and different reduction methods based on retention evaluation.

### Project files

- `spark_evaluator.py`: implementation of retention (micro and macro) evaluation metric.
- `spark_query_engine.py`: a very simple query engine for graph databases (as they are defined in the project description).
- `spark_reducer.py`: implementation of the two different reduction techniques (participation & rarity scoring methods).
- `spark_experiments.py`: the main experimental pipeline, consisting of two main experiments (focusing on retention quality and execution time).

All above are implemented in Apache Spark (PySpark).

- `graph.py`: implementation of a GraphDB and query generator, using two kind of query-to-graphs distributions (uniform and skewed).
- `visualizers.py`: helper methods for graphDB visualizations.

In `python_implementations` directory one can find the initial implementations in native-python.

### Set up

From the project directory, create and activate a virtual environment:

macOS/Linux:

```sh
python3 -m venv .venv
source .venv/bin/activate
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

This removes the `datasets/` and `visualizations/` directory contents (graph databases, query sets, graph visualizations).

## Experiments

The `experiments.py` script evaluates the Spark graph-database reduction using two types of experiments.

### Experiment 1: Retention Quality

Fixes the database and varies the retention budget (`B`) and the scoring parameter (`alpha`) to evaluate reduction quality.

- **Single query log:** Runs the experiment using one query log.
- **Two query logs:** Runs the experiment separately for each query log and generates a comparison of the results. This is for our two kind of distributions: uniform and skewed.

### Experiment 2: Quality and Execution Time

Evaluates the reduction across multiple databases and query logs using a fixed retention budget (`B`) and scoring parameter (`alpha`). The experiment measures both reduction quality and execution time. Multiple repetitions can be specified to improve the reliability of the results.

### Matching Optimization

Query matching is independent of the retention budget (`B`) and scoring parameter (`alpha`). Therefore, matching is performed only once for each database–query-log pair, and the results are reused across all configurations.

### Usage

Run Experiment 1 with a single query log:

```bash
python experiments.py --exp 1 --database db1.txt --qlogs q1.log
```

Run Experiment 1 with two query logs (e.g., uniform and skewed):

```bash
python experiments.py --exp 1 --database db1.txt --qlogs uniform.log skewed.log
```

Specify custom names for the query logs:

```bash
python experiments.py --exp 1 --database db1.txt \
    --qlogs u.log s.log --qlog-names uniform skewed
```

Specify custom budgets and alpha values for Experiment 1:

```bash
python experiments.py --exp 1 --database db1.txt --qlogs q1.log \
    --budgets 0.2 0.4 0.6 0.8 --alphas 0.0 0.5 1.0
```

Run Experiment 2 with multiple datasets:

```bash
python experiments.py --exp 2 --budget 0.5 --alpha 0.5 --repeats 3 \
    --dataset small db_s.txt q_s.log \
    --dataset medium db_m.txt q_m.log \
    --dataset large db_l.txt q_l.log \
    --dataset xl db_xl.txt q_xl.log
```

All experiment results (CSV files and plots) are saved in `results/experiments` by default. Use `--out-dir` to specify a different output directory.

For additional configuration options, run:

```bash
python experiments.py --help
```

### Commands for our actual experiments
The first experiment is executed two times, one for our dataset and one for the baseline (provided):

```python spark_experiments.py --exp 1 --database data/Database01.txt --qlogs data/QLog01.txt --budgets 0.2 0.4 0.6 0.8 --alphas 0.25 0.5 0.75```

and

```python spark_experiments.py --exp 1 --database data/Database13_2.txt --qlogs data/QLog13_2_1.txt data/QLog13_2_2.txt --qlog-names uniform skewed  --budgets 0.2 0.4 0.6 0.8 --alphas 0.25 0.5 0.75```

The second experiment was performed by running the following command:

```python spark_experiments.py --exp 2 --budget 0.5 --alpha 0.75 --repeats 3 --dataset 100_500 data/Database13_1.txt data/QLog13_1_1.txt --dataset 1000_5000 data/Database13_2.txt data/QLog13_2_1.txt --dataset 10000_50000 data/Database13_3.txt data/QLog13_3_1.txt```

### Clean generated data

```sh
make clean
```

### Collaborators
This project was a work of collaboration with [Evita Dologlou](https://github.com/evitadologlou) and [Zoi Dimitriou](https://github.com/zdimitriou).
