"""
MLOps Batch Job — Rolling Mean Signal Pipeline
"""

import argparse
import io
import json
import logging
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import yaml


def setup_logging(log_file: str) -> logging.Logger:
    logger = logging.getLogger("mlops_job")
    logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S"
    )

    fh = logging.FileHandler(log_file)
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)

    ch = logging.StreamHandler(sys.stderr)
    ch.setLevel(logging.INFO)
    ch.setFormatter(formatter)

    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger


def write_metrics(output_path: str, payload: dict) -> None:
    with open(output_path, "w") as f:
        json.dump(payload, f, indent=2)


def load_config(config_path: str, logger: logging.Logger) -> dict:
    logger.info(f"Loading config from: {config_path}")

    if not Path(config_path).exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    if not isinstance(config, dict):
        raise ValueError("Config file is not a valid YAML mapping.")

    required_fields = ["seed", "window", "version"]
    for field in required_fields:
        if field not in config:
            raise ValueError(f"Missing required config field: '{field}'")

    if not isinstance(config["seed"], int):
        raise ValueError("Config field 'seed' must be an integer.")
    if not isinstance(config["window"], int) or config["window"] < 1:
        raise ValueError("Config field 'window' must be a positive integer.")
    if not isinstance(config["version"], str):
        raise ValueError("Config field 'version' must be a string.")

    logger.info(
        f"Config validated — seed={config['seed']}, "
        f"window={config['window']}, version={config['version']}"
    )
    return config


def load_dataset(input_path: str, logger: logging.Logger) -> pd.DataFrame:
    logger.info(f"Loading dataset from: {input_path}")

    if not Path(input_path).exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    try:
        with open(input_path, "r", encoding="utf-8") as f:
            raw_lines = f.readlines()

        # Strip surrounding quotes from each line if present (Google Sheets export quirk)
        cleaned_lines = []
        for line in raw_lines:
            line = line.strip()
            if line.startswith('"') and line.endswith('"'):
                line = line[1:-1]
            cleaned_lines.append(line)

        cleaned_content = "\n".join(cleaned_lines)
        df = pd.read_csv(io.StringIO(cleaned_content))
    except Exception as e:
        raise ValueError(f"Failed to parse CSV: {e}")

    if df.empty:
        raise ValueError("Input CSV is empty.")

    if "close" not in df.columns:
        raise ValueError(
            f"Required column 'close' not found. "
            f"Available columns: {list(df.columns)}"
        )

    if df["close"].isnull().all():
        raise ValueError("Column 'close' contains only null values.")

    logger.info(f"Dataset loaded — {len(df)} rows, columns: {list(df.columns)}")
    return df


def compute_rolling_mean(df: pd.DataFrame, window: int, logger: logging.Logger) -> pd.Series:
    logger.info(f"Computing rolling mean with window={window}")
    rolling_mean = df["close"].rolling(window=window, min_periods=window).mean()
    nan_count = rolling_mean.isna().sum()
    logger.info(
        f"Rolling mean computed — {nan_count} NaN rows "
        f"(first {window - 1} rows excluded from signal)"
    )
    return rolling_mean


def compute_signal(df: pd.DataFrame, rolling_mean: pd.Series, logger: logging.Logger) -> pd.Series:
    logger.info("Generating binary signal (close > rolling_mean → 1, else 0)")
    valid_mask = rolling_mean.notna()
    signal = pd.Series(0, index=df.index, dtype=float)
    signal[valid_mask] = (df.loc[valid_mask, "close"] > rolling_mean[valid_mask]).astype(int)
    signal[~valid_mask] = np.nan

    valid_signals = signal[valid_mask]
    logger.info(
        f"Signal generated — {valid_mask.sum()} valid rows, "
        f"signal_rate={valid_signals.mean():.4f}"
    )
    return signal


def parse_args():
    parser = argparse.ArgumentParser(description="MLOps Rolling Mean Signal Pipeline")
    parser.add_argument("--input",    required=True, help="Path to input CSV file")
    parser.add_argument("--config",   required=True, help="Path to YAML config file")
    parser.add_argument("--output",   required=True, help="Path to output metrics JSON file")
    parser.add_argument("--log-file", required=True, help="Path to log file")
    return parser.parse_args()


def main():
    args = parse_args()
    logger = setup_logging(args.log_file)

    logger.info("=" * 60)
    logger.info("Job started")
    logger.info(f"  input    : {args.input}")
    logger.info(f"  config   : {args.config}")
    logger.info(f"  output   : {args.output}")
    logger.info(f"  log_file : {args.log_file}")
    logger.info("=" * 60)

    start_time = time.time()
    version = "v1"

    try:
        # 1) Load + validate config
        config = load_config(args.config, logger)
        version = config["version"]
        seed = config["seed"]
        window = config["window"]

        np.random.seed(seed)
        logger.info(f"Random seed set: {seed}")

        # 2) Load + validate dataset
        df = load_dataset(args.input, logger)
        rows_loaded = len(df)

        # 3) Rolling mean
        rolling_mean = compute_rolling_mean(df, window, logger)

        # 4) Signal
        signal = compute_signal(df, rolling_mean, logger)

        # 5) Metrics
        valid_signal = signal.dropna()
        signal_rate = round(float(valid_signal.mean()), 4)
        latency_ms = int((time.time() - start_time) * 1000)

        metrics = {
            "version": version,
            "rows_processed": rows_loaded,
            "metric": "signal_rate",
            "value": signal_rate,
            "latency_ms": latency_ms,
            "seed": seed,
            "status": "success"
        }

        write_metrics(args.output, metrics)
        logger.info(f"Metrics written to: {args.output}")
        logger.info(f"  rows_processed : {rows_loaded}")
        logger.info(f"  signal_rate    : {signal_rate}")
        logger.info(f"  latency_ms     : {latency_ms}")
        logger.info("Job completed successfully")
        logger.info("=" * 60)

        print(json.dumps(metrics, indent=2))
        sys.exit(0)

    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        logger.error(f"Job failed: {e}", exc_info=True)
        logger.info("=" * 60)

        error_metrics = {
            "version": version,
            "status": "error",
            "error_message": str(e)
        }
        write_metrics(args.output, error_metrics)
        print(json.dumps(error_metrics, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()