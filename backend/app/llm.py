import os
import json
import time
import httpx

from app.metrics import record_llm_usage

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://litellm.llm-gateway.svc:4000/v1/chat/completions")
LITELLM_MASTER_KEY = os.getenv("LITELLM_MASTER_KEY")

MAX_IMAGE_SIZE_MB = 8
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


def validate_image(data_url: str) -> None:
    if not data_url.startswith("data:"):
        raise ValueError("Invalid image format")
    header, _, encoded = data_url.partition(",")
    mime = header.split(";")[0].replace("data:", "")
    if mime not in ALLOWED_IMAGE_TYPES:
        raise ValueError(f"Unsupported image type: {mime}")
    size_mb = (len(encoded) * 3 / 4) / (1024 * 1024)
    if size_mb > MAX_IMAGE_SIZE_MB:
        raise ValueError(f"Image exceeds {MAX_IMAGE_SIZE_MB}MB limit")


def _build_messages(message: str, image_data_url: str | None):
    if not image_data_url:
        return [{"role": "user", "content": message}]
    return [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": message},
                {"type": "image_url", "image_url": {"url": image_data_url}},
            ],
        }
    ]


def _headers():
    return {"Authorization": f"Bearer {LITELLM_MASTER_KEY}"}


async def get_llm_reply(message: str, image_data_url: str | None = None) -> str:
    model = "vision" if image_data_url else "text-primary"
    start = time.monotonic()
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            GATEWAY_URL,
            headers=_headers(),
            json={"model": model, "messages": _build_messages(message, image_data_url)},
        )
        response.raise_for_status()
        data = response.json()
        usage = data.get("usage", {})
        record_llm_usage(
            model=model,
            duration_seconds=time.monotonic() - start,
            status="success",
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
        )
        return data["choices"][0]["message"]["content"]


async def _stream_from_model(message: str, image_data_url: str | None, model: str):
    start = time.monotonic()
    prompt_tokens = 0
    completion_tokens = 0
    async with httpx.AsyncClient(timeout=60) as client:
        async with client.stream(
            "POST",
            GATEWAY_URL,
            headers=_headers(),
            json={
                "model": model,
                "messages": _build_messages(message, image_data_url),
                "stream": True,
                "stream_options": {"include_usage": True},
            },
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue
                payload = line[len("data: "):]
                if payload == "[DONE]":
                    break
                chunk = json.loads(payload)
                usage = chunk.get("usage")
                if usage:
                    prompt_tokens = usage.get("prompt_tokens", 0)
                    completion_tokens = usage.get("completion_tokens", 0)
                choices = chunk.get("choices") or []
                if choices:
                    delta = choices[0].get("delta", {}).get("content")
                    if delta:
                        yield delta
    record_llm_usage(
        model=model,
        duration_seconds=time.monotonic() - start,
        status="success",
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )


async def stream_llm_reply(message: str, image_data_url: str | None = None):
    model = "vision" if image_data_url else "text-primary"
    async for delta in _stream_from_model(message, image_data_url, model):
        yield delta