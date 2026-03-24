import json

import pandas as pd

from aizynthfinder.tools.autoresearch import main as autoresearch_main


class _DummyCollection:
    def __init__(self, items):
        self.items = items
        self.selection = None

    def select(self, value):
        self.selection = value

    def select_all(self):
        self.selection = self.items

    def deselect(self):
        self.selection = []


class _DummyConfig:
    def __init__(self):
        self.updated = None

    def _update_from_config(self, config):
        self.updated = config


class _DummyFinder:
    def __init__(self, configfile, stats):
        self.configfile = configfile
        self._stats = iter(stats)
        self.config = _DummyConfig()
        self.stock = _DummyCollection(["zinc"])
        self.expansion_policy = _DummyCollection(["uspto", "ringbreaker"])
        self.filter_policy = _DummyCollection(["uspto"])
        self.target_smiles = ""

    def prepare_tree(self):
        return None

    def tree_search(self):
        return None

    def build_routes(self):
        return None

    def extract_statistics(self):
        return next(self._stats)


def test_autoresearch_main(add_cli_arguments, mocker, tmpdir):
    benchmark_file = tmpdir / "benchmark.smi"
    benchmark_file.write("c1ccccc1\nCCO\n")
    spec_file = tmpdir / "spec.yml"
    spec_file.write(
        "\n".join(
            [
                "config: config.yml",
                "benchmark:",
                "  smiles: benchmark.smi",
                "policy: uspto",
                "filter:",
                "  - uspto",
                "stocks:",
                "  - zinc",
                "search:",
                "  time_limit: 30",
                "  iteration_limit: 100",
                "  random_seed: 1337",
            ]
        )
    )
    summary_file = tmpdir / "summary.json"
    details_file = tmpdir / "details.json"
    stats = [
        {
            "target": "c1ccccc1",
            "search_time": 3.0,
            "first_solution_time": 1.5,
            "first_solution_iteration": 4,
            "is_solved": True,
        },
        {
            "target": "CCO",
            "search_time": 5.0,
            "first_solution_time": 0,
            "first_solution_iteration": 0,
            "is_solved": False,
        },
    ]
    factory = mocker.Mock(side_effect=lambda configfile: _DummyFinder(configfile, stats))
    mocker.patch("aizynthfinder.tools.autoresearch.AiZynthFinder", factory)
    add_cli_arguments(
        f"--spec {spec_file} --output {summary_file} --details-output {details_file}"
    )

    autoresearch_main()

    assert factory.call_args.kwargs["configfile"] == str(tmpdir / "config.yml")
    with open(summary_file, "r") as fileobj:
        summary = json.load(fileobj)

    assert summary["spec"]["benchmark_smiles"] == str(benchmark_file)
    assert summary["spec"]["max_wall_time"] is None
    assert summary["summary"]["n_targets"] == 2
    assert summary["summary"]["n_targets_planned"] == 2
    assert summary["summary"]["n_targets_run"] == 2
    assert summary["summary"]["n_targets_remaining"] == 0
    assert summary["summary"]["stopped_early"] is False
    assert summary["summary"]["n_solved"] == 1
    assert summary["summary"]["solved_fraction"] == 0.5
    assert summary["summary"]["median_first_solution_time"] == 1.5
    assert summary["summary"]["mean_search_time"] == 4.0

    details = pd.read_json(details_file, orient="table")
    assert list(details["smiles"]) == ["c1ccccc1", "CCO"]
    assert list(details["status"]) == ["ok", "ok"]


def test_autoresearch_stops_before_exceeding_benchmark_wall_time(
    add_cli_arguments, mocker, tmpdir
):
    benchmark_file = tmpdir / "benchmark.smi"
    benchmark_file.write("c1ccccc1\nCCO\nCCC\n")
    spec_file = tmpdir / "spec.yml"
    spec_file.write(
        "\n".join(
            [
                "config: config.yml",
                "benchmark:",
                "  smiles: benchmark.smi",
                "  max_wall_time: 60",
                "policy: uspto",
                "filter:",
                "  - uspto",
                "stocks:",
                "  - zinc",
                "search:",
                "  time_limit: 30",
                "  iteration_limit: 100",
                "  random_seed: 1337",
            ]
        )
    )
    summary_file = tmpdir / "summary.json"
    details_file = tmpdir / "details.json"
    finder_factory = mocker.Mock(
        side_effect=lambda configfile: _DummyFinder(configfile, [])
    )
    mocker.patch("aizynthfinder.tools.autoresearch.AiZynthFinder", finder_factory)
    mocker.patch("aizynthfinder.tools.autoresearch.logger", return_value=mocker.Mock())
    run_single_target = mocker.patch(
        "aizynthfinder.tools.autoresearch._run_single_target",
        return_value={
            "benchmark_index": 0,
            "smiles": "c1ccccc1",
            "status": "ok",
            "error": "",
            "is_solved": True,
            "search_time": 20.0,
            "first_solution_time": 10.0,
            "first_solution_iteration": 5,
            "target_wall_time": 35.0,
        },
    )
    mocker.patch(
        "aizynthfinder.tools.autoresearch.time.time",
        side_effect=[0.0, 0.0, 35.0, 35.0, 35.5],
    )
    add_cli_arguments(
        f"--spec {spec_file} --output {summary_file} --details-output {details_file}"
    )

    autoresearch_main()

    assert run_single_target.call_count == 1
    with open(summary_file, "r") as fileobj:
        summary = json.load(fileobj)

    assert summary["spec"]["max_wall_time"] == 60.0
    assert summary["summary"]["n_targets"] == 1
    assert summary["summary"]["n_targets_planned"] == 3
    assert summary["summary"]["n_targets_run"] == 1
    assert summary["summary"]["n_targets_remaining"] == 2
    assert summary["summary"]["stopped_early"] is True
    assert summary["summary"]["max_wall_time"] == 60.0

    details = pd.read_json(details_file, orient="table")
    assert list(details["smiles"]) == ["c1ccccc1"]
