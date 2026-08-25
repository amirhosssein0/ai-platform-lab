import os
import json
import httpx

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemma-4-26b-a4b-it:free")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

VISION_MODELS = [
    "google/gemma-4-31b-it:free",
    "google/gemma-4-26b-a4b-it:free",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
]

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


async def get_llm_reply(message: str, image_data_url: str | None = None) -> str:
    models = VISION_MODELS if image_data_url else [OPENROUTER_MODEL]
    last_error: Exception | None = None
    for model in models:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    OPENROUTER_URL,
                    headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
                    json={"model": model, "messages": _build_messages(message, image_data_url)},
                )
                response.raise_for_status()
                return response.json()["choices"][0]["message"]["content"]
        except httpx.HTTPStatusError as e:
            last_error = e
            continue
    raise last_error


async def _stream_from_model(model: str, message: str, image_data_url: str | None):
    async with httpx.AsyncClient(timeout=60) as client:
        async with client.stream(
            "POST",
            OPENROUTER_URL,
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
            json={
                "model": model,
                "messages": _build_messages(message, image_data_url),
                "stream": True,
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
                delta = chunk["choices"][0]["delta"].get("content")
                if delta:
                    yield delta


async def stream_llm_reply(message: str, image_data_url: str | None = None):
    models = VISION_MODELS if image_data_url else [OPENROUTER_MODEL]
    last_error: Exception | None = None
    for model in models:
        try:
            async for delta in _stream_from_model(model, message, image_data_url):
                yield delta
            return
        except httpx.HTTPStatusError as e:
            last_error = e
            continue
    if last_error:
        raise last_error