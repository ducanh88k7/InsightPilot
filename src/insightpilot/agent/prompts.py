from __future__ import annotations

import json
from typing import Any

BASE_SYSTEM_PROMPT = """
You are InsightPilot, an AI Data Analyst Agent.

Your job is to answer questions about the currently loaded dataset by using the
available analysis tools. Never invent numerical results. If a question requires
calculation, use a tool and base the answer on its returned data.

Follow these rules:
1. First understand the user's analytical goal.
2. Use the provided dataset profile as the first source of truth about available columns and types.
3. Reuse an existing revenue column when available.
4. If the user asks about revenue or sales and price + quantity are available,
   use the revenue column or the revenue tool before revenue-based analysis.
5. Use the smallest number of tools needed to answer correctly.
6. After receiving a tool result, decide whether another tool is necessary.
7. If a tool returns an error, inspect the error and recover by correcting arguments
   or choosing a more appropriate tool when possible.
8. Clearly distinguish observed facts from interpretations.
9. If the dataset cannot support a conclusion, say so instead of guessing.
10. Answer in the same language as the user's question (Vietnamese for Vietnamese questions,
    English for English questions, and so on).
11. Do not expose hidden reasoning or chain-of-thought. Give concise conclusions,
    mention the relevant calculations/evidence, and state uncertainty when necessary.
""".strip()


def build_system_prompt(profile: dict[str, Any] | None = None) -> str:
    """Tạo system prompt kèm bản tóm tắt ngắn gọn về dataset từ bước preflight."""
    if not profile:
        return BASE_SYSTEM_PROMPT

    snapshot = json.dumps(profile, ensure_ascii=False, indent=2)
    return (
        f"{BASE_SYSTEM_PROMPT}\n\n"
        "CURRENT DATASET PREFLIGHT PROFILE:\n"
        f"{snapshot}\n\n"
        "Treat this profile as descriptive metadata, not as a substitute for exact calculations. "
        "Use analysis tools for numerical answers."
    )


# Giữ mặc định để tương thích ngược với code và test đang import trực tiếp SYSTEM_PROMPT.
SYSTEM_PROMPT = BASE_SYSTEM_PROMPT


def build_plan_synthesis_prompt(
    question: str,
    profile: dict[str, Any] | None,
    plan: dict[str, Any],
    step_results: dict[str, dict[str, Any]],
) -> list[dict[str, str]]:
    """Tạo prompt không dùng Tool để tổng hợp kết quả của kế hoạch đã thực thi."""
    profile_text = json.dumps(profile or {}, ensure_ascii=False, indent=2)
    plan_text = json.dumps(plan, ensure_ascii=False, indent=2)
    results_text = json.dumps(step_results, ensure_ascii=False, indent=2, default=str)

    system = (
        "You are the final synthesis component of InsightPilot. "
        "Answer the user's analytical question using only the verified results from the executed plan. "
        "Do not invent calculations, columns, or facts. Distinguish observed results from interpretation. "
        "If the plan is partial or failed, clearly say what was completed and what could not be established. "
        "Answer in the same language as the user's question. Do not expose hidden reasoning."
    )
    user = (
        f"USER QUESTION:\n{question}\n\n"
        f"DATASET PROFILE:\n{profile_text}\n\n"
        f"EXECUTED PLAN:\n{plan_text}\n\n"
        f"VERIFIED STEP RESULTS:\n{results_text}\n\n"
        "Produce a concise, useful final answer with the key evidence and conclusions."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
