# autoresearch

This repo uses `program.md` as the operational prompt for autonomous research on
AiZynthFinder itself.

The goal is not to optimize one target molecule by hand. The goal is to improve
retrosynthesis route finding on a fixed benchmark by making algorithmic changes,
running the same benchmark, and keeping only changes that genuinely improve the
benchmark outcome.

## Setup

To set up a new experiment, work with the user to:

1. **Agree on a run tag**: propose a tag based on today's date, for example
   `mar24`. The branch `autoresearch/<tag>` must not already exist.
2. **Create the branch**: `git checkout -b autoresearch/<tag>`.
3. **Read the in-scope files**:
   - `README.md` — repo context.
   - `program.md` — this file.
   - `AUTORESEARCH.md` — benchmark philosophy and metric ordering.
   - `data/benchmark.yml` — fixed benchmark spec.
   - `data/benchmark.smi` and `data/benchmark_manifest.csv` — fixed target set.
   - `aizynthfinder/aizynthfinder.py`
   - `aizynthfinder/context/config.py`
   - `aizynthfinder/context/policy/expansion_strategies.py`
   - `aizynthfinder/context/scoring/scorers.py`
   - `aizynthfinder/search/mcts/search.py`
   - `aizynthfinder/search/mcts/node.py`
   - `aizynthfinder/search/retrostar/search_tree.py`
4. **Verify the benchmark assets exist**: confirm that `data/config.yml` and the
   model, template, filter, and stock files it references are present.
5. **Initialize `results.tsv`**: create it with only the header row. The baseline
   will be written after the first run, using one row per benchmark executed.
6. **Confirm and start**: once setup looks good, begin experimentation.

## Fixed Evaluation Contract

Every experiment in a run must use the same benchmark and the same run budget.

The current fixed benchmark is defined by `data/benchmark.yml` and includes:

- 15 fixed PaRoutes-derived targets in `data/benchmark.smi`
- `time_limit: 30`
- `iteration_limit: 1000`
- `return_first: true`
- `random_seed: 1337`
- `benchmark.max_wall_time: 600`

There is also a secondary hard benchmark in `data/benchmark_hard.yml` with 10
persistent hard or slow targets. Use it to characterize progress once the main
benchmark starts to saturate, or to check whether a change helps on the
persistent hard cases instead of only making easy targets faster.

These files are evaluation infrastructure and must stay fixed during a research
run:

- `data/benchmark.yml`
- `data/benchmark_hard.yml`
- `data/benchmark.smi`
- `data/benchmark_hard.smi`
- `data/benchmark_manifest.csv`
- `data/benchmark_hard_manifest.csv`
- `data/config.yml`
- `aizynthfinder/tools/autoresearch.py`
- `tests/`

Do not modify the benchmark, the benchmark harness, or the tests during the
research loop unless the human explicitly asks to change the evaluation setup.

## Editable Surface

The benchmark contract is fixed. The code surface is not.

Any source code in the repo is fair game if changing it could plausibly improve
route-finding performance on the fixed benchmark. Do not artificially limit
yourself to a tiny file allowlist once progress starts to stall.

The highest-yield files are still likely to be:

- `aizynthfinder/aizynthfinder.py`
- `aizynthfinder/context/config.py`
- `aizynthfinder/context/policy/`
- `aizynthfinder/context/scoring/`
- `aizynthfinder/search/`
- `aizynthfinder/analysis/`

You may also:

- add new source files or helper modules
- add profiling or instrumentation
- add small support utilities for experiment orchestration
- update tests if the code change legitimately requires it
- modify `aizynthfinder/tools/autoresearch.py` if the benchmark semantics stay fixed

Do not widen scope for cosmetic reasons. Widen it only when it helps search
quality, search efficiency, or research velocity under the same benchmark.

## Benchmark Command

Run the fixed benchmark like this:

```bash
python -m aizynthfinder.tools.autoresearch --spec data/benchmark.yml --output benchmark_summary.json --details-output benchmark_details.json > run.log 2>&1
```

Do not use a different spec during the run.

The hard benchmark uses:

```bash
python -m aizynthfinder.tools.autoresearch --spec data/benchmark_hard.yml --output benchmark_hard_summary.json --details-output benchmark_hard_details.json > run_hard.log 2>&1
```

Use the hard benchmark as a secondary characterization benchmark, not as a
replacement for the primary one unless the human explicitly changes the policy.

## Objective

The benchmark is judged in this exact order:

1. higher `solved_fraction`
2. lower `median_first_solution_time`
3. lower `median_first_solution_iteration`
4. lower `mean_search_time`

Use the values from `benchmark_summary.json`.

If two runs are effectively tied on these metrics, prefer the simpler change.

Do not confuse activity with progress. Repeated tiny hyperparameter changes
along the same line of attack are a failure mode, not a research strategy.

Once the main benchmark is already solving most targets, treat progress on the
persistent-unsolved and slow-solved targets as the most valuable kind of
progress. Do not spend the default research budget shaving tiny amounts of time
from already easy sub-second cases unless the same mechanism is likely to help
the hard cases too.

## What You Can Change

Anything that improves research progress under the fixed benchmark is fair game,
including both algorithmic changes and support changes around the algorithm.

Examples:

- MCTS selection behavior such as `C`, prior usage, grouping, reward handling
- expansion width, branching control, and pruning logic
- search depth handling and staged search schedules
- transposition tables, duplicate detection, and state or subtree reuse
- stall detection with rescue stages or fallback search behavior
- reaction filtering and cycle pruning
- multi-policy balancing, including RingBreaker combinations
- Retro* versus MCTS, or hybrid search strategies
- caching, batching, and child-instantiation efficiency
- batched frontier expansion or filter evaluation across multiple nodes
- route scoring that guides search more effectively
- depth-aware, prior-aware, or target-aware progressive widening
- benchmark instrumentation, profiling counters, and result summaries
- small framework changes that let future experiments run faster or more safely

Pure scalar hyperparameter changes are allowed, but they are not the default
mode once the obvious baseline sweeps have been explored.

## What You Cannot Change

- the target set
- the benchmark objective order
- the benchmark seed
- the benchmark wall-clock budget
- the meaning of the benchmark metrics
- model, stock, or filter assets used by the benchmark
- dependency files or package installation unless the human explicitly asks

You may improve the benchmark harness, but not in ways that move the goalposts.
The point is to improve the system under a fixed evaluation, not to make the
evaluation easier to win.

## Output Files

The benchmark writes:

- `benchmark_summary.json` — benchmark-level metrics and the exact fixed spec
- `benchmark_details.json` — per-target results
- `run.log` — full command output

The source of truth for keep/discard decisions is `benchmark_summary.json`.

For publication tracking, also maintain `research/accepted_changes.tsv` for
every kept algorithmic change.

## Logging Results

When an experiment finishes, append one row to `results.tsv` for each benchmark
that was executed.

Use tab-separated columns with this header:

```text
commit	benchmark	solved_fraction	n_solved	median_first_solution_s	median_first_solution_iter	mean_search_s	benchmark_wall_s	status	description
```

Use:

- `keep` if the experiment improves the benchmark and becomes the new base
- `discard` if it does not improve the benchmark
- `crash` if it fails to run or does not produce a valid summary

Use `benchmark` values such as `main15` and `hard10`.

Do not commit `results.tsv`.

Do commit `research/accepted_changes.tsv`. That file is the tracked summary of
accepted changes for later paper writing.

## The Experiment Loop

The first run must always be the baseline with no code changes.

Then loop forever:

1. Check the current branch and current best commit.
2. Make one bounded algorithmic change in the editable surface.
3. Commit the change.
4. Run the fixed benchmark command and redirect output to `run.log`.
5. If `benchmark_summary.json` is missing or invalid, inspect `tail -n 50 run.log`.
6. If the failure is trivial and directly caused by the last edit, fix it and re-run once.
7. Record one row per benchmark run in `results.tsv`.
8. Compare against the current best using the objective order above.
9. If the new run is better, keep the commit and continue from there.
10. If it is worse or tied without a compelling simplification win, revert to the previous best commit.

If a change is kept, append one row to `research/accepted_changes.tsv` with:

- the kept algorithm commit
- its parent commit
- the benchmark name, for example `main15` or `hard10`
- the benchmark metrics
- the files changed
- a short change summary
- a one-sentence mechanistic hypothesis for why it helped

This tracked log is part of the research artifact and should stay publication-friendly.

## Plateau Strategy

If the main benchmark is plateaued and the hard benchmark still has persistent
unsolved targets, optimize for one of these outcomes:

- solve one previously persistent-unsolved hard target
- materially reduce search time on a hard target that is currently around `10s`
  to `30s`
- introduce a structural search improvement that is likely to transfer to both
  benchmarks

Do not treat a small speedup on already easy targets as sufficient evidence that
the search algorithm is genuinely improving.

## Anti-Local-Optimum Rules

Do not get stuck doing the same experiment in slightly different numbers.

- Do not run long sequences of single-knob sweeps unless you have a very specific hypothesis.
- If two consecutive experiments are just small variations of the same idea, the next one must be qualitatively different.
- If three consecutive experiments fail to improve the benchmark, the next one must change control flow, search staging, data structures, or caching behavior rather than just retuning constants.
- If a line of attack gives only weak or noisy gains, pivot to a different mechanism rather than continuing to micro-tune it.
- Prefer experiments that change control flow, search structure, pruning behavior, caching, ranking, or state representation over experiments that only nudge constants.
- Before each experiment, state which target cohort it is intended to help: persistent-unsolved, slow-solved, or broad average-case.
- If you touch a hyperparameter, explain why that parameter matters mechanistically for this code path.
- Treat repeated tiny `C`, `max_transforms`, or width-cutoff nudges as low-value unless they are attached to a broader algorithmic change.

## Timeout And Crashes

The benchmark itself has a fixed `benchmark.max_wall_time: 600`, but model load
and startup add overhead. If a run exceeds 12 minutes wall clock, kill it and
treat it as a crash.

If a run crashes:

- fix obvious mistakes quickly if the idea is still sound
- otherwise log the crash and revert

Do not spend many attempts salvaging a weak idea.

## Simplicity Criterion

Do not accumulate complexity for tiny or ambiguous wins.

- a clear benchmark improvement is worth keeping
- an equal benchmark with simpler code can be worth keeping
- a tiny improvement that adds brittle complexity is usually not worth keeping

## Good Next Experiments

At this point, do not over-focus on tiny single-knob sweeps unless there is a
strong reason. Prefer changes that alter search behavior or search-system
efficiency in a more structural way.

Good directions now:

- staged or adaptive search instead of one fixed search schedule
- hybrid strategies that mix MCTS and Retro* style behavior
- better expansion control than static width cutoffs, for example depth-aware or prior-aware branching
- improved duplicate detection, state merging, or subtree reuse
- explicit transposition-table style memoization for equivalent frontier states
- stall detection that escalates from cheap search to more aggressive search on hard targets
- better child selection logic than the current plain UCB-style scoring
- targeted reaction filtering that removes low-value branches without hurting solved fraction
- batching and caching changes that reduce repeated policy, filter, or reactant work
- frontier-level batching so multiple promising nodes can be expanded or filtered together
- route or state rewards that better correlate with actually reaching purchasable leaves
- small structural additions to the benchmark harness that improve research speed, observability, or safety without changing evaluation semantics

Lower-priority directions:

- very small retuning of `C`
- very small retuning of `max_transforms`
- very small retuning of width cutoffs

Those may still help, but they are no longer the most interesting default moves
once the obvious baseline tuning has already been explored.

## Bad Default Behavior

Avoid these patterns unless there is strong evidence for them:

- changing one scalar by a small amount and calling that a research iteration
- retrying the same failed idea with slightly different constants
- spending many runs on local tuning before trying a qualitatively new mechanism
- treating benchmark harness changes as progress when they do not improve research throughput or observability

## Autonomy

Once the experiment loop has begun, do not stop to ask the human whether to keep
going. Continue until manually interrupted.

If you run out of obvious ideas, revisit the editable files, look for repeated
work, compare near-miss experiments in `results.tsv`, and continue iterating.
