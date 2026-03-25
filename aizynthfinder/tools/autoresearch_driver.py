"""Hard-first experiment driver for autoresearch benchmark runs."""
from __future__ import annotations

import argparse
import csv
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from aizynthfinder.tools.autoresearch import run_benchmark_from_spec

RESULTS_COLUMNS = [
    "commit",
    "benchmark",
    "solved_fraction",
    "n_solved",
    "median_first_solution_s",
    "median_first_solution_iter",
    "mean_search_s",
    "benchmark_wall_s",
    "status",
    "description",
]
RESULTS_TSV_TOLERANCE = 1e-6


def _get_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser("aizynth_autoresearch_driver")
    parser.add_argument("--description", required=True, help="short experiment summary")
    parser.add_argument(
        "--commit",
        default="HEAD",
        help="git revision to record, defaults to HEAD",
    )
    parser.add_argument(
        "--results-tsv",
        default="results.tsv",
        help="the TSV file used for local experiment tracking",
    )
    parser.add_argument(
        "--hard-spec",
        default="data/benchmark_hard.yml",
        help="the hard benchmark spec file",
    )
    parser.add_argument(
        "--main-spec",
        default="data/benchmark.yml",
        help="the main regression benchmark spec file",
    )
    parser.add_argument(
        "--hard-output",
        default="benchmark_hard_summary.json",
        help="the hard benchmark summary JSON file",
    )
    parser.add_argument(
        "--hard-details-output",
        default="benchmark_hard_details.json",
        help="the hard benchmark details output file",
    )
    parser.add_argument(
        "--main-output",
        default="benchmark_summary.json",
        help="the main benchmark summary JSON file",
    )
    parser.add_argument(
        "--main-details-output",
        default="benchmark_details.json",
        help="the main benchmark details output file",
    )
    return parser.parse_args()


def _resolve_commit(ref: str) -> str:
    output = subprocess.check_output(
        ["git", "rev-parse", "--short", ref], text=True
    ).strip()
    return output


def _normalize_results_tsv(filename: str) -> None:
    path = Path(filename)
    if not path.exists():
        path.write_text("\t".join(RESULTS_COLUMNS) + "\n")
        return

    lines = path.read_text().splitlines()
    if not lines:
        path.write_text("\t".join(RESULTS_COLUMNS) + "\n")
        return

    header = lines[0].split("\t")
    if len(header) > 1 and header[1] == "benchmark":
        return

    updated_lines = ["\t".join([header[0], "benchmark", *header[1:]])]
    for line in lines[1:]:
        if not line.strip():
            continue
        parts = line.split("\t")
        updated_lines.append("\t".join([parts[0], "main15", *parts[1:]]))
    path.write_text("\n".join(updated_lines) + "\n")


def _read_results_rows(filename: str) -> List[Dict[str, str]]:
    _normalize_results_tsv(filename)
    with open(filename, "r", newline="") as fileobj:
        reader = csv.DictReader(fileobj, delimiter="\t")
        return list(reader)


def _append_results_row(filename: str, row: Dict[str, str]) -> None:
    _normalize_results_tsv(filename)
    with open(filename, "a", newline="") as fileobj:
        writer = csv.DictWriter(fileobj, fieldnames=RESULTS_COLUMNS, delimiter="\t")
        writer.writerow(row)


def _latest_keep_row(rows: List[Dict[str, str]], benchmark: str) -> Optional[Dict[str, str]]:
    for row in reversed(rows):
        if row.get("benchmark") == benchmark and row.get("status") == "keep":
            return row
    return None


def _optional_float(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    return float(value)


def _metrics_from_summary(summary: Dict[str, Any]) -> Dict[str, Optional[float]]:
    return {
        "solved_fraction": float(summary["solved_fraction"]),
        "n_solved": int(summary["n_solved"]),
        "median_first_solution_s": _optional_float(
            summary.get("median_first_solution_time")
        ),
        "median_first_solution_iter": _optional_float(
            summary.get("median_first_solution_iteration")
        ),
        "mean_search_s": _optional_float(summary.get("mean_search_time")),
        "benchmark_wall_s": _optional_float(summary.get("benchmark_wall_time")),
    }


def _metrics_from_row(row: Dict[str, str]) -> Dict[str, Optional[float]]:
    return {
        "solved_fraction": float(row["solved_fraction"]),
        "n_solved": int(row["n_solved"]),
        "median_first_solution_s": _optional_float(row["median_first_solution_s"]),
        "median_first_solution_iter": _optional_float(row["median_first_solution_iter"]),
        "mean_search_s": _optional_float(row["mean_search_s"]),
        "benchmark_wall_s": _optional_float(row["benchmark_wall_s"]),
    }


def _compare_optional_lower(
    candidate: Optional[float], reference: Optional[float]
) -> int:
    if candidate is None and reference is None:
        return 0
    if candidate is None:
        return -1
    if reference is None:
        return 1
    if candidate < reference - RESULTS_TSV_TOLERANCE:
        return 1
    if candidate > reference + RESULTS_TSV_TOLERANCE:
        return -1
    return 0


def _compare_higher(candidate: float, reference: float) -> int:
    if candidate > reference + RESULTS_TSV_TOLERANCE:
        return 1
    if candidate < reference - RESULTS_TSV_TOLERANCE:
        return -1
    return 0


def _compare_by_objective(
    candidate: Dict[str, Optional[float]], reference: Dict[str, Optional[float]]
) -> int:
    comparisons = [
        _compare_higher(
            float(candidate["solved_fraction"]), float(reference["solved_fraction"])
        ),
        _compare_optional_lower(
            candidate["median_first_solution_s"], reference["median_first_solution_s"]
        ),
        _compare_optional_lower(
            candidate["median_first_solution_iter"],
            reference["median_first_solution_iter"],
        ),
        _compare_optional_lower(candidate["mean_search_s"], reference["mean_search_s"]),
    ]
    for comparison in comparisons:
        if comparison != 0:
            return comparison
    return 0


def _passes_main_gate(
    candidate: Dict[str, Optional[float]], reference: Optional[Dict[str, Optional[float]]]
) -> bool:
    if reference is None:
        return True
    return (
        float(candidate["solved_fraction"]) + RESULTS_TSV_TOLERANCE
        >= float(reference["solved_fraction"])
    )


def _format_metric(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, int):
        return str(value)
    return f"{float(value):.6f}"


def _results_row(
    commit: str,
    benchmark: str,
    metrics: Optional[Dict[str, Optional[float]]],
    status: str,
    description: str,
) -> Dict[str, str]:
    metrics = metrics or {}
    return {
        "commit": commit,
        "benchmark": benchmark,
        "solved_fraction": _format_metric(metrics.get("solved_fraction")),
        "n_solved": _format_metric(metrics.get("n_solved")),
        "median_first_solution_s": _format_metric(metrics.get("median_first_solution_s")),
        "median_first_solution_iter": _format_metric(
            metrics.get("median_first_solution_iter")
        ),
        "mean_search_s": _format_metric(metrics.get("mean_search_s")),
        "benchmark_wall_s": _format_metric(metrics.get("benchmark_wall_s")),
        "status": status,
        "description": description,
    }


def main() -> None:
    """Entry point for the aizynth_autoresearch_driver command."""
    args = _get_arguments()
    commit = _resolve_commit(args.commit)
    rows = _read_results_rows(args.results_tsv)
    hard_reference_row = _latest_keep_row(rows, "hard10")
    main_reference_row = _latest_keep_row(rows, "main15")
    hard_reference = (
        _metrics_from_row(hard_reference_row) if hard_reference_row is not None else None
    )
    main_reference = (
        _metrics_from_row(main_reference_row) if main_reference_row is not None else None
    )

    hard_metrics: Optional[Dict[str, Optional[float]]] = None
    main_metrics: Optional[Dict[str, Optional[float]]] = None

    try:
        hard_payload = run_benchmark_from_spec(
            spec_filename=args.hard_spec,
            output_filename=args.hard_output,
            details_output_filename=args.hard_details_output,
        )
        hard_metrics = _metrics_from_summary(hard_payload["summary"])
    except Exception:  # pylint: disable=broad-except
        _append_results_row(
            args.results_tsv,
            _results_row(commit, "hard10", None, "crash", args.description),
        )
        raise

    hard_improved = hard_reference is None or _compare_by_objective(
        hard_metrics, hard_reference
    ) > 0
    if not hard_improved:
        _append_results_row(
            args.results_tsv,
            _results_row(commit, "hard10", hard_metrics, "discard", args.description),
        )
        print("Decision: discard (hard10 did not improve); main15 skipped")
        return

    try:
        main_payload = run_benchmark_from_spec(
            spec_filename=args.main_spec,
            output_filename=args.main_output,
            details_output_filename=args.main_details_output,
        )
        main_metrics = _metrics_from_summary(main_payload["summary"])
    except Exception:  # pylint: disable=broad-except
        _append_results_row(
            args.results_tsv,
            _results_row(commit, "hard10", hard_metrics, "crash", args.description),
        )
        _append_results_row(
            args.results_tsv,
            _results_row(commit, "main15", None, "crash", args.description),
        )
        raise

    final_status = "keep" if _passes_main_gate(main_metrics, main_reference) else "discard"
    _append_results_row(
        args.results_tsv,
        _results_row(commit, "hard10", hard_metrics, final_status, args.description),
    )
    _append_results_row(
        args.results_tsv,
        _results_row(commit, "main15", main_metrics, final_status, args.description),
    )
    print(f"Decision: {final_status}")


if __name__ == "__main__":
    main()
