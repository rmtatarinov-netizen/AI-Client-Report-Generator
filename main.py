import argparse
import sys
from pathlib import Path

from utils.ai_processor import (
    AIProcessingError,
    get_demo_report,
    process_dialog_with_ai,
)
from utils.pdf_generator import PDFGenerationError, display_path, generate_pdf


def read_transcript_file(path: Path) -> str:
    if not path.is_file():
        raise ValueError(f"Файл не найден: {path}")

    for encoding in ("utf-8-sig", "cp1251"):
        try:
            content = path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
        if content.strip():
            return content.strip()

    raise ValueError(f"Не удалось прочитать текст из файла: {path}")


def read_interactive() -> str:
    print("Введите транскрибацию диалога. Завершите ввод пустой строкой:")
    lines: list[str] = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if not line.strip() and lines:
            break
        lines.append(line)

    transcript = "\n".join(lines).strip()
    if not transcript:
        raise ValueError(
            "Транскрибация не введена. Передайте файл через --input, "
            "текст через --text или запустите демо: --demo."
        )
    return transcript


def resolve_transcript(args: argparse.Namespace) -> str:
    if args.text:
        return args.text.strip()
    if args.input:
        return read_transcript_file(Path(args.input))
    return read_interactive()


def build_report(args: argparse.Namespace) -> Path:
    if args.demo:
        if args.input or args.text:
            resolve_transcript(args)
        data = get_demo_report()
    else:
        transcript = resolve_transcript(args)
        data = process_dialog_with_ai(transcript)

    return generate_pdf(data, output_dir=args.output_dir)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AI Client Report Generator — PDF-отчёты по диалогам с клиентами."
    )
    parser.add_argument(
        "-i",
        "--input",
        help="Путь к текстовому файлу с транскрибацией диалога.",
    )
    parser.add_argument(
        "-t",
        "--text",
        help="Транскрибация диалога, переданная строкой.",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Сгенерировать отчёт на демо-данных без вызова OpenAI.",
    )
    parser.add_argument(
        "--output-dir",
        help="Папка для сохранения PDF (по умолчанию reports/).",
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Запустить Flask API.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Хост Flask API.")
    parser.add_argument("--port", type=int, default=5000, help="Порт Flask API.")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Включить режим отладки Flask.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.serve:
        try:
            from app import create_app
        except ImportError as exc:
            print(f"Ошибка: не удалось запустить Flask API: {exc}", file=sys.stderr)
            return 1

        create_app().run(host=args.host, port=args.port, debug=args.debug)
        return 0

    try:
        output_path = build_report(args)
    except (AIProcessingError, PDFGenerationError, ValueError, OSError) as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1

    print(f"Отчёт успешно создан: {display_path(output_path)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
