from __future__ import annotations

import argparse
from pathlib import Path

from openpyxl import load_workbook

from common import (
    ROW_LIMIT,
    SHEET_REPORT,
    SHEET_SVYATOGOR,
    SHEET_UMM2,
    count_external_refs,
    fix_umm2_data,
    print_validation,
    rewrite_formulas,
    set_calculation_properties,
    validate_workbook,
)

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
VPF10_DIR = PROJECT_DIR.parent
DEFAULT_SOURCE = VPF10_DIR / "Отчёт.xlsx"
DEFAULT_OUTPUT = SCRIPT_DIR / "Отчёт_шаблон.xlsx"


def main() -> None:
    parser = argparse.ArgumentParser(description="Сборка Excel-шаблона отчёта АО Святогор")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    if not args.source.exists():
        raise FileNotFoundError(f"Не найден исходный отчёт: {args.source}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    step1 = args.output.with_name(f"{args.output.stem}.step1{args.output.suffix}")

    wb = load_workbook(args.source, data_only=False, keep_links=True)
    required = {SHEET_REPORT, SHEET_SVYATOGOR, SHEET_UMM2}
    missing = required.difference(wb.sheetnames)
    if missing:
        raise ValueError(f"В книге нет листов: {', '.join(sorted(missing))}")

    external_before = count_external_refs(wb)
    fixed_cells = fix_umm2_data(wb[SHEET_UMM2])

    report_ws = wb[SHEET_REPORT]
    for coord in ("A13", "B18", "B21"):
        value = report_ws[coord].value
        if isinstance(value, str):
            report_ws[coord].value = value.replace("DD.MM.YYYY", "ДД.ММ.ГГГГ")

    rewritten = {}
    for ws in wb.worksheets:
        rewritten[ws.title] = rewrite_formulas(ws, ROW_LIMIT)

    wb.save(step1)
    wb.close()

    wb = load_workbook(step1, data_only=False, keep_links=False)
    set_calculation_properties(wb)
    wb.active = wb.sheetnames.index(SHEET_REPORT)
    wb.save(args.output)
    wb.close()
    step1.unlink(missing_ok=True)

    print(f"Шаблон: {args.output}")
    print(f"Внешних формул до замены: {external_before}")
    print(f"Исправлено ячеек УММ2: {len(fixed_cells)} -> {', '.join(fixed_cells)}")
    for sheet, stats in rewritten.items():
        print(
            f"  {sheet}: формул={stats['formulas']}, массивов={stats['arrays']}, "
            f"изменено={stats['changed']}"
        )
    print_validation(validate_workbook(args.output))


if __name__ == "__main__":
    main()
