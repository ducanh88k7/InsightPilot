# InsightPilot — Milestone 5.2: Evidence Integration & Critic Verification

## Goal

Connect the Milestone 5.1 evidence/report structures to the existing Agent so final answers can be checked against Tool results. This milestone adds review and one bounded revision cycle to both Direct Mode and Planned Mode.

## Architecture after this milestone

```text
User question
  |
  v
DataAnalystAgent.ask() -- creates a new EvidenceLedger for this turn
  |
  +--> Preflight: profile / derive revenue -------------------+
  |                                                          |
  +--> Direct Mode: Agent -> ToolRegistry -> Tool result -----+--> EvidenceLedger
  |                                                          |
  +--> Planned Mode: Planner -> AnalysisPlan -> Executor -----+
                         Executor callback records each attempted step
  |
  v
Draft answer
  |
  v
CriticVerifier.review(question, draft, evidence, profile, plan)
  |       - requests structured JSON from the LLM
  |       - does not expose analysis Tools
  |       - validates evidence IDs and execution statuses locally
  |
  +--> PASS ------------------------------> final answer
  |
  +--> NEEDS_REVISION / INSUFFICIENT_EVIDENCE
  |       |
  |       v
  |    One rewrite request with tools=[]
  |       |
  |       v
  |    One final Critic review
  |       |
  |       v
  |    final answer + caveat if unresolved
  |
  +--> REVIEW_ERROR ----------------------> draft + verification warning
```

No analysis Tool is executed during revision or review, so this path will not accidentally re-run analyses or side effects.

## Files added or changed

### Added: `src/insightpilot/verification/critic.py`

Key parts:

- `REVIEW_SCHEMA`: structured output contract for claim-level verification and the Critic decision.
- `CriticVerifier._input(...)`: packages the question, draft, profile, plan and evidence ledger into the review context. It explicitly treats dataset values as data rather than instructions and requests no Tools.
- `CriticVerifier.review(...)`: returns deterministic `INSUFFICIENT_EVIDENCE` when the ledger has no successful Tool evidence. Otherwise, it submits one structured review request.
- `CriticVerifier._validated_reports(...)`: parses the report, checks each evidence ID, rejects unknown or failed Tool results as evidence, recalculates the overall verification status and downgrades an unsafe `PASS` decision.

The LLM identifies semantic claims, but local code validates evidence references and review contracts. This is a bounded verification layer, not a mathematical guarantee that every model judgement is correct.

### Changed: `src/insightpilot/agent/core.py`

#### Evidence capture

- Each call to `DataAnalystAgent.ask()` creates a new `EvidenceLedger`.
- `_execute_tool(...)` stores both successful Tool results and error results.
- `_preflight(...)` records profiling and revenue-derivation results using `mode="preflight"`.
- Direct Mode stores results using `mode="direct"`, including malformed Tool arguments as error evidence.
- The Planned Mode step callback stores completed/failed step outputs using `mode="planned"` and the actual `plan_step_id`.

#### Review and revision

- `_build_critic(...)` creates `CriticVerifier` with the per-turn counted client.
- `_review_and_revise(...)` checks the draft before returning the response.
- `_revise_answer(...)` can make one rewrite request with `tools=[]`; it receives existing evidence, not permission to execute Tools.
- The revised answer is reviewed once more. The Agent never enters a revision loop.
- If review or revision fails, the Agent attaches a user-visible caution and stores the error/decision in the result instead of falsely reporting `PASS`.
- If there is no successful Tool evidence, the verifier returns `INSUFFICIENT_EVIDENCE` without spending a review API call.

#### Added to `AgentResult`

| Field | Meaning |
|---|---|
| `evidence_ledger` | JSON-compatible evidence snapshot for the current turn. |
| `verification_report` | Claim-level findings and overall verification status. |
| `critic_report` | Decision, issues and revision instructions. |
| `review_attempts` | Number of review passes performed by the orchestrator (normally 1, or 2 after a revision). |

The existing metrics remain available. `llm_requests` now includes Critic and revision requests, so answers may involve more API calls than Milestone 4.5.

### Tests

- `tests/test_critic.py`: successful structured review, unknown evidence IDs, failed Tool evidence, no-evidence short-circuit, malformed JSON.
- `tests/test_agent.py`: evidence capture in Direct/Planned/preflight, review failure, one revision, unresolved issues after revision, and no successful evidence.
- Previous Milestone 1–4.5 tests remain in the suite.

## Expected behavior examples

### Supported statement

A successful comparison Tool returns a month-over-month change of `-35.58%`. The Critic can mark the claim verified only when it cites a successful evidence record from this turn.

### Unsupported cause

If the draft says the decline was caused by poor advertising but no evidence covers advertising, the Critic should request a revision. The revised answer should state the observed decline and explain that the available dataset does not establish its cause.

### Unknown or failed evidence

An invented evidence ID, or an ID whose Tool call failed, cannot support a `VERIFIED` claim. If all Tool calls failed, verification is short-circuited to `INSUFFICIENT_EVIDENCE` and the Agent warns the user.

## API costs

Tests and the offline demos use fake/deterministic components and make no real LLM API calls. In live use, a turn with successful Tool evidence normally adds one Critic request. A turn that requires revision adds a rewrite request and a second Critic request. The Critic and revision calls can incur API usage charges. A live demo also needs an available model ID in `OPENAI_MODEL` and a valid `OPENAI_API_KEY`.

## Run checks locally

From the project root, install the project in editable mode once (works with the `src/` layout):

```bash
python -m pip install -e .
pytest -q
python run_demo.py
python run_tools_demo.py
python run_planning_demo.py
```

Alternatively, set `PYTHONPATH=src` for the demo commands if you do not want an editable install.

The live Agent demo is `python run_agent_demo.py`; only run it when you intentionally want to make API requests.

## Scope limits

- Critic review is LLM-assisted; it does not prove semantic correctness with mathematical certainty.
- Evidence is collected from Tool outputs, not by copying the full source DataFrame into each review prompt.
- This first version has one revision pass only; there is no unbounded retry loop.
- A future milestone can add deterministic verification rules for specific numeric claims and improved evidence-to-claim matching.
