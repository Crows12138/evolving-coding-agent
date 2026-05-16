# evolving-coding-agent

A coding agent that **rewrites its own prompt and tools** to solve more bugs over time.

Built on a minimal coding agent runtime (forked from
[nano-claude-code](https://github.com/SafeRL-Lab/nano-claude-code)) with a
**DGM (Darwin Gödel Machine) self-evolution framework** on top.

[中文 README](README.CN.md)

```text
gen 1: train 60% (±5) | hold 50% (±15) | LCB 42.5      ← noisy baseline
gen 2: train 75% (±5) | hold 65% (±10) | LCB 60.0  ✅  ← promote
gen 3: train 80% (±5) | hold 55% (±20) | LCB 45.0  ❌  ← rollback (hold dropped)
```

## What it does

The agent runs a pytest-based eval suite (51 buggy Python programs). After
each evaluation, a **meta-agent** reads the failures and edits the worker
agent's system prompt and tool implementations. Changes that improve the
holdout pass rate are kept; changes that hurt it are rolled back.

## Why it's different

| | Most "agent improves itself" demos | This project |
|---|---|---|
| What evolves | Prompt only | **Prompt + tool implementations** |
| Decision metric | Mean pass rate | **LCB** (median − spread/2, penalizes noisy prompts) |
| Overfit defense | Often none | **Hold-out split** (16/51) — meta-agent never sees holdout failures |
| Meta-agent corruption | Often uses same prompt as worker | **Separate stable META_AGENT_SYSTEM** |
| Cheating defense | Trust the prompt | **Protected files** (eval scripts/config) auto-restored via `git checkout` |
| Crash handling | Silent rollback failure | **Stale-result detection** (no new result file = treated as worst score) |
| Repeatability | Single run per generation | **N=5 runs per generation**, treated as random-variable samples |

## Quick start

### 1. Install

```bash
pip install -r requirements.txt
```

### 2. Set up a local LLM (default: Ollama + Qwen3.5)

```bash
# Install Ollama: https://ollama.com/download
ollama pull qwen3.5:9b

# Create a 16K context variant (recommended for local)
echo 'FROM qwen3.5:9b
PARAMETER num_ctx 16384' > /tmp/Modelfile
ollama create qwen3.5-16k -f /tmp/Modelfile
```

You can also use Claude, GPT, Gemini, etc. — see `providers.py`.

### 3. Generate QuixBugs tasks (38 extra bug-fix tasks)

```bash
git clone https://github.com/jkoppel/QuixBugs eval/_quixbugs
python eval/build_quixbugs_tasks.py --verify
```

### 4. Smoke test (5 minutes, 3 tasks)

```bash
python eval/smoke_test.py
```

This temporarily hides all but 3 tasks, runs one generation, and restores
everything. Confirms the pipeline works end-to-end.

### 5. Real run

```bash
# Default: 3 generations, N=5 evaluations per generation
python eval/evolve.py --generations 3 --max-rounds 2

# Faster but less rigorous (N=1)
python eval/evolve.py --generations 3 --quick

# Different model
python eval/evolve.py --model "claude-sonnet-4-6"
```

Expect ~12 hours per generation on a local 9B model with N=5. Plan for
overnight runs.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  EVOLVABLE — DGM can edit these (with rollback guard)        │
│    context.py   — system prompt                              │
│    tools.py     — tool implementations (Read/Write/Edit/...) │
├─────────────────────────────────────────────────────────────┤
│  PROTECTED — git checkout restores any change                │
│    eval/evolve.py, eval/run_eval.py — eval mechanism itself  │
│    config.py — runtime params auto-tuned by model class      │
├─────────────────────────────────────────────────────────────┤
│  Meta layer (the DGM driver)                                 │
│    META_AGENT_SYSTEM — stable prompt for the editor agent    │
│    HOLDOUT_TASKS — 16 tasks the editor never sees fail       │
│    LCB decision — promote/rollback based on holdout LCB      │
└─────────────────────────────────────────────────────────────┘
```

## Key design choices

### 1. Treat eval results as random variables
With `N=5` runs per generation, each prompt produces a distribution. Compare
**distributions** (median + spread), not point estimates. LCB
(`median - spread/2`) prefers stable prompts over flaky high-mean ones.

### 2. Hold-out keeps the meta-agent honest
The meta-agent sees failures from 35 train tasks but never from the 16
holdout tasks. Holdout pass rate drives all promote/rollback decisions —
this catches prompt changes that overfit to specific train tasks.

### 3. The meta-agent uses a separate, immutable prompt
The worker agent's prompt evolves freely. The meta-agent's prompt
(`META_AGENT_SYSTEM`) is hardcoded in `evolve.py` and not in
`EVOLVABLE_FILES`. Worker prompt changes never corrupt the meta-agent's
analysis ability.

### 4. Protected files survive meta-agent mistakes
If the meta-agent edits `eval/evolve.py` or `config.py` (the cheating
attack surface), `_enforce_protected` runs `git checkout` to revert. This
is enforced both after `analyze_and_evolve` and after `fix_broken_files`.

### 5. Crashed eval = worst score
If the eval subprocess crashes before writing a result file (e.g., the
meta-agent broke `tools.py`), the driver detects "no fresh result file"
and treats this generation as a total fail — triggering rollback. Without
this check, evolve would silently read the previous generation's result.

## Eval set

51 Python bug-fix tasks total:

- **13 hand-rolled tasks** (`task_01..task_13`) — diverse: shopping cart,
  state machine, linked list, cache, rate limiter, parser, scheduler, etc.
- **38 QuixBugs tasks** (`qb_*`) — classical algorithms with single-line
  bugs: sorting, graph, DP, search, math, strings.

Each task has `issue.md` (description), one or more `.py` files (with the
bug), and `test_*.py` (pytest verification). The agent's job: read the
issue, find the bug, edit the source until tests pass.

The 16 holdout tasks span: state/parse/numeric/IO from the hand-rolled set,
and sort/graph/search/DP/math/string from QuixBugs.

## Limitations

- **Local 9B model bottleneck**: ~84s per task; N=5 × 51 tasks × 3
  generations ≈ 36 hours. Cloud models (Claude/GPT) cut this 5-10×.
- **No population/parallel search**: this is hill climbing with rollback,
  not true evolutionary search with multiple candidates per generation.
- **Eval set is small**: 51 tasks is enough to see DGM signal but small
  enough that some noise persists.
- **No external benchmark integration**: doesn't currently plug into
  SWE-bench / HumanEvalFix. Adding mini-SWE-agent-style integration is on
  the roadmap.

## Roadmap

- [ ] Adapt to SWE-bench Verified Mini for publishable comparison numbers
- [ ] Population-based search (multiple candidates per generation)
- [ ] Cross-generation memory (selective; risks contamination)
- [ ] Visualize prompt evolution diff across generations

## Acknowledgments

- [nano-claude-code](https://github.com/SafeRL-Lab/nano-claude-code) — base
  coding agent runtime (Apache 2.0)
- [QuixBugs](https://github.com/jkoppel/QuixBugs) — 38 bug-fix tasks (MIT)
- [mini-SWE-agent](https://github.com/SWE-agent/mini-swe-agent) — minimal
  agent design inspiration
- [Darwin Gödel Machine](https://arxiv.org/abs/2504.08066) (Sakana AI) —
  self-evolving agent paper

## License

Apache License 2.0. See `LICENSE` and `NOTICE`.
