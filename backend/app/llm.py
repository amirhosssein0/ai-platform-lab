import os
import httpx

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


async def get_llm_reply(message: str) -> str:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            OPENROUTER_URL,
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
            json={
                "model": "openrouter/free",
                "messages": [{"role": "user", "content": message}],
            },
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]