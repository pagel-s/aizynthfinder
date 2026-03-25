import csv

from aizynthfinder.tools.autoresearch_driver import main as driver_main


def _payload(
    solved_fraction,
    n_solved,
    median_first_solution_time,
    median_first_solution_iteration,
    mean_search_time,
    benchmark_wall_time,
):
    return {
        "summary": {
            "solved_fraction": solved_fraction,
            "n_solved": n_solved,
            "median_first_solution_time": median_first_solution_time,
            "median_first_solution_iteration": median_first_solution_iteration,
            "mean_search_time": mean_search_time,
            "benchmark_wall_time": benchmark_wall_time,
        }
    }


def _read_rows(filename):
    with open(filename, "r", newline="") as fileobj:
        return list(csv.DictReader(fileobj, delimiter="\t"))


def test_driver_skips_main_when_hard_does_not_improve(
    add_cli_arguments, mocker, tmpdir
):
    results_file = tmpdir / "results.tsv"
    results_file.write(
        "\n".join(
            [
                "commit\tbenchmark\tsolved_fraction\tn_solved\tmedian_first_solution_s\tmedian_first_solution_iter\tmean_search_s\tbenchmark_wall_s\tstatus\tdescription",
                "basehard\thard10\t0.500000\t5\t10.000000\t300.000000\t16.000000\t160.000000\tkeep\thard baseline",
                "basemain\tmain15\t0.800000\t12\t1.200000\t44.500000\t8.100000\t123.000000\tkeep\tmain baseline",
            ]
        )
        + "\n"
    )
    run_patch = mocker.patch(
        "aizynthfinder.tools.autoresearch_driver.run_benchmark_from_spec",
        return_value=_payload(0.5, 5, 10.5, 301.0, 16.5, 161.0),
    )
    mocker.patch(
        "aizynthfinder.tools.autoresearch_driver._resolve_commit",
        return_value="abc1234",
    )
    add_cli_arguments(
        f"--description no_improvement --results-tsv {results_file}"
    )

    driver_main()

    assert run_patch.call_count == 1
    rows = _read_rows(results_file)
    assert rows[-1]["commit"] == "abc1234"
    assert rows[-1]["benchmark"] == "hard10"
    assert rows[-1]["status"] == "discard"
    assert rows[-1]["description"] == "no_improvement"


def test_driver_logs_hard_then_main_on_hard_improvement(
    add_cli_arguments, mocker, tmpdir
):
    results_file = tmpdir / "results.tsv"
    results_file.write(
        "\n".join(
            [
                "commit\tbenchmark\tsolved_fraction\tn_solved\tmedian_first_solution_s\tmedian_first_solution_iter\tmean_search_s\tbenchmark_wall_s\tstatus\tdescription",
                "basehard\thard10\t0.500000\t5\t10.000000\t300.000000\t16.000000\t160.000000\tkeep\thard baseline",
                "basemain\tmain15\t0.800000\t12\t1.200000\t44.500000\t8.100000\t123.000000\tkeep\tmain baseline",
            ]
        )
        + "\n"
    )
    run_patch = mocker.patch(
        "aizynthfinder.tools.autoresearch_driver.run_benchmark_from_spec",
        side_effect=[
            _payload(0.6, 6, 9.0, 250.0, 14.0, 150.0),
            _payload(0.8, 12, 1.4, 45.0, 8.4, 126.0),
        ],
    )
    mocker.patch(
        "aizynthfinder.tools.autoresearch_driver._resolve_commit",
        return_value="def5678",
    )
    add_cli_arguments(
        f"--description paired_run --results-tsv {results_file}"
    )

    driver_main()

    assert run_patch.call_count == 2
    rows = _read_rows(results_file)
    assert rows[-2]["commit"] == "def5678"
    assert rows[-2]["benchmark"] == "hard10"
    assert rows[-2]["status"] == "keep"
    assert rows[-1]["commit"] == "def5678"
    assert rows[-1]["benchmark"] == "main15"
    assert rows[-1]["status"] == "keep"
    assert rows[-1]["description"] == "paired_run"


def test_driver_keeps_when_main_gate_matches_with_tsv_rounding(
    add_cli_arguments, mocker, tmpdir
):
    results_file = tmpdir / "results.tsv"
    results_file.write(
        "\n".join(
            [
                "commit\tbenchmark\tsolved_fraction\tn_solved\tmedian_first_solution_s\tmedian_first_solution_iter\tmean_search_s\tbenchmark_wall_s\tstatus\tdescription",
                "basehard\thard10\t0.600000\t6\t10.924031\t293.500000\t19.895422\t199.916548\tkeep\thard baseline",
                "basemain\tmain15\t0.866667\t13\t1.805017\t53.000000\t9.635446\t145.244698\tkeep\tmain baseline",
            ]
        )
        + "\n"
    )
    run_patch = mocker.patch(
        "aizynthfinder.tools.autoresearch_driver.run_benchmark_from_spec",
        side_effect=[
            _payload(0.6, 6, 6.96048104763031, 293.0, 17.13386778831482, 172.331421),
            _payload(
                13 / 15,
                13,
                0.7675271034240723,
                53.0,
                8.096232398351033,
                123.272949,
            ),
        ],
    )
    mocker.patch(
        "aizynthfinder.tools.autoresearch_driver._resolve_commit",
        return_value="ghi9012",
    )
    add_cli_arguments(
        f"--description rounded_main_gate --results-tsv {results_file}"
    )

    driver_main()

    assert run_patch.call_count == 2
    rows = _read_rows(results_file)
    assert rows[-2]["commit"] == "ghi9012"
    assert rows[-2]["benchmark"] == "hard10"
    assert rows[-2]["status"] == "keep"
    assert rows[-1]["commit"] == "ghi9012"
    assert rows[-1]["benchmark"] == "main15"
    assert rows[-1]["status"] == "keep"
