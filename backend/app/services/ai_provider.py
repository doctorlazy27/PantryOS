import os

import httpx


class AIProviderError(RuntimeError):
    pass


def is_configured() -> bool:
    return bool(os.getenv("AI_API_KEY") and os.getenv("AI_MODEL"))


def complete(system_prompt: str, user_prompt: str, max_tokens: int = 400) -> str | None:
    api_key = os.getenv("AI_API_KEY")
    model = os.getenv("AI_MODEL")
    if not api_key or not model:
        return None

    api_url = os.getenv("AI_API_URL", "https://openrouter.ai/api/v1/chat/completions")
    try:
        response = httpx.post(
            api_url,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.2,
                "max_tokens": max_tokens,
            },
            timeout=httpx.Timeout(18.0, connect=5.0),
        )
        response.raise_for_status()
        payload = response.json()
        content = payload["choices"][0]["message"]["content"]
        if not isinstance(content, str) or not content.strip():
            raise AIProviderError("Model provider returned an empty response")
        return content.strip()[:6000]
    except AIProviderError:
        raise
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as error:
        raise AIProviderError("Model provider request failed") from error