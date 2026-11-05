import json
import os
import re
from typing import Any

from .openai_client import (
    OpenAIRequestError,
    create_openai_client,
    describe_openai_error,
)

REPORT_FIELDS = ("client_name", "topic", "main_request", "mood", "next_steps")
DEFAULT_VALUE = "Не указано"

SYSTEM_PROMPT = """Ты — аналитик клиентских диалогов. Проанализируй транскрибацию диалога и верни строго один JSON-объект без markdown, пояснений и дополнительного текста.

JSON должен содержать ровно эти ключи:
- "client_name" — имя клиента или компании; если не названо, верни "Не указано";
- "topic" — краткая тема диалога (до 12 слов);
- "main_request" — главный запрос клиента, 1–3 предложения;
- "mood" — эмоциональное состояние и настрой клиента, кратко;
- "next_steps" — следующие шаги или договорённости, каждый шаг с новой строки.

Пиши на русском языке, если диалог на русском. Не выдумывай факты, которых нет в транскрибации. Все значения должны быть строками."""

DEMO_REPORT = {
    "client_name": "ООО «Ромашка»",
    "topic": "Подключение корпоративного тарифа",
    "main_request": (
        "Клиент хочет подключить корпоративный тариф для 25 сотрудников "
        "и получить счёт на оплату до конца недели."
    ),
    "mood": "Заинтересован, но сомневается в цене",
    "next_steps": (
        "1. Отправить коммерческое предложение с расчётом на 25 сотрудников.\n"
        "2. Согласовать скидку при годовой оплате.\n"
        "3. Выставить счёт после подтверждения тарифа."
    ),
}


class AIProcessingError(RuntimeError):
    pass


def get_demo_report() -> dict[str, str]:
    return dict(DEMO_REPORT)


def _strip_code_fences(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _parse_json(raw: str) -> dict[str, Any]:
    if not raw or not raw.strip():
        raise AIProcessingError("Модель вернула пустой ответ.")

    text = _strip_code_fences(raw)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise AIProcessingError(
                "Не удалось извлечь JSON из ответа модели. "
                f"Фрагмент ответа: {raw[:300]}"
            ) from None
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise AIProcessingError(
                "Модель вернула некорректный JSON. "
                f"Фрагмент ответа: {raw[:300]}"
            ) from exc

    if not isinstance(data, dict):
        raise AIProcessingError("Модель вернула JSON, но это не объект.")

    return data


def normalize_report(data: dict[str, Any]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for field in REPORT_FIELDS:
        value = data.get(field)
        if value is None or not str(value).strip():
            normalized[field] = DEFAULT_VALUE
        else:
            normalized[field] = str(value).strip()
    return normalized


def process_dialog_with_ai(transcript: str) -> dict[str, str]:
    if not transcript or not transcript.strip():
        raise AIProcessingError("Транскрибация диалога пуста.")

    try:
        client = create_openai_client()
    except OpenAIRequestError as exc:
        raise AIProcessingError(str(exc)) from exc

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"

    try:
        response = client.chat.completions.create(
            model=model,
            temperature=0.2,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "Проанализируй транскрибацию диалога и верни JSON.\n\n"
                        f"Транскрибация:\n{transcript.strip()}"
                    ),
                },
            ],
        )
    except Exception as exc:
        raise AIProcessingError(describe_openai_error(exc)) from exc

    content = response.choices[0].message.content if response.choices else None
    if not content:
        raise AIProcessingError("Модель не вернула содержимое ответа.")

    return normalize_report(_parse_json(content))
