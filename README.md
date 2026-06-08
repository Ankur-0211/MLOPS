# MLOps Batch Job — Rolling Mean Signal Pipeline

A minimal MLOps-style batch job that computes a rolling mean signal over OHLCV data.  
Demonstrates **reproducibility**, **observability**, and **Docker-based deployment readiness**.

---

## Project Structure

```
.
├── run.py            # Main pipeline script
├── config.yaml       # Pipeline configuration
├── data.csv          # Input OHLCV dataset (10,000 rows)
├── requirements.txt  # Python dependencies
├── Dockerfile        # Container definition
├── metrics.json      # Sample output from a successful run
├── run.log           # Sample log from a successful run
└── README.md
```

---

## Quickstart (Local)

### 1. Prerequisites
- Python 3.9+
- pip

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Run the pipeline

```bash
python run.py \
  --input data.csv \
  --config config.yaml \
  --output metrics.json \
  --log-file run.log
```

On Windows:

```powershell
python run.py --input data.csv --config config.yaml --output metrics.json --log-file run.log
```

**Output:**
- Prints `metrics.json` to stdout
- Writes `metrics.json` and `run.log` in the current directory
- Exits with code `0` on success, non-zero on failure

---

## Docker

### Build

```bash
docker build -t mlops-task .
```

### Run

```bash
docker run --rm mlops-task
```

The container includes `data.csv` and `config.yaml`. It runs the full pipeline and prints the metrics JSON to stdout.

---

## Configuration (`config.yaml`)

```yaml
seed: 42
window: 5
version: "v1"
```

| Field     | Type   | Description                      |
|-----------|--------|----------------------------------|
| `seed`    | int    | Random seed for reproducibility  |
| `window`  | int    | Rolling mean window size         |
| `version` | string | Pipeline version tag             |

---

## Pipeline Steps

1. **Load + validate config** — parses YAML, validates required fields, sets numpy random seed
2. **Load + validate dataset** — reads CSV, checks for missing file / empty file / missing `close` column
3. **Rolling mean** — computed over `close` with the configured `window`; first `window-1` rows produce NaN and are excluded from signal computation
4. **Signal generation** — `signal = 1` if `close > rolling_mean`, else `signal = 0`
5. **Metrics + logging** — writes structured JSON output and detailed timestamped logs

---

## Example `metrics.json` (success)

```json
{
  "version": "v1",
  "rows_processed": 10000,
  "metric": "signal_rate",
  "value": 0.499,
  "latency_ms": 87,
  "seed": 42,
  "status": "success"
}
```

## Example `metrics.json` (error)

```json
{
  "version": "v1",
  "status": "error",
  "error_message": "Required column 'close' not found. Available columns: [...]"
}
```

---

## Logging

All steps are logged with timestamps to `run.log`. Includes:
- Job start + config summary
- Rows loaded
- Rolling mean + signal generation steps
- Final metrics summary
- Any errors with full traceback

---

## Error Handling

The pipeline handles these cases cleanly and always writes a `metrics.json`:

| Case | Behaviour |
|---|---|
| Missing input file | Logs error, writes error JSON, exits non-zero |
| Invalid / empty CSV | Logs error, writes error JSON, exits non-zero |
| Missing `close` column | Logs error, writes error JSON, exits non-zero |
| Invalid config structure | Logs error, writes error JSON, exits non-zero |
| Missing config file | Logs error, writes error JSON, exits non-zero |
