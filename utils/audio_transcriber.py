import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .openai_client import (
    OpenAIRequestError,
    create_openai_client,
    describe_openai_error,
)

DEFAULT_TRANSCRIPTION_MODEL = "gpt-4o-transcribe-diarize"
DEFAULT_TRANSCRIPTION_LANGUAGE = "ru"
MAX_AUDIO_SIZE = 25 * 1024 * 1024
ALLOWED_AUDIO_EXTENSIONS = {".mp3"}
AUDIO_MIME_TYPE = "audio/mpeg"
TRANSCRIPTION_TIMEOUT = 600.0


class TranscriptionError(RuntimeError):
    pass


class AudioValidationError(TranscriptionError):
    pass


class AudioFileTooLargeError(TranscriptionError):
    pass


@dataclass
class TranscriptSegment:
    speaker: str
    start: float
    end: float
    text: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "speaker": self.speaker,
            "start": round(self.start, 2),
            "end": round(self.end, 2),
            "text": self.text,
        }


@dataclass
class TranscriptionResult:
    source_name: str
    model: str
    language: str
    duration: float | None
    text: str
    segments: list[TranscriptSegment] = field(default_factory=list)

    @property
    def duration_display(self) -> str:
        if not self.duration:
            return "Не определена"

        total_seconds = int(round(self.duration))
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        if hours:
            return f"{hours} ч {minutes:02d} мин {seconds:02d} с"
        if minutes:
            return f"{minutes} мин {seconds:02d} с"
        return f"{seconds} с"

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_name": self.source_name,
            "model": self.model,
            "language": self.language,
            "duration": self.duration,
            "duration_display": self.duration_display,
            "text": self.text,
            "segments": [segment.to_dict() for segment in self.segments],
        }


def validate_audio(data: bytes, filename: str) -> str:
    source_name = Path(filename or "").name
    if Path(source_name).suffix.lower() not in ALLOWED_AUDIO_EXTENSIONS:
        raise AudioValidationError("Поддерживаются только MP3-файлы.")

    if not data:
        raise AudioValidationError("Загруженный аудиофайл пуст.")

    if len(data) > MAX_AUDIO_SIZE:
        raise AudioFileTooLargeError(
            "Аудиофайл больше 25 МБ. Загрузите запись меньшего размера."
        )

    return source_name


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _optional_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _display_speaker(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "Спикер"

    match = re.fullmatch(
        r"(?:speaker|спикер)[\s_-]*([A-Za-zА-Яа-я0-9]+)",
        raw,
        flags=re.IGNORECASE,
    )
    if match:
        raw = match.group(1)

    return f"Спикер {raw}"


def _get_field(item: Any, name: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def _merge_segments(segments: list[TranscriptSegment]) -> list[TranscriptSegment]:
    merged: list[TranscriptSegment] = []

    for segment in segments:
        if (
            merged
            and merged[-1].speaker == segment.speaker
            and segment.start - merged[-1].end <= 1.0
        ):
            previous = merged[-1]
            merged[-1] = TranscriptSegment(
                speaker=previous.speaker,
                start=previous.start,
                end=max(previous.end, segment.end),
                text=f"{previous.text} {segment.text}".strip(),
            )
        else:
            merged.append(segment)

    return merged


def _build_segments(response: Any) -> list[TranscriptSegment]:
    raw_segments = _get_field(response, "segments")
    if not raw_segments:
        return []

    segments: list[TranscriptSegment] = []
    for item in raw_segments:
        text = str(_get_field(item, "text", "") or "").strip()
        if not text:
            continue

        segments.append(
            TranscriptSegment(
                speaker=_display_speaker(_get_field(item, "speaker")),
                start=_as_float(_get_field(item, "start")),
                end=_as_float(_get_field(item, "end")),
                text=text,
            )
        )

    segments.sort(key=lambda segment: (segment.start, segment.end))
    return _merge_segments(segments)


def transcribe_mp3(data: bytes, filename: str) -> TranscriptionResult:
    source_name = validate_audio(data, filename)
    data = bytes(data)

    model = (
        os.getenv("TRANSCRIPTION_MODEL", "").strip()
        or DEFAULT_TRANSCRIPTION_MODEL
    )
    language = (
        os.getenv("TRANSCRIPTION_LANGUAGE", "").strip()
        or DEFAULT_TRANSCRIPTION_LANGUAGE
    )

    try:
        client = create_openai_client(timeout=TRANSCRIPTION_TIMEOUT)
    except OpenAIRequestError as exc:
        raise TranscriptionError(str(exc)) from exc

    try:
        response = client.audio.transcriptions.create(
            model=model,
            file=(source_name, data, AUDIO_MIME_TYPE),
            response_format="diarized_json",
            chunking_strategy="auto",
            language=language,
        )
    except Exception as exc:
        raise TranscriptionError(describe_openai_error(exc)) from exc

    segments = _build_segments(response)
    text = str(_get_field(response, "text", "") or "").strip()
    if not text:
        text = " ".join(segment.text for segment in segments).strip()

    if not text:
        raise TranscriptionError("Модель не вернула текст расшифровки.")

    duration = _optional_float(_get_field(response, "duration"))
    if duration is None and segments:
        duration = max(segment.end for segment in segments)

    if not segments:
        segments = [
            TranscriptSegment(
                speaker="Собеседники",
                start=0.0,
                end=duration or 0.0,
                text=text,
            )
        ]

    return TranscriptionResult(
        source_name=source_name,
        model=model,
        language=language,
        duration=duration,
        text=text,
        segments=segments,
    )
