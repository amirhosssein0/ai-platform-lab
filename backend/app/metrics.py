from prometheus_client import Counter, Histogram

LLM_REQUESTS_TOTAL = Counter(
    "llm_requests_total", "Total LLM API calls", ["model", "status"]
)
LLM_REQUEST_DURATION_SECONDS = Histogram(
    "llm_request_duration_seconds", "Latency of LLM API calls", ["model"]
)
LLM_PROMPT_TOKENS_TOTAL = Counter(
    "llm_prompt_tokens_total", "Total prompt tokens sent to LLM", ["model"]
)
LLM_COMPLETION_TOKENS_TOTAL = Counter(
    "llm_completion_tokens_total", "Total completion tokens received from LLM", ["model"]
)
LLM_COST_USD_TOTAL = Counter(
    "llm_cost_usd_total", "Estimated cumulative LLM cost in USD", ["model"]
)

# USD per 1M tokens: (prompt_rate, completion_rate). All current models are free-tier.
MODEL_PRICING = {
    "google/gemma-4-26b-a4b-it:free": (0.0, 0.0),
    "openai/gpt-oss-20b:free": (0.0, 0.0),
    "google/gemma-4-31b-it:free": (0.0, 0.0),
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free": (0.0, 0.0),
}


def record_llm_usage(
    model: str,
    duration_seconds: float,
    status: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
):
    LLM_REQUESTS_TOTAL.labels(model=model, status=status).inc()
    LLM_REQUEST_DURATION_SECONDS.labels(model=model).observe(duration_seconds)
    if prompt_tokens:
        LLM_PROMPT_TOKENS_TOTAL.labels(model=model).inc(prompt_tokens)
    if completion_tokens:
        LLM_COMPLETION_TOKENS_TOTAL.labels(model=model).inc(completion_tokens)

    prompt_rate, completion_rate = MODEL_PRICING.get(model, (0.0, 0.0))
    cost = (prompt_tokens / 1_000_000) * prompt_rate + (completion_tokens / 1_000_000) * completion_rate
    if cost:
        LLM_COST_USD_TOTAL.labels(model=model).inc(cost)

def init_cost_series():
    for model in MODEL_PRICING:
        LLM_COST_USD_TOTAL.labels(model=model).inc(0)