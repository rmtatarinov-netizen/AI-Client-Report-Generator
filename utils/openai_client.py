import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

DEFAULT_PROXY_BASE_URL = "https://api.proxyapi.ru/openai/v1"


class OpenAIRequestError(RuntimeError):
    pass


def create_openai_client(timeout: float | None = None) -> Any:
    api_key = os.getenv("PROXY_API_KEY", "").strip()
    if not api_key:
        raise OpenAIRequestError(
            "Не найден PROXY_API_KEY. Добавьте ключ в файл .env."
        )

    base_url = os.getenv("PROXY_BASE_URL", "").strip() or DEFAULT_PROXY_BASE_URL

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise OpenAIRequestError(
            "Библиотека openai не установлена. Выполните: pip install -r requirements.txt"
        ) from exc

    kwargs: dict[str, Any] = {"api_key": api_key, "base_url": base_url}
    if timeout is not None:
        kwargs["timeout"] = timeout
    return OpenAI(**kwargs)


def describe_openai_error(exc: Exception) -> str:
    try:
        from openai import (
            APIConnectionError,
            APIStatusError,
            AuthenticationError,
            RateLimitError,
        )
    except ImportError:
        return f"Ошибка при обращении к прокси-провайдеру: {exc}"

    if isinstance(exc, AuthenticationError):
        return (
            "Прокси-провайдер отклонил API-ключ. "
            "Проверьте PROXY_API_KEY в файле .env."
        )
    if isinstance(exc, RateLimitError):
        return "Превышен лимит запросов прокси-провайдера. Попробуйте позже."
    if isinstance(exc, APIConnectionError):
        return (
            "Не удалось подключиться к прокси-провайдеру. "
            "Проверьте интернет-соединение и PROXY_BASE_URL."
        )
    if isinstance(exc, APIStatusError):
        response = getattr(exc, "response", None)
        detail = response.text[:500] if response is not None else exc.message
        return f"Прокси-провайдер вернул ошибку {exc.status_code}: {detail}"

    return f"Ошибка при обращении к прокси-провайдеру: {exc}"
