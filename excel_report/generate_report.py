from __future__ import annotations

import argparse
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from common import (
    ROW_LIMIT,
    SHEET_REPORT,
    SHEET_SVYATOGOR,
    SHEET_UMM2,
    copy_svyatogor_data,
    copy_umm2_data,
    last_data_row,
    parse_date,
    print_validation,
    recalc_with_excel,
    rewrite_formulas,
    set_calculation_properties,
    set_period,
    validate_workbook,
)

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
DEFAULT_TEMPLATE = SCRIPT_DIR / "Отчёт_шаблон.xlsx"
DEFAULT_REPORT_DIR = PROJECT_DIR / "reports"
REGISTRY_DIR = PROJECT_DIR / "registries"
REGISTRY_PATTERNS = ("Реестр предписаний*.xlsx", "Реестр предписаний*.xlsm")


def find_registry() -> Path:
    candidates = []
    for pattern in REGISTRY_PATTERNS:
        candidates.extend(REGISTRY_DIR.glob(pattern))

    candidates = sorted(
        candidates,
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError(
            f"В {REGISTRY_DIR} не найден реестр предписаний. "
            "Положите файл 'Реестр предписаний*.xlsx' или '*.xlsm' "
            "в эту папку или укажите путь через --registry."
        )
    return candidates[0]


def main() -> None:
    parser = argparse.ArgumentParser(description="Формирование отчёта АО Святогор")
    parser.add_argument(
        "--registry",
        type=Path,
        default=None,
        help="Путь к реестру; по умолчанию ищется в registries",
    )
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--start", required=True, help="Начало периода, ДД.ММ.ГГГГ")
    parser.add_argument("--end", required=True, help="Конец периода, ДД.ММ.ГГГГ")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--umm2", type=Path, default=None)
    parser.add_argument("--no-recalc", action="store_true")
    parser.add_argument("--no-pdf", action="store_true")
    args = parser.parse_args()

    registry = args.registry or find_registry()
    if not registry.exists():
        raise FileNotFoundError(f"Не найден реестр: {registry}")
    if not args.template.exists():
        raise FileNotFoundError(f"Не найден шаблон: {args.template}")

    start = parse_date(args.start)
    end = parse_date(args.end)
    if start > end:
        raise ValueError("Начало периода не может быть позже конца")

    output = args.output
    if output is None:
        output = DEFAULT_REPORT_DIR / (
            f"svyatogor_report_{start:%Y-%m-%d}_{end:%Y-%m-%d}.xlsx"
        )
    output.parent.mkdir(parents=True, exist_ok=True)

    template_wb = load_workbook(args.template, data_only=False, keep_links=False)
    registry_wb = load_workbook(registry, data_only=True, keep_links=False)

    if SHEET_SVYATOGOR not in registry_wb.sheetnames:
        raise ValueError(f"В реестре нет листа {SHEET_SVYATOGOR!r}")

    copy_stats = copy_svyatogor_data(
        registry_wb[SHEET_SVYATOGOR],
        template_wb[SHEET_SVYATOGOR],
    )

    umm2_stats = None
    if args.umm2:
        if not args.umm2.exists():
            raise FileNotFoundError(f"Не найден файл УММ2: {args.umm2}")
        umm2_wb = load_workbook(args.umm2, data_only=True, keep_links=False)
        if SHEET_UMM2 not in umm2_wb.sheetnames:
            raise ValueError(f"В файле УММ2 нет листа {SHEET_UMM2!r}")
        umm2_stats = copy_umm2_data(
            umm2_wb[SHEET_UMM2],
            template_wb[SHEET_UMM2],
        )
        umm2_wb.close()

    set_period(template_wb, start, end)

    sv_last = last_data_row(template_wb[SHEET_SVYATOGOR], 20)
    umm2_last = last_data_row(template_wb[SHEET_UMM2], 17)
    row_limit = max(ROW_LIMIT, sv_last + 100, umm2_last + 100)
    rewrite_stats = rewrite_formulas(template_wb[SHEET_REPORT], row_limit)

    report_ws = template_wb[SHEET_REPORT]
    report_last = max(1, last_data_row(report_ws, 6, 1))
    for col_idx in range(7, report_ws.max_column + 1):
        report_ws.column_dimensions[get_column_letter(col_idx)].hidden = True
    report_ws.print_options.gridLines = False
    report_ws.print_area = f"A1:F{report_last}"
    print_area = f"$A$1:$F${report_last}"

    set_calculation_properties(template_wb)
    template_wb.active = template_wb.sheetnames.index(SHEET_REPORT)
    try:
        template_wb.save(output)
    except PermissionError as exc:
        template_wb.close()
        registry_wb.close()
        raise RuntimeError(
            f"Не удалось сохранить Excel-файл: {output}. "
            "Закройте этот файл в Excel и запустите команду снова."
        ) from exc
    template_wb.close()
    registry_wb.close()

    print(f"Реестр: {registry}")
    print(f"Шаблон: {args.template}")
    print(f"Период: {start:%d.%m.%Y} - {end:%d.%m.%Y}")
    print(f"Строк Святогора: {copy_stats['source_last'] - 8}")
    if umm2_stats:
        print(f"Строк УММ2: {umm2_stats['source_last'] - 8}")
    print(
        f"Формул отчёта: {rewrite_stats['formulas']}, "
        f"массивов: {rewrite_stats['arrays']}, изменено: {rewrite_stats['changed']}"
    )
    print(f"Файл Excel: {output}")

    pdf_output = None if args.no_pdf else output.with_suffix(".pdf")
    pdf_failed = False

    if not args.no_recalc:
        try:
            recalc_with_excel(
                output,
                pdf_output,
                print_area,
                "G:Y",
            )
            print("Пересчёт Excel: выполнен")
            if pdf_output is not None:
                print(f"Файл PDF: {pdf_output}")
            else:
                print("PDF: отключён (--no-pdf)")
        except Exception as exc:
            print(f"Пересчёт Excel/PDF не выполнен: {exc}")
            if pdf_output is not None:
                pdf_failed = True
    else:
        print("Пересчёт Excel: пропущен")
        print("PDF: не создан (--no-recalc)")

    print_validation(validate_workbook(output))

    if pdf_failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
