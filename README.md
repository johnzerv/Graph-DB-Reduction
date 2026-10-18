# Graph Query Project

## Set Up a Virtual Environment

From the project directory, create and activate a virtual environment.

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

Install the project dependencies:

```sh
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Generate the Database and Query Logs

Generate the database and both query-log modes without starting a visualizer:

```sh
python graph.py --query-mode both --no-visualize
```

The default settings create 10 graphs and 50 queries per mode. Change these with `--num-graphs` and `--num-queries`, for example:

```sh
python graph.py --num-graphs 25 --num-queries 100 --query-mode both --no-visualize
```

The database is saved as `Database<group>_<graphs>.txt`. Query logs are saved separately as `QLog<group>_<queries>_uniform.txt` and `QLog<group>_<queries>_skewed.txt` depending on which query distribution was executed. Existing outputs are reused; add `--regenerate` to recreate them.

To create only one query-log mode, use `--query-mode uniform` or `--query-mode skewed`.

## Visualize Graphs

Open the interactive HTML graph selector:

```sh
python graph.py --visualizer html
```

Or use the Matplotlib visualizer:

```sh
python graph.py --visualizer python
```

Enter a graph number when prompted, or `q` to quit. HTML graph files are written to `visualizations/`.

## Evaluate Queries

Evaluate the uniform query log and generate a query-to-graph relation visualization:

```sh
python query_engine.py --query-mode uniform
```

For the skewed log:

```sh
python query_engine.py --query-mode skewed
```

The evaluator expects the database and matching query log to exist. Use the same `--num-graphs`, `--num-queries`, and `--group-number` values used during generation when they differ from the defaults. The HTML relation visualization is written to `visualizations/`.

## Clean Generated Files

Remove generated visualizations, databases, and query logs with:

```sh
make clean
```
