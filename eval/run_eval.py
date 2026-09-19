import json
import os
import sys
import time
import httpx
from pathlib import Path


BACKEND_URL = os.getenv("BACKEND_URL", "http://backend.dev.svc:8000")
GATEWAY_URL = os.getenv(
    "GATEWAY_URL",
    "http://litellm.llm-gateway.svc:4000/v1/chat/completions"
)
LITELLM_MASTER_KEY = os.getenv("LITELLM_MASTER_KEY")
PUSHGATEWAY_URL = os.getenv(
    "PUSHGATEWAY_URL",
    "http://pushgateway.monitoring.svc:9091"
)

REPORT_PATH = "/app/output/eval_report.json"

def load_judge_prompt() -> str:
    lines = Path("prompts/judge_prompt.txt").read_text().splitlines()
    if lines and lines[0].startswith("# version:"):
        lines = lines[1:]
    return "\n".join(lines).lstrip("\n")

JUDGE_PROMPT = load_judge_prompt()


def ask_backend(question: str) -> str:
    resp = httpx.post(
        f"{BACKEND_URL}/api/chat",
        json={"message": question},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["reply"]


def upload_setup_document(text: str):
    files = {"file": ("setup.txt", text.encode())}
    resp = httpx.post(
        f"{BACKEND_URL}/api/documents/upload",
        files=files,
        timeout=30,
    )
    resp.raise_for_status()


def build_expected(case: dict) -> str:
    if case.get("expected_answer"):
        return f"""
Expected answer:
{case["expected_answer"]}
"""

    if case.get("expected_topics"):
        topics = ", ".join(case["expected_topics"])
        return f"""
The answer should explain the question correctly.

Expected topics:
{topics}
"""

    if case.get("expected_behavior") == "should_admit_uncertainty":
        return """
Expected behavior:
The assistant should admit uncertainty because there is no reliable
information about the capital of the fictional country.

It must NOT invent a capital.

A response saying that the information is unknown, unavailable,
or cannot be determined is considered correct.
"""

    return "Evaluate the answer for correctness."


def judge_answer(question: str, expected: str, actual: str) -> int:
    prompt = JUDGE_PROMPT.format(
        question=question,
        expected=expected,
        actual=actual
    )

    resp = httpx.post(
        GATEWAY_URL,
        headers={
            "Authorization": f"Bearer {LITELLM_MASTER_KEY}"
        },
        json={
            "model": "text-primary",
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        },
        timeout=30,
    )

    resp.raise_for_status()

    content = resp.json()["choices"][0]["message"]["content"].strip()

    try:
        digits = "".join(filter(str.isdigit, content))
        return min(int(digits[:2] or "0"), 10)
    except ValueError:
        return 0


def push_metrics(results: list[dict]):
    avg_score = sum(r["score"] for r in results) / len(results)
    pass_count = sum(
        1 for r in results if r["score"] >= 6
    )

    body = (
        f"eval_average_score {avg_score}\n"
        f"eval_pass_rate {pass_count / len(results)}\n"
        f"eval_total_cases {len(results)}\n"
    )

    resp = httpx.post(
        f"{PUSHGATEWAY_URL}/metrics/job/rag_eval",
        content=body,
        timeout=10,
    )
    resp.raise_for_status()


def main():
    with open("golden_dataset.json") as f:
        dataset = json.load(f)

    results = []

    for case in dataset:
        if case.get("setup_document"):
            upload_setup_document(case["setup_document"])
            time.sleep(2)

        actual = ask_backend(case["question"])
        expected = build_expected(case)

        score = judge_answer(
            case["question"],
            expected,
            actual
        )

        results.append({
            "id": case["id"],
            "question": case["question"],
            "actual": actual,
            "score": score
        })

        print(
            f"[{case['id']}] "
            f"score={score}/10 — {actual[:80]}"
        )

    push_metrics(results)

    with open(REPORT_PATH, "w") as f:
        json.dump(results, f, indent=2)

    avg = sum(r["score"] for r in results) / len(results)

    print(f"\nAverage score: {avg:.1f}/10")

    if avg < 6:
        print("FAILED: average score below threshold (6.0)")
        sys.exit(1)

    print("PASSED: average score meets threshold (6.0)")


if __name__ == "__main__":
    main()