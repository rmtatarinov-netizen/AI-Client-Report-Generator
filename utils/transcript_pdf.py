import re
from datetime import datetime
from pathlib import Path

from .audio_transcriber import TranscriptionResult
from .pdf_generator import TRANSCRIPT_TEMPLATE_NAME, generate_pdf

INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _safe_filename_part(value: str, default: str = "call") -> str:
    part = INVALID_FILENAME_CHARS.sub("_", value)
    part = re.sub(r"\s+", "_", part).strip(" ._")
    if not part:
        part = default
    return part[:80]


def generate_transcript_pdf(
    transcript: TranscriptionResult,
    output_dir: Path | str | None = None,
    generated_at: datetime | None = None,
) -> Path:
    timestamp = generated_at or datetime.now()
    source_stem = Path(transcript.source_name).stem
    filename_stem = (
        f"transcript_{_safe_filename_part(source_stem)}_"
        f"{timestamp.strftime('%Y-%m-%d_%H-%M')}"
    )

    return generate_pdf(
        transcript.to_dict(),
        output_dir=output_dir,
        generated_at=timestamp,
        template_name=TRANSCRIPT_TEMPLATE_NAME,
        filename_stem=filename_stem,
        context={"transcript": transcript, "generated_at": timestamp},
    )
