import json
import os
import sys
import time
import httpx

BACKEND_URL = os.getenv("BACKEND_URL", "http://backend.dev.svc:8000")
GATEWAY_URL = os.getenv("GATEWAY_URL", "http://litellm.llm-gateway.svc:4000/v1/chat/completions")
LITELLM_MASTER_KEY = os.getenv("LITELLM_MASTER_KEY")
PUSHGATEWAY_URL = os.getenv("PUSHGATEWAY_URL", "http://pushgateway.monitoring.svc:9091")

JUDGE_PROMPT = """You are evaluating an AI system's answer for correctness and groundedness.

Question: {question}
Expected: {expected}
Actual answer: {actual}

Score the actual answer from 0 to 10, where:
- 10 = fully correct and matches expected content
- 0 = completely wrong or hallucinated

Respond with ONLY a single integer from 0-10, nothing else."""


def ask_backend(question: str) -> str:
    resp = httpx.post(f"{BACKEND_URL}/api/chat", json={"message": question}, timeout=60)
    resp.raise_for_status()
    return resp.json()["reply"]


def upload_setup_document(text: str):
    files = {"file": ("setup.txt", text.encode())}
    httpx.post(f"{BACKEND_URL}/api/documents/upload", files=files, timeout=30)


def judge_answer(question: str, expected: str, actual: str) -> int:
    prompt = JUDGE_PROMPT.format(question=question, expected=expected, actual=actual)
    resp = httpx.post(
        GATEWAY_URL,
        headers={"Authorization": f"Bearer {LITELLM_MASTER_KEY}"},
        json={"model": "text-primary", "messages": [{"role": "user", "content": prompt}]},
        timeout=30,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"].strip()
    try:
        return int("".join(filter(str.isdigit, content))[:2] or "0")
    except ValueError:
        return 0


def push_metrics(results: list[dict]):
    avg_score = sum(r["score"] for r in results) / len(results)
    pass_count = sum(1 for r in results if r["score"] >= 6)
    body = (
        f"eval_average_score {avg_score}\n"
        f"eval_pass_rate {pass_count / len(results)}\n"
        f"eval_total_cases {len(results)}\n"
    )
    httpx.post(f"{PUSHGATEWAY_URL}/metrics/job/rag_eval", content=body, timeout=10)


def main():
    with open("golden_dataset.json") as f:
        dataset = json.load(f)

    results = []
    for case in dataset:
        if case.get("setup_document"):
            upload_setup_document(case["setup_document"])
            time.sleep(2)

        actual = ask_backend(case["question"])
        expected = case.get("expected_answer") or ", ".join(case.get("expected_topics", []))
        score = judge_answer(case["question"], expected, actual)

        results.append({"id": case["id"], "question": case["question"], "actual": actual, "score": score})
        print(f"[{case['id']}] score={score}/10 — {actual[:80]}")

    push_metrics(results)

    with open("eval_report.json", "w") as f:
        json.dump(results, f, indent=2)

    avg = sum(r["score"] for r in results) / len(results)
    print(f"\nAverage score: {avg:.1f}/10")
    if avg < 6:
        print("FAILED: average score below threshold (6.0)")
        sys.exit(1)


if __name__ == "__main__":
    main()