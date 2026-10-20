# InsightPilot — Milestone 5.1: Evidence Ledger & Verification Models

## Goal

Create the first layer for Critic & Verification without changing the current Agent execution flow yet. This keeps the new data contracts independently testable before connecting them to Direct Mode and Planned Mode.

## Files added

```text
src/insightpilot/verification/
├── __init__.py
├── evidence.py
└── models.py

tests/test_verification_models.py
```

## 1. `evidence.py`

### `EvidenceExecutionStatus`

A string enum with two values:

- `SUCCESS`: the Tool call produced a non-error result.
- `ERROR`: the Tool result explicitly has `status == "error"`, or the caller supplies an explicit error status.

### `EvidenceItem`

Represents one attempted Tool call. It stores:

| Field | Meaning |
|---|---|
| `evidence_id` | Per-ledger identifier, such as `E0001`. |
| `tool_name` | Registered Tool that was attempted. |
| `arguments` | Snapshot of the Tool arguments. |
| `result` | Snapshot of the returned dictionary, including error payloads. |
| `execution_status` | `success` or `error`. |
| `mode` | Source workflow label, e.g. `preflight`, `direct`, or `planned`. |
| `plan_step_id` | Planning step ID when the Tool came from a plan; otherwise `None`. |
| `created_at` | UTC timestamp captured when the item is created. |

`to_dict()` returns a detached, JSON-compatible representation.

### `EvidenceLedger`

The ledger is designed to be instantiated per user turn. It stores Tool outputs only, not the full source DataFrame.

| Method | Input | Output | Purpose |
|---|---|---|---|
| `add(...)` | Tool name, arguments, result, mode, optional plan step ID/status | `EvidenceItem` | Store one Tool attempt and return a detached copy. |
| `get(evidence_id)` | Evidence ID | `EvidenceItem` or `None` | Find one stored item. |
| `all()` | None | List of `EvidenceItem` | Get a detached list in insertion order. |
| `to_dict()` | None | Dictionary | Serialize all items and count. |
| `to_prompt_context()` | None | JSON string | Produce readable evidence context for the future verifier prompt. |
| `clear()` | None | `None` | Clear the turn's entries and restart its IDs. |
| `len(ledger)` | Ledger object | Integer | Get the number of recorded items. |

The ledger copies arguments and results on write and returns copies on read. Mutating the original Tool result or an object returned from `get()` therefore does not silently rewrite stored evidence.

Common nested Python, NumPy, and Pandas values are normalized for JSON serialization. A Tool error is retained as an error record; it must not be treated as a successful analytical result.

## 2. `models.py`

### Claim-level outcome

`ClaimStatus` contains:

- `VERIFIED`
- `UNSUPPORTED`
- `CONTRADICTED`
- `NOT_VERIFIABLE`

`ClaimVerification` stores a claim ID, text, status, evidence IDs, explanation, and severity.

### Overall verification outcome

`VerificationStatus` contains:

- `VERIFIED`
- `PARTIALLY_VERIFIED`
- `FAILED`
- `INSUFFICIENT_EVIDENCE`

`VerificationReport` contains the overall status, a list of claim-level findings, and a summary.

### Critic decision

`CriticDecision` contains:

- `PASS`
- `NEEDS_REVISION`
- `INSUFFICIENT_EVIDENCE`
- `REVIEW_ERROR`

`CriticIssue` stores an issue type, description, associated claim ID when available, and severity. `CriticReport` stores the decision, summary, issues, and revision instructions.

Both report types expose `to_dict()` to make their enum values and nested records straightforward to serialize and inspect in tests.

## 3. Example

```python
from insightpilot.verification import EvidenceLedger

ledger = EvidenceLedger()
item = ledger.add(
    tool_name="compare_last_two_periods",
    arguments={"date_col": "date", "metric_col": "revenue"},
    result={
        "previous_value": 26000,
        "current_value": 16750,
        "absolute_change": -9250,
        "percentage_change": -35.58,
    },
    mode="planned",
    plan_step_id="step_04",
)

print(item.evidence_id)            # E0001
print(ledger.get("E0001").result)  # Stored result snapshot
print(ledger.to_prompt_context())  # JSON context for future review
```

The returned ID is an identifier, not proof that the claim is correct. The future `CriticVerifier` must compare a claim with the contents and execution status of its referenced evidence.

## 4. Tests added

`tests/test_verification_models.py` covers:

- Stable IDs and insertion order.
- Automatic and explicit error statuses.
- Copy isolation on write and read.
- Missing evidence IDs.
- NumPy/Pandas JSON normalization.
- Clearing a ledger.
- Input contract checks.
- Serialization of verification and critic report models.

## 5. Run tests

From the project root:

```bash
pytest -q
```

Current result for this milestone package: **39 passed**.

## 6. Scope boundary

This milestone adds the evidence storage and report data structures only. It does not yet:

- Modify `DataAnalystAgent` to record Tool outputs.
- Connect the `AnalysisExecutor.on_step` callback to an EvidenceLedger.
- Make LLM review requests.
- Revise or gate final answers.

Those integrations belong to the next step, after the new data contracts are established and tested.
