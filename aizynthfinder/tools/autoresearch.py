"""Benchmark harness for reproducible autoresearch experiments."""
from __future__ import annotations

import argparse
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import yaml

from aizynthfinder.aizynthfinder import AiZynthFinder
from aizynthfinder.utils.files import save_datafile
from aizynthfinder.utils.logging import logger, setup_logger


@dataclass
class BenchmarkSpec:
    """A fixed benchmark definition for autoresearch runs."""

    config: str
    benchmark_smiles: str
    search: Dict[str, Any]
    benchmark_max_wall_time: Optional[float] = None
    policy: Optional[List[str]] = None
    filter: Optional[List[str]] = None
    stocks: Optional[List[str]] = None

    @classmethod
    def from_file(cls, filename: str) -> "BenchmarkSpec":
        with open(filename, "r") as fileobj:
            raw_spec = yaml.safe_load(fileobj) or {}
        if not isinstance(raw_spec, dict):
            raise ValueError("Benchmark spec must be a dictionary")

        benchmark_config = raw_spec.get("benchmark", {})
        if not isinstance(benchmark_config, dict):
            raise ValueError("The 'benchmark' section must be a dictionary")

        search_config = raw_spec.get("search", {})
        if not isinstance(search_config, dict):
            raise ValueError("The 'search' section must be a dictionary")
        missing_keys = [
            key for key in ["time_limit", "iteration_limit"] if key not in search_config
        ]
        if missing_keys:
            raise ValueError(
                "The benchmark spec must fix the search budget by setting "
                + ", ".join(missing_keys)
            )

        base_path = Path(filename).resolve().parent
        config_path = _resolve_path(raw_spec.get("config"), base_path, "config")
        smiles_path = _resolve_path(
            benchmark_config.get("smiles"), base_path, "benchmark.smiles"
        )
        max_wall_time = _normalize_optional_positive_float(
            benchmark_config.get("max_wall_time"), "benchmark.max_wall_time"
        )

        return cls(
            config=config_path,
            benchmark_smiles=smiles_path,
            search=dict(search_config),
            benchmark_max_wall_time=max_wall_time,
            policy=_normalize_selection(raw_spec.get("policy"), "policy"),
            filter=_normalize_selection(raw_spec.get("filter"), "filter"),
            stocks=_normalize_selection(raw_spec.get("stocks"), "stocks"),
        )


def _get_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser("aizynth_autoresearch")
    parser.add_argument(
        "--spec", required=True, help="the benchmark specification yaml file"
    )
    parser.add_argument(
        "--output",
        default="benchmark_summary.json",
        help="the benchmark summary JSON file",
    )
    parser.add_argument(
        "--details-output",
        default="benchmark_details.json",
        help="the per-target benchmark output file (JSON or HDF5)",
    )
    parser.add_argument(
        "--log_to_file",
        action="store_true",
        default=False,
        help="if provided, detailed logging to file is enabled",
    )
    return parser.parse_args()


def _resolve_path(value: Any, base_path: Path, name: str) -> str:
    if not value or not isinstance(value, str):
        raise ValueError(f"Expected '{name}' to be a path string")
    path = Path(value)
    if not path.is_absolute():
        path = base_path / path
    return str(path.resolve())


def _normalize_selection(value: Any, name: str) -> Optional[List[str]]:
    if value is None:
        return None
    if isinstance(value, str):
        return [value]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"Expected '{name}' to be a string or a list of strings")
    return list(value)


def _normalize_optional_positive_float(value: Any, name: str) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Expected '{name}' to be a positive number")
    number = float(value)
    if number <= 0:
        raise ValueError(f"Expected '{name}' to be a positive number")
    return number


def _load_benchmark_smiles(filename: str) -> pd.DataFrame:
    path = Path(filename)
    if path.suffix.lower() == ".csv":
        data = pd.read_csv(path)
        if "smiles" not in data.columns:
            raise ValueError("Benchmark CSV input must contain a 'smiles' column")
        columns = ["smiles"] + [column for column in ["name"] if column in data.columns]
        return data[columns]

    with open(path, "r") as fileobj:
        smiles = [line.strip() for line in fileobj if line.strip()]
    return pd.DataFrame({"smiles": smiles})


def _apply_benchmark_spec(finder: AiZynthFinder, spec: BenchmarkSpec) -> None:
    finder.config._update_from_config({"search": spec.search})
    finder.stock.select(spec.stocks or finder.stock.items)
    finder.expansion_policy.select(spec.policy or finder.expansion_policy.items[0])
    if spec.filter is None:
        finder.filter_policy.select_all()
    elif spec.filter:
        finder.filter_policy.select(spec.filter)
    else:
        finder.filter_policy.deselect()


def _run_single_target(
    finder: AiZynthFinder, row: pd.Series, index: int
) -> Dict[str, Any]:
    smiles = row["smiles"]
    record: Dict[str, Any] = {
        "benchmark_index": index,
        "smiles": smiles,
        "status": "ok",
        "error": "",
        "is_solved": False,
    }
    if "name" in row:
        record["name"] = row["name"]

    time0 = time.time()
    finder.target_smiles = smiles
    try:
        finder.prepare_tree()
        finder.tree_search()
        finder.build_routes()
        record.update(finder.extract_statistics())
    except Exception as err:  # pylint: disable=broad-except
        record["status"] = "failed"
        record["error"] = str(err)
        logger().warning(f"Benchmark failed for target {smiles}: {err}")
    record["target_wall_time"] = time.time() - time0
    return record


def _median_or_none(series: pd.Series) -> Optional[float]:
    if series.empty:
        return None
    value = float(series.median())
    if pd.isna(value):
        return None
    return value


def _mean_or_none(series: pd.Series) -> Optional[float]:
    if series.empty:
        return None
    value = float(series.mean())
    if pd.isna(value):
        return None
    return value


def _summarize_results(data: pd.DataFrame) -> Dict[str, Any]:
    if data.empty:
        return {
            "n_targets": 0,
            "n_successful_runs": 0,
            "n_failed_runs": 0,
            "n_solved": 0,
            "solved_fraction": 0.0,
            "median_first_solution_time": None,
            "median_first_solution_iteration": None,
            "mean_search_time": None,
            "median_search_time": None,
            "mean_target_wall_time": None,
        }

    solved_mask = data["status"].eq("ok") & data["is_solved"].fillna(False)
    solved = data.loc[solved_mask]
    successful = data.loc[data["status"].eq("ok")]

    return {
        "n_targets": int(len(data)),
        "n_successful_runs": int(successful.shape[0]),
        "n_failed_runs": int((data["status"] != "ok").sum()),
        "n_solved": int(solved.shape[0]),
        "solved_fraction": float(solved.shape[0] / len(data)) if len(data) else 0.0,
        "median_first_solution_time": _median_or_none(
            solved["first_solution_time"].dropna()
        ),
        "median_first_solution_iteration": _median_or_none(
            solved["first_solution_iteration"].dropna()
        ),
        "mean_search_time": _mean_or_none(successful["search_time"].dropna()),
        "median_search_time": _median_or_none(successful["search_time"].dropna()),
        "mean_target_wall_time": _mean_or_none(data["target_wall_time"].dropna()),
    }


def _should_stop_before_target(
    benchmark_start_time: float, spec: BenchmarkSpec
) -> bool:
    if spec.benchmark_max_wall_time is None:
        return False
    remaining_time = spec.benchmark_max_wall_time - (time.time() - benchmark_start_time)
    return remaining_time < float(spec.search["time_limit"])


def main() -> None:
    """Entry point for the aizynth_autoresearch command."""
    args = _get_arguments()
    file_level_logging = logging.DEBUG if args.log_to_file else None
    setup_logger(logging.INFO, file_level_logging)

    spec = BenchmarkSpec.from_file(args.spec)
    benchmark_data = _load_benchmark_smiles(spec.benchmark_smiles)
    finder = AiZynthFinder(configfile=spec.config)
    _apply_benchmark_spec(finder, spec)

    logger().info(
        "Starting benchmark with "
        f"{len(benchmark_data)} targets, time_limit={spec.search['time_limit']}, "
        f"iteration_limit={spec.search['iteration_limit']}, "
        f"max_wall_time={spec.benchmark_max_wall_time}"
    )

    time0 = time.time()
    stopped_early = False
    results = []
    for index, (_, row) in enumerate(benchmark_data.iterrows()):
        if _should_stop_before_target(time0, spec):
            stopped_early = True
            elapsed_time = time.time() - time0
            remaining_time = max(
                spec.benchmark_max_wall_time - elapsed_time, 0.0
            )
            logger().warning(
                "Stopping benchmark early before target %s/%s because "
                "remaining wall time %.1fs is below the fixed per-target "
                "time_limit %.1fs",
                index + 1,
                len(benchmark_data),
                remaining_time,
                float(spec.search["time_limit"]),
            )
            break
        results.append(_run_single_target(finder, row, index))
    results_df = pd.DataFrame(results)
    summary = _summarize_results(results_df)
    summary["benchmark_wall_time"] = time.time() - time0
    summary["n_targets_planned"] = int(len(benchmark_data))
    summary["n_targets_run"] = int(len(results_df))
    summary["n_targets_remaining"] = int(len(benchmark_data) - len(results_df))
    summary["stopped_early"] = stopped_early
    summary["max_wall_time"] = spec.benchmark_max_wall_time

    with open(args.output, "w") as fileobj:
        json.dump(
            {
                "spec": {
                    "config": spec.config,
                    "benchmark_smiles": spec.benchmark_smiles,
                    "max_wall_time": spec.benchmark_max_wall_time,
                    "search": spec.search,
                    "policy": spec.policy,
                    "filter": spec.filter,
                    "stocks": spec.stocks,
                },
                "summary": summary,
            },
            fileobj,
            indent=2,
        )
    save_datafile(results_df, args.details_output)

    logger().info(
        f"Benchmark complete: solved {summary['n_solved']}/{summary['n_targets_run']} "
        f"run targets, solved_fraction={summary['solved_fraction']:.3f}"
    )
    logger().info(f"Summary saved to {args.output}")
    logger().info(f"Details saved to {args.details_output}")


if __name__ == "__main__":
    main()
