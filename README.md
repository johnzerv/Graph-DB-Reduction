# Graph Query Project

This project generates synthetic graph data, creates query logs, evaluates those queries, ranks graphs by match quality, and renders visualizations.

## Project layout

- `graph.py` generates the database and query logs
- `query_engine.py` parses the database and evaluates each query against every graph
- `reducer.py` containes multiple reduction techniques
- `visualizers.py` renders HTML and Matplotlib output
- `main.py` runs the end-to-end evaluation flow

## Set up

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

Install the project dependencies:

```sh
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Generate the database and query logs

Generate the default dataset and both query modes without opening a visualizer:

```sh
python graph.py --query-mode both --no-visualize
```

You can change the generated size:

```sh
python graph.py --num-graphs 25 --num-queries 100 --query-mode both --no-visualize
```

The files are written under `datasets/`:

- `datasets/Database<group>_<graphs>.txt`
- `datasets/QLog<group>_<graphs>_<queries>_<mode>.txt`

Existing files are reused unless you pass `--regenerate`.

To generate only one query mode, use `--query-mode uniform` or `--query-mode skewed`.

## Evaluate queries

Evaluate a query log against the current database:

```sh
python query_engine.py --query-mode uniform
```

Or for the skewed mode:

```sh
python query_engine.py --query-mode skewed
```

The evaluator expects the database and matching query log to exist. Use the same `--num-graphs`, `--num-queries`, and `--group-number` values used during generation if they differ from the defaults.

A quick end-to-end run is also available through:

```sh
python main.py --query-mode skewed
```

## Visualize results

Open the HTML graph selector:

```sh
python graph.py --visualizer html
```

Or use the Matplotlib visualizer:

```sh
python graph.py --visualizer python
```

Enter a graph number when prompted, or `q` to quit. HTML output is written to `visualizations/`.

## Clean generated files

Remove generated output directories and files:

```sh
make clean
```

This removes `visualizations/` and `datasets/` and also clears legacy root-level generated files if they still exist.
