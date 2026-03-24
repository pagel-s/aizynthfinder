# Autoresearch For AiZynthFinder

This adapts the training-oriented `program.md` loop to route-search optimization in
AiZynthFinder.

## Objective

Optimize route-finding performance on a fixed benchmark, not just single-run wall
clock time for one target.

Recommended primary metric order:

1. solved fraction within the fixed search budget
2. median `first_solution_time` for solved targets
3. median `first_solution_iteration` for solved targets
4. mean `search_time`

This matches how the code already reports search statistics in
`aizynthfinder/aizynthfinder.py`.

## Keep Fixed

Use a fixed benchmark for the whole run:

- one base config file with fixed model, stock, and scorer paths
- one fixed SMILES file with representative targets
- one fixed machine or runner type
- one fixed search budget for every run, including both `time_limit` and `iteration_limit`
- one fixed benchmark-level `benchmark.max_wall_time` if you want a hard cap on total run time
- one fixed `search.random_seed` unless you are explicitly measuring robustness

Do not change benchmark inputs during the run. Otherwise the comparisons are not
useful.

## Current Levers In This Repo

The main search surfaces already exposed by the code are:

- `search.algorithm`: MCTS by default, or alternatives such as Retro*
- `search.algorithm_config`: `C`, `use_prior`, cycle pruning, grouping, reward mix
- `search.iteration_limit`, `search.time_limit`, `search.return_first`
- expansion policy selection, including `MultiExpansionStrategy`
- post-processing route scorers

The most relevant files are:

- `aizynthfinder/aizynthfinder.py`
- `aizynthfinder/context/config.py`
- `aizynthfinder/interfaces/aizynthcli.py`
- `aizynthfinder/search/mcts/search.py`
- `aizynthfinder/search/mcts/node.py`
- `aizynthfinder/search/retrostar/search_tree.py`

## Benchmark Loop

Start with a baseline run before changing code.

The repo now has a benchmark harness that reads a fixed YAML spec. An example spec is
available in `contrib/autoresearch.example.yml`, and the current default benchmark is
defined by `data/benchmark.yml` with targets in `data/benchmark.smi`.
That default benchmark currently uses 15 fixed PaRoutes-derived targets, a
per-target budget of `time_limit: 30` and `iteration_limit: 1000`, and a
benchmark-level cap of `benchmark.max_wall_time: 600`.

There is also a secondary hard benchmark in `data/benchmark_hard.yml` with 10
persistent hard or slow targets. Use the main benchmark as the primary gate and
the hard benchmark as a saturation check once the main benchmark starts to
plateau.

Example command:

```bash
aizynth_autoresearch --spec contrib/autoresearch.example.yml --output baseline_summary.json --details-output baseline_details.json
```

For each experiment:

1. make one bounded code or config change
2. rerun the same benchmark with the same seed
3. compare solved fraction, `first_solution_time`, `first_solution_iteration`, and `search_time`
4. keep only changes that improve the benchmark according to the objective order
5. log the result in a TSV file

If `benchmark.max_wall_time` is set, the harness will stop before starting the next
target once the remaining benchmark budget falls below the fixed per-target
`time_limit`. This preserves the fixed per-target search budget instead of shrinking
the last target opportunistically.

Suggested TSV columns:

```text
commit	solved_fraction	median_first_solution_s	mean_search_s	status	description
```

Use `status` values `keep`, `discard`, or `crash`.

For publication tracking, keep a separate tracked log of accepted changes in
`research/accepted_changes.tsv`. That log should contain only the kept
algorithmic changes plus baseline rows for each benchmark tier.

## High-Value Experiments

Good first experiments for this codebase:

- add a staged search schedule: cheap `return_first=True` pass, then a deeper fallback
- compare MCTS and Retro* on the same benchmark
- tune `iteration_limit`, `time_limit`, and MCTS `C`
- test `MultiExpansionStrategy` with a stricter `cutoff_number`
- reduce repeated work in expansion and child instantiation paths
- improve instrumentation so benchmark output includes the right profiling counters

## Why Seed Control Matters

MCTS selection currently uses both `random` and `numpy.random`. Without a fixed seed,
small code changes can look better or worse just because the search walked a different
branch. A reproducible `search.random_seed` setting is therefore a useful first step
for any autonomous experiment loop.
