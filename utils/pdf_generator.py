from datetime import datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"
REPORTS_DIR = BASE_DIR / "reports"
REPORT_TEMPLATE_NAME = "report_template.html"
TRANSCRIPT_TEMPLATE_NAME = "transcript_template.html"

GTK_HINT = (
    "WeasyPrint не может загрузить системные библиотеки GTK/Pango. "
    "Установите GTK3 Runtime командой: "
    "winget install -e --id tschoonj.GTKForWindows"
)


class PDFGenerationError(RuntimeError):
    pass


def _create_environment() -> Environment:
    if not TEMPLATES_DIR.is_dir():
        raise PDFGenerationError(f"Папка шаблонов не найдена: {TEMPLATES_DIR}")

    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_html(template_name: str, context: dict[str, Any]) -> str:
    if not isinstance(context, dict):
        raise PDFGenerationError("Контекст шаблона должен быть словарём.")

    try:
        template = _create_environment().get_template(template_name)
    except Exception as exc:
        raise PDFGenerationError(
            f"Не удалось загрузить шаблон {template_name}: {exc}"
        ) from exc

    return template.render(**context)


def _unique_path(directory: Path, stem: str, suffix: str = ".pdf") -> Path:
    candidate = directory / f"{stem}{suffix}"
    counter = 1
    while candidate.exists():
        candidate = directory / f"{stem}_{counter}{suffix}"
        counter += 1
    return candidate


def generate_pdf(
    data: dict[str, Any],
    output_dir: Path | str | None = None,
    generated_at: datetime | None = None,
    template_name: str = REPORT_TEMPLATE_NAME,
    filename_stem: str | None = None,
    context: dict[str, Any] | None = None,
) -> Path:
    if not isinstance(data, dict):
        raise PDFGenerationError("Данные отчёта должны быть словарём.")

    try:
        from weasyprint import HTML
    except (ImportError, OSError) as exc:
        raise PDFGenerationError(GTK_HINT) from exc

    timestamp = generated_at or datetime.now()
    directory = Path(output_dir) if output_dir else REPORTS_DIR
    directory.mkdir(parents=True, exist_ok=True)

    render_context = dict(context) if context is not None else {"report": data}
    render_context.setdefault("generated_at", timestamp)

    html = render_html(template_name, render_context)
    stem = filename_stem or timestamp.strftime("report_%Y-%m-%d_%H-%M")
    target = _unique_path(directory, stem)

    try:
        HTML(string=html, base_url=str(BASE_DIR)).write_pdf(str(target))
    except OSError as exc:
        raise PDFGenerationError(GTK_HINT) from exc
    except Exception as exc:
        raise PDFGenerationError(f"Не удалось сгенерировать PDF: {exc}") from exc

    if not target.exists() or target.stat().st_size == 0:
        raise PDFGenerationError("PDF-файл не был создан или оказался пустым.")

    return target


def display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(BASE_DIR).as_posix()
    except ValueError:
        return str(path)
