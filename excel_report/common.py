from __future__ import annotations

import os
import re
import time
import traceback
import uuid
import zipfile
from copy import copy
from datetime import date, datetime
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.worksheet.formula import ArrayFormula

SHEET_REPORT = "Отчёт"
SHEET_SVYATOGOR = "АО Святогор"
SHEET_UMM2 = "АО УММ2"

ROW_LIMIT = 5000
DATA_START_ROW = 9
SVYATOGOR_DATA_COLS = 20
UMM2_DATA_COLS = 17
CALC_COLS = 22

DATE_FORMAT = "DD.MM.YYYY"
NO_PRESCRIPTIONS_MARKER = "Предписаний нет"


def rewrite_external_refs(text: str) -> str:
    text = text.replace("'[1]АО Святогор'!", "'АО Святогор'!")
    text = text.replace("'[1]АО УММ2'!", "'АО УММ2'!")
    text = re.sub(r"\[1\]([^'!]+)!", lambda m: f"'{m.group(1).strip()}'!", text)
    return text


def normalize_sheet_ranges(text: str, row_limit: int) -> str:
    pattern = re.compile(
        r"('(?:АО Святогор|АО УММ2)'!\$?[A-Z]{1,3}\$?9:\$?[A-Z]{1,3}\$?)\d+"
    )
    return pattern.sub(lambda m: f"{m.group(1)}{row_limit}", text)


def rewrite_formula(text: str, row_limit: int) -> str:
    return normalize_sheet_ranges(rewrite_external_refs(text), row_limit)


def rewrite_formulas(ws, row_limit: int) -> dict[str, int]:
    stats = {"formulas": 0, "arrays": 0, "changed": 0}
    for row in ws.iter_rows():
        for cell in row:
            value = cell.value
            if isinstance(value, ArrayFormula):
                stats["arrays"] += 1
                new_text = rewrite_formula(value.text, row_limit)
                if new_text != value.text:
                    cell.value = ArrayFormula(value.ref, new_text)
                    stats["changed"] += 1
            elif isinstance(value, str) and value.startswith("="):
                stats["formulas"] += 1
                new_text = rewrite_formula(value, row_limit)
                if new_text != value:
                    cell.value = new_text
                    stats["changed"] += 1
    return stats


def count_external_refs(wb) -> int:
    count = 0
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                value = cell.value
                text = value.text if isinstance(value, ArrayFormula) else value
                if isinstance(text, str) and "[1]" in text:
                    count += 1
    return count


def zip_external_link_parts(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as archive:
        return [name for name in archive.namelist() if "externalLink" in name]


def last_data_row(ws, max_col: int, start_row: int = DATA_START_ROW) -> int:
    for row in range(ws.max_row, start_row - 1, -1):
        for col in range(1, max_col + 1):
            if ws.cell(row, col).value not in (None, ""):
                return row
    return start_row - 1


def _copy_style(src, dst) -> None:
    if src.has_style:
        dst._style = copy(src._style)


def _ensure_row_style(ws, row: int, sample_row: int, max_col: int, original_max_row: int) -> None:
    if row <= original_max_row:
        return
    for col in range(1, max_col + 1):
        _copy_style(ws.cell(sample_row, col), ws.cell(row, col))


def fix_umm2_data(ws) -> list[str]:
    fixes = {
        "J466": date(2024, 7, 15),
        "J467": date(2024, 7, 15),
        "J1435": date(2026, 9, 30),
        "J1436": date(2026, 9, 30),
        "J1205": date(2026, 4, 8),
        "K248": date(2024, 2, 7),
    }
    for coord, value in fixes.items():
        ws[coord] = value
        ws[coord].number_format = DATE_FORMAT

    ws["R1435"] = '=IF(AND(J1435<TODAY(),L1435="нет"),1,IF(L1435="да",0))'
    ws["R466"] = '=IF(AND(J466<TODAY(),L466="нет"),1,IF(L466="да",0))'
    ws["R1436"] = '=IF(AND(J1436<TODAY(),L1436="нет"),1,IF(L1436="да",0))'

    return list(fixes)


def copy_svyatogor_data(source_ws, target_ws) -> dict[str, int]:
    source_last = last_data_row(source_ws, SVYATOGOR_DATA_COLS)
    target_last = last_data_row(target_ws, SVYATOGOR_DATA_COLS)
    original_max_row = target_ws.max_row
    clear_to = max(source_last, target_last) + 50

    for row in range(DATA_START_ROW, clear_to + 1):
        for col in range(1, CALC_COLS + 1):
            target_ws.cell(row, col).value = None

    for row in range(DATA_START_ROW, source_last + 1):
        _ensure_row_style(target_ws, row, DATA_START_ROW, CALC_COLS, original_max_row)
        for col in range(1, SVYATOGOR_DATA_COLS + 1):
            target_ws.cell(row, col).value = source_ws.cell(row, col).value
        target_ws[f"U{row}"] = f'=IF(AND(J{row}<TODAY(),M{row}="нет"),1,IF(M{row}="да",0))'
        target_ws[f"V{row}"] = f'=IF(AND(ISNUMBER(I{row}),ISNUMBER(L{row})),L{row}-I{row},"")'

    return {"source_last": source_last, "target_last": target_last}


def copy_umm2_data(source_ws, target_ws) -> dict[str, int]:
    source_last = last_data_row(source_ws, UMM2_DATA_COLS)
    target_last = last_data_row(target_ws, UMM2_DATA_COLS)
    original_max_row = target_ws.max_row
    clear_to = max(source_last, target_last) + 50

    for row in range(DATA_START_ROW, clear_to + 1):
        for col in range(1, 19):
            target_ws.cell(row, col).value = None

    for row in range(DATA_START_ROW, source_last + 1):
        _ensure_row_style(target_ws, row, DATA_START_ROW, 18, original_max_row)
        for col in range(1, 19):
            target_ws.cell(row, col).value = source_ws.cell(row, col).value

    return {"source_last": source_last, "target_last": target_last}


def set_period(wb, start: date, end: date) -> None:
    ws = wb[SHEET_REPORT]
    ws["G9"] = start
    ws["H9"] = end
    ws["G9"].number_format = DATE_FORMAT
    ws["H9"].number_format = DATE_FORMAT


def parse_date(value: str) -> date:
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"Не удалось разобрать дату: {value}")


def set_calculation_properties(wb) -> None:
    wb.calculation.calcMode = "auto"
    wb.calculation.fullCalcOnLoad = True
    wb.calculation.forceFullCalc = True


def hide_unneeded_prescription_rows(report) -> None:
    used = report.UsedRange
    values = used.Value
    if values is None:
        return
    if not isinstance(values, tuple):
        values = ((values,),)
    elif values and not isinstance(values[0], tuple):
        values = tuple((value,) for value in values)

    rows = [row if isinstance(row, tuple) else (row,) for row in values]
    first_row = used.Row

    for offset, row in enumerate(rows):
        if any(isinstance(value, str) and "Предписаний больше нет" in value for value in row):
            report.Rows(first_row + offset).Hidden = True

    section_starts = [
        offset
        for offset, row in enumerate(rows)
        if row and isinstance(row[0], str) and row[0].strip().startswith("Замечания АО")
    ]

    for start in section_starts:
        end = len(rows)
        for offset in range(start + 1, len(rows)):
            row = rows[offset]
            heading = row[0] if row else None
            if isinstance(heading, str):
                heading = heading.strip()
                if heading.startswith("Замечания/") or heading.startswith("Замечания АО"):
                    end = offset
                    break
            if any(
                isinstance(value, str) and value.strip().startswith("УС №")
                for value in row
            ):
                end = offset
                break

        marker_rows = []
        has_real_remark = False
        for offset in range(start, end):
            row = rows[offset]
            description = row[1] if len(row) > 1 else None
            if isinstance(description, str) and NO_PRESCRIPTIONS_MARKER in description:
                marker_rows.append(offset)
            elif isinstance(description, str) and description.strip() and "Предписаний больше нет" not in description:
                has_real_remark = True
            elif description not in (None, ""):
                has_real_remark = True

        for marker_pos, offset in enumerate(marker_rows):
            keep = not has_real_remark and marker_pos == 0
            report.Rows(first_row + offset).Hidden = not keep


def _write_recalc_error(path: Path, stage: str, exc: Exception) -> None:
    log_path = path.parent / "generate_report_error.log"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with log_path.open("a", encoding="utf-8") as log:
            log.write(f"[{timestamp}] {stage}: {exc}\n")
            log.write(traceback.format_exc())
            log.write("\n")
    except OSError:
        pass


def _retry(action, attempts: int = 2, delay: float = 1.0):
    for attempt in range(1, attempts + 1):
        try:
            return action()
        except Exception:
            if attempt == attempts:
                raise
            time.sleep(delay)


def recalc_with_excel(
    path: Path,
    pdf_path: Path | None = None,
    print_area: str | None = None,
    hidden_columns: str | None = None,
) -> None:
    import pythoncom
    import win32com.client as win32

    pythoncom.CoInitialize()
    excel = None
    workbook = None
    pdf_tmp = None
    keep_tmp = False
    stage = "запуск Excel"
    try:
        if pdf_path is not None:
            stage = "подготовка PDF"
            pdf_path = pdf_path.resolve()
            pdf_path.parent.mkdir(parents=True, exist_ok=True)
            pdf_tmp = pdf_path.with_name(
                f"{pdf_path.stem}.{uuid.uuid4().hex[:8]}.tmp{pdf_path.suffix}"
            )

        stage = "запуск Excel"
        excel = win32.DispatchEx("Excel.Application")
        excel.Visible = False
        excel.Interactive = False
        excel.DisplayAlerts = False
        excel.AskToUpdateLinks = False

        stage = "открытие книги Excel"
        workbook = _retry(
            lambda: excel.Workbooks.Open(str(path.resolve()), UpdateLinks=0)
        )

        stage = "пересчёт формул"
        excel.Calculation = -4105
        _retry(excel.CalculateFullRebuild)

        report = workbook.Worksheets(SHEET_REPORT)
        report.Activate()

        stage = "скрытие строк"
        hide_unneeded_prescription_rows(report)
        if hidden_columns:
            stage = "скрытие столбцов"
            report.Columns(hidden_columns).EntireColumn.Hidden = True
        if print_area:
            stage = "настройка области печати"
            report.PageSetup.PrintArea = print_area
        report.PageSetup.PrintGridlines = False

        stage = "сохранение Excel"
        _retry(workbook.Save)

        if pdf_path is not None and pdf_tmp is not None:
            stage = "экспорт PDF"
            report.Select()
            _retry(lambda: report.ExportAsFixedFormat(0, str(pdf_tmp)))
            if not pdf_tmp.exists():
                raise RuntimeError(f"Excel не создал PDF: {pdf_tmp}")
            if pdf_tmp.stat().st_size == 0:
                raise RuntimeError(f"Excel создал пустой PDF: {pdf_tmp}")
            with pdf_tmp.open("rb") as pdf_file:
                if pdf_file.read(5) != b"%PDF-":
                    raise RuntimeError(f"Excel создал некорректный PDF: {pdf_tmp}")

            stage = "замена PDF"
            try:
                os.replace(pdf_tmp, pdf_path)
            except OSError as exc:
                keep_tmp = True
                raise RuntimeError(
                    f"PDF создан, но не удалось заменить {pdf_path}. "
                    f"Закройте файл и повторите. Новый PDF: {pdf_tmp}"
                ) from exc

        stage = "закрытие Excel"
        workbook.Close(SaveChanges=False)
        workbook = None
    except Exception as exc:
        _write_recalc_error(path, stage, exc)
        raise RuntimeError(f"Сбой на этапе '{stage}': {exc}") from exc
    finally:
        if workbook is not None:
            try:
                workbook.Close(SaveChanges=False)
            except Exception:
                pass
        if excel is not None:
            try:
                excel.Quit()
            except Exception:
                pass
        if pdf_tmp is not None and pdf_tmp.exists() and not keep_tmp:
            try:
                pdf_tmp.unlink()
            except OSError:
                pass
        pythoncom.CoUninitialize()


def validate_workbook(path: Path) -> dict[str, object]:
    formula_wb = load_workbook(path, data_only=False, keep_links=False)
    value_wb = load_workbook(path, data_only=True, keep_links=False)
    result: dict[str, object] = {
        "external_formula_cells": count_external_refs(formula_wb),
        "external_link_parts": zip_external_link_parts(path),
        "errors": [],
    }

    errors = result["errors"]
    for ws in value_wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if isinstance(cell.value, str) and cell.value.startswith("#"):
                    errors.append(f"{ws.title}!{cell.coordinate}={cell.value}")

    formula_wb.close()
    value_wb.close()
    return result


def print_validation(result: dict[str, object]) -> None:
    print(f"Внешних формул [1]: {result['external_formula_cells']}")
    print(f"Частей externalLink: {len(result['external_link_parts'])}")
    errors = result["errors"]
    print(f"Ячеек с ошибками: {len(errors)}")
    for error in errors[:20]:
        print(f"  {error}")
