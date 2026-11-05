import atexit
import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from flask import Flask, jsonify, render_template, request, send_from_directory

from utils.ai_processor import (
    AIProcessingError,
    get_demo_report,
    process_dialog_with_ai,
)
from utils.audio_transcriber import (
    MAX_AUDIO_SIZE,
    AudioFileTooLargeError,
    AudioValidationError,
    TranscriptionError,
    transcribe_mp3,
    validate_audio,
)
from utils.pdf_generator import (
    PDFGenerationError,
    REPORTS_DIR,
    display_path,
    generate_pdf,
)
from utils.transcript_pdf import generate_transcript_pdf

MAX_REPORT_SIZE = 2 * 1024 * 1024
MAX_REQUEST_SIZE = MAX_AUDIO_SIZE + 2 * 1024 * 1024
TASK_TTL_SECONDS = 60 * 60

_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="transcription")
_TASKS: dict[str, "TranscriptionTask"] = {}
_TASKS_LOCK = threading.Lock()

atexit.register(_EXECUTOR.shutdown, wait=False, cancel_futures=True)


class PayloadTooLargeError(ValueError):
    pass


@dataclass
class TranscriptionTask:
    task_id: str
    filename: str
    status: str = "queued"
    stage: str = "queued"
    message: str = "Задача создана"
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    finished_at: datetime | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    http_status: int | None = None

    def to_dict(self) -> dict[str, Any]:
        end_time = self.finished_at or datetime.now()
        payload: dict[str, Any] = {
            "status": self.status,
            "task_id": self.task_id,
            "stage": self.stage,
            "message": self.message,
            "filename": self.filename,
            "created_at": self.created_at.isoformat(timespec="seconds"),
            "updated_at": self.updated_at.isoformat(timespec="seconds"),
            "finished_at": (
                self.finished_at.isoformat(timespec="seconds")
                if self.finished_at
                else None
            ),
            "elapsed_seconds": round(
                (end_time - self.created_at).total_seconds(), 1
            ),
        }
        if self.result is not None:
            payload.update(self.result)
        if self.error is not None:
            payload["error"] = self.error
        if self.http_status is not None:
            payload["http_status"] = self.http_status
        return payload


def _cleanup_tasks() -> None:
    cutoff = datetime.now() - timedelta(seconds=TASK_TTL_SECONDS)
    with _TASKS_LOCK:
        expired = [
            task_id
            for task_id, task in _TASKS.items()
            if task.status in {"completed", "failed"} and task.updated_at < cutoff
        ]
        for task_id in expired:
            _TASKS.pop(task_id, None)


def _create_task(filename: str) -> TranscriptionTask:
    _cleanup_tasks()
    task = TranscriptionTask(task_id=uuid.uuid4().hex, filename=filename)
    with _TASKS_LOCK:
        _TASKS[task.task_id] = task
    return task


def _get_task_payload(task_id: str) -> dict[str, Any] | None:
    with _TASKS_LOCK:
        task = _TASKS.get(task_id)
        return task.to_dict() if task is not None else None


def _update_task(task_id: str, **changes: Any) -> None:
    with _TASKS_LOCK:
        task = _TASKS.get(task_id)
        if task is None:
            return
        for name, value in changes.items():
            setattr(task, name, value)
        now = datetime.now()
        task.updated_at = now
        if task.status in {"completed", "failed"} and task.finished_at is None:
            task.finished_at = now


def _process_transcription(
    task_id: str,
    data: bytes,
    filename: str,
    logger: logging.Logger,
) -> None:
    try:
        _update_task(
            task_id,
            status="processing",
            stage="transcribing",
            message="Отправляем аудио в модель и ждём расшифровку.",
        )
        logger.info("Транскрибация %s: отправка в модель", task_id)

        transcript = transcribe_mp3(data, filename)

        _update_task(
            task_id,
            stage="generating_pdf",
            message="Расшифровка получена, формируем PDF.",
        )
        logger.info("Транскрибация %s: формирование PDF", task_id)

        path = generate_transcript_pdf(transcript)
        result = {
            "file": path.name,
            "path": display_path(path),
            "url": f"/reports/{path.name}",
            "transcript": transcript.to_dict(),
        }
        _update_task(
            task_id,
            status="completed",
            stage="done",
            message="PDF с расшифровкой готов.",
            result=result,
        )
        logger.info("Транскрибация %s: готово, %s", task_id, path.name)
    except AudioFileTooLargeError as exc:
        _update_task(
            task_id,
            status="failed",
            stage="failed",
            message=str(exc),
            error=str(exc),
            http_status=413,
        )
        logger.warning("Транскрибация %s: файл слишком большой", task_id)
    except AudioValidationError as exc:
        _update_task(
            task_id,
            status="failed",
            stage="failed",
            message=str(exc),
            error=str(exc),
            http_status=400,
        )
        logger.warning("Транскрибация %s: ошибка проверки файла", task_id)
    except TranscriptionError as exc:
        _update_task(
            task_id,
            status="failed",
            stage="failed",
            message=str(exc),
            error=str(exc),
            http_status=502,
        )
        logger.warning("Транскрибация %s: ошибка провайдера", task_id)
    except PDFGenerationError as exc:
        _update_task(
            task_id,
            status="failed",
            stage="failed",
            message=str(exc),
            error=str(exc),
            http_status=500,
        )
        logger.exception("Транскрибация %s: ошибка PDF", task_id)
    except Exception as exc:
        _update_task(
            task_id,
            status="failed",
            stage="failed",
            message="Внутренняя ошибка обработки аудиофайла.",
            error=str(exc),
            http_status=500,
        )
        logger.exception("Транскрибация %s: непредвиденная ошибка", task_id)


def _decode_text(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1251"):
        try:
            text = raw.decode(encoding).strip()
        except UnicodeDecodeError:
            continue
        if text:
            return text
    raise ValueError("Не удалось прочитать текст из загруженного файла.")


def _read_request() -> tuple[str, bool]:
    uploaded = request.files.get("file")
    if uploaded is not None:
        if not uploaded.filename:
            raise ValueError("Имя загруженного файла пустое.")
        raw = uploaded.read()
        if len(raw) > MAX_REPORT_SIZE:
            raise PayloadTooLargeError("Файл слишком большой (лимит 2 МБ).")
        demo = request.form.get("demo", "").strip().lower() in {"1", "true", "yes", "on"}
        return _decode_text(raw), demo

    if request.content_length is not None and request.content_length > MAX_REPORT_SIZE:
        raise PayloadTooLargeError("Файл слишком большой (лимит 2 МБ).")

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ValueError(
            "Ожидается JSON с полем transcript или multipart-файл в поле file."
        )

    demo = bool(payload.get("demo"))
    transcript = payload.get("transcript", "")
    if not isinstance(transcript, str):
        raise ValueError("Поле transcript должно быть строкой.")

    transcript = transcript.strip()
    if not demo and not transcript:
        raise ValueError(
            "Передайте текст в поле transcript или установите demo: true."
        )

    return transcript, demo


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = MAX_REQUEST_SIZE
    app.config["JSON_AS_ASCII"] = False
    app.logger.setLevel(logging.INFO)

    @app.errorhandler(413)
    def too_large(_error):
        if request.path == "/api/transcribe":
            message = "Файл слишком большой (лимит 25 МБ)."
        else:
            message = "Файл слишком большой (лимит 2 МБ)."
        return jsonify({"status": "error", "error": message}), 413

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    @app.post("/api/report")
    def create_report():
        try:
            transcript, demo = _read_request()
            data = get_demo_report() if demo else process_dialog_with_ai(transcript)
            path = generate_pdf(data)
        except PayloadTooLargeError as exc:
            return jsonify({"status": "error", "error": str(exc)}), 413
        except ValueError as exc:
            return jsonify({"status": "error", "error": str(exc)}), 400
        except AIProcessingError as exc:
            return jsonify({"status": "error", "error": str(exc)}), 502
        except PDFGenerationError as exc:
            return jsonify({"status": "error", "error": str(exc)}), 500

        return (
            jsonify(
                {
                    "status": "success",
                    "file": path.name,
                    "path": display_path(path),
                    "url": f"/reports/{path.name}",
                    "report": data,
                }
            ),
            201,
        )

    @app.post("/api/transcribe")
    def transcribe_audio():
        uploaded = request.files.get("file")
        if uploaded is None or not uploaded.filename:
            return (
                jsonify(
                    {
                        "status": "error",
                        "error": "Передайте MP3-файл в multipart-поле file.",
                    }
                ),
                400,
            )

        try:
            data = uploaded.read()
            validate_audio(data, uploaded.filename)
        except AudioFileTooLargeError as exc:
            return jsonify({"status": "error", "error": str(exc)}), 413
        except AudioValidationError as exc:
            return jsonify({"status": "error", "error": str(exc)}), 400

        task = _create_task(uploaded.filename)
        _EXECUTOR.submit(
            _process_transcription,
            task.task_id,
            data,
            uploaded.filename,
            app.logger,
        )

        return (
            jsonify(
                {
                    "status": "accepted",
                    "task_id": task.task_id,
                    "status_url": f"/api/transcribe/{task.task_id}",
                    "message": (
                        "Файл принят. Опрашивайте status_url, "
                        "чтобы видеть этап обработки."
                    ),
                }
            ),
            202,
        )

    @app.get("/api/transcribe/<task_id>")
    def transcription_status(task_id: str):
        payload = _get_task_payload(task_id)
        if payload is None:
            return (
                jsonify({"status": "error", "error": "Задача не найдена."}),
                404,
            )
        return jsonify(payload)

    @app.get("/reports/<path:filename>")
    def download_report(filename: str):
        return send_from_directory(str(REPORTS_DIR), filename, as_attachment=False)

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=5000, debug=False)
