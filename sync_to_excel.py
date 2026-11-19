"""
Синхронизация данных из БД в исходный Excel-файл.

Особенности:
- Обновляет ТОЛЬКО «Место хранения» и «Кол-во» (для Пластика — «Вес»).
- Остальные колонки НЕ трогает.
- Новые записи из БД НЕ добавляет (для этого — «Экспорт»).
- Записи из Excel, которых нет в БД — НЕ удаляет и НЕ трогает.
- Перед записью делает бэкап в backups/.
- Если файл открыт в Excel — пишет в копию.
"""

import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
from openpyxl import load_workbook

logger = logging.getLogger("app.sync_excel")


# =============================================================================
# Конфигурация листов и колонок
# =============================================================================

# ВАЖНО: имена колонок в БД — РУССКИЕ (как их отдаёт get_sheet_df).
SHEET_CONFIG = {
    "Закупки": {
        "table": "procurement",
        "code_col": "Код",
        "qr_col": "QR код",
        "field_map": {
            "Место хранения": "Место хранения",
            "Кол-во": "Кол-во",
        },
    },
    "ОС Главная": {
        "table": "os_main",
        "code_col": "Код",
        "qr_col": "QR код",
        "field_map": {
            "Место хранения": "Место хранения",
            "Кол-во": "Кол-во",
        },
    },
    "Пластик": {
        "table": "plastic_spools",
        "code_col": "Код",
        "qr_col": "QR код",
        "field_map": {
            "Место хранения": "Место хранения",
            "Вес": "Вес",
        },
    },
}


# =============================================================================
# Результаты
# =============================================================================

@dataclass
class SheetSyncResult:
    sheet_name: str
    rows_excel: int = 0
    rows_db: int = 0
    matched: int = 0
    skipped_not_in_db: int = 0
    skipped_ambiguous: int = 0
    skipped_no_keys: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class SyncResult:
    sheets: list[SheetSyncResult] = field(default_factory=list)
    backup_path: Optional[str] = None
    output_path: Optional[str] = None
    file_was_open: bool = False
    success: bool = False
    error: Optional[str] = None


# =============================================================================
# Хелперы
# =============================================================================

def _normalize_code(value) -> str:
    """Нормализует код для сравнения.
    
    - None → ''
    - float 850.0 → '850'
    - int 850 → '850'
    - str '  850  ' → '850'
    - str '850.0' → '850'
    """
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, int):
        return str(value)
    s = str(value).strip()
    if s.endswith(".0") and s[:-2].replace("-", "").isdigit():
        s = s[:-2]
    return s


def _find_col(df: pd.DataFrame, *candidates: str) -> Optional[str]:
    """Ищет первую подходящую колонку в df."""
    for c in candidates:
        if c in df.columns:
            return c
    return None


def _load_db_data(source: str = "postgres") -> dict[str, pd.DataFrame]:
    """Загружает данные из БД для 3 таблиц."""
    from db import get_sheet_df

    result = {}
    for sheet_name, cfg in SHEET_CONFIG.items():
        try:
            df, _ = get_sheet_df(sheet_name, source=source)
            result[cfg["table"]] = df
            logger.info("Загружено из БД: %s — %d строк", cfg["table"], len(df))
        except Exception:
            logger.exception("Ошибка загрузки %s из БД", cfg["table"])
            result[cfg["table"]] = pd.DataFrame()
    return result


def is_file_open(path: Path) -> bool:
    """Проверяет, открыт ли файл (например, в Excel)."""
    if not path.exists():
        return False
    try:
        with open(path, "a"):
            pass
        return False
    except (OSError, PermissionError):
        return True


def _make_backup(path: Path, backups_dir: Path) -> Path:
    """Делает бэкап файла в backups_dir."""
    backups_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    backup_path = backups_dir / f"inventarization_backup_{timestamp}.xlsx"
    shutil.copy2(path, backup_path)
    logger.info("Бэкап: %s → %s", path, backup_path)
    return backup_path


def _build_db_index(db_df: pd.DataFrame, cfg: dict) -> dict[str, list[dict]]:
    """Строит индекс БД по коду."""
    code_col = _find_col(db_df, cfg["code_col"], "code")
    if code_col is None:
        return {}

    db_by_code: dict[str, list[dict]] = {}
    for _, row in db_df.iterrows():
        code = _normalize_code(row.get(code_col))
        if code:
            db_by_code.setdefault(code, []).append(row.to_dict())
    return db_by_code


# =============================================================================
# Preview (без изменения)
# =============================================================================

def _sync_sheet_preview(ws, cfg: dict, db_df: pd.DataFrame) -> SheetSyncResult:
    """Только считает, БЕЗ изменения."""
    result = SheetSyncResult(sheet_name=ws.title)
    result.rows_excel = ws.max_row - 1 if ws.max_row > 0 else 0
    result.rows_db = len(db_df)

    if result.rows_excel <= 0:
        return result

    headers: dict[str, int] = {}
    for col_idx in range(1, ws.max_column + 1):
        v = ws.cell(row=1, column=col_idx).value
        if v is not None:
            headers[str(v).strip()] = col_idx

    required = [cfg["code_col"]] + list(cfg["field_map"].keys())
    missing = [c for c in required if c not in headers]
    if missing:
        result.errors.append(
            f"Лист «{ws.title}»: отсутствуют колонки: {', '.join(missing)}."
        )
        return result

    code_col_idx = headers[cfg["code_col"]]
    qr_col_idx = headers.get(cfg["qr_col"])

    db_by_code = _build_db_index(db_df, cfg)

    for row_idx in range(2, ws.max_row + 1):
        code = ws.cell(row=row_idx, column=code_col_idx).value
        code_str = _normalize_code(code)

        qr_str = ""
        if qr_col_idx is not None:
            qr_val = ws.cell(row=row_idx, column=qr_col_idx).value
            qr_str = _normalize_code(qr_val)

        if not code_str and not qr_str:
            result.skipped_no_keys += 1
            continue

        if code_str and code_str in db_by_code:
            candidates = db_by_code[code_str]
            if len(candidates) == 1:
                result.matched += 1
            else:
                if qr_str:
                    qr_matches = [
                        r for r in candidates
                        if _normalize_code(r.get(cfg["qr_col"])) == qr_str
                    ]
                    if len(qr_matches) == 1:
                        result.matched += 1
                    else:
                        result.skipped_ambiguous += 1
                else:
                    result.skipped_ambiguous += 1
        else:
            result.skipped_not_in_db += 1

    return result


def get_sync_summary(source: str = "postgres") -> list[SheetSyncResult]:
    """Сводка БЕЗ изменения файла."""
    from data_loader import LOCAL_FILE_PATH

    path = Path(LOCAL_FILE_PATH)
    if not path.exists():
        raise FileNotFoundError(f"Файл не найден: {path}")

    db_data = _load_db_data(source)
    # data_only=True — чтобы читать значения формул (например, QR = CONCATENATE)
    wb = load_workbook(path, data_only=True)

    results: list[SheetSyncResult] = []
    for sheet_name, cfg in SHEET_CONFIG.items():
        if sheet_name not in wb.sheetnames:
            r = SheetSyncResult(sheet_name=sheet_name)
            r.errors.append(f"Лист «{sheet_name}» не найден в Excel.")
            results.append(r)
            continue
        ws = wb[sheet_name]
        db_df = db_data.get(cfg["table"], pd.DataFrame())
        results.append(_sync_sheet_preview(ws, cfg, db_df))

    wb.close()
    return results


# =============================================================================
# Синхронизация одного листа
# =============================================================================

def _sync_sheet(ws, cfg: dict, db_df: pd.DataFrame) -> SheetSyncResult:
    """Синхронизирует один лист."""
    result = SheetSyncResult(sheet_name=ws.title)
    result.rows_excel = ws.max_row - 1 if ws.max_row > 0 else 0
    result.rows_db = len(db_df)

    if result.rows_excel <= 0:
        return result

    headers: dict[str, int] = {}
    for col_idx in range(1, ws.max_column + 1):
        v = ws.cell(row=1, column=col_idx).value
        if v is not None:
            headers[str(v).strip()] = col_idx

    required = [cfg["code_col"]] + list(cfg["field_map"].keys())
    missing = [c for c in required if c not in headers]
    if missing:
        result.errors.append(
            f"Лист «{ws.title}»: отсутствуют колонки: {', '.join(missing)}."
        )
        return result

    code_col_idx = headers[cfg["code_col"]]
    qr_col_idx = headers.get(cfg["qr_col"])
    field_cols: dict[str, int] = {
        excel_col: headers[excel_col]
        for excel_col in cfg["field_map"].keys()
    }

    db_by_code = _build_db_index(db_df, cfg)
    db_qr_col = _find_col(db_df, cfg["qr_col"], "qr_code")

    for row_idx in range(2, ws.max_row + 1):
        code = ws.cell(row=row_idx, column=code_col_idx).value
        code_str = _normalize_code(code)

        qr_str = ""
        if qr_col_idx is not None:
            qr_val = ws.cell(row=row_idx, column=qr_col_idx).value
            qr_str = _normalize_code(qr_val)

        if not code_str and not qr_str:
            result.skipped_no_keys += 1
            continue

        matched_db_row = None

        if code_str and code_str in db_by_code:
            candidates = db_by_code[code_str]
            if len(candidates) == 1:
                matched_db_row = candidates[0]
            else:
                if qr_str and db_qr_col:
                    qr_matches = [
                        r for r in candidates
                        if _normalize_code(r.get(db_qr_col)) == qr_str
                    ]
                    if len(qr_matches) == 1:
                        matched_db_row = qr_matches[0]
                    else:
                        result.skipped_ambiguous += 1
                        continue
                else:
                    result.skipped_ambiguous += 1
                    continue

        if matched_db_row is None:
            result.skipped_not_in_db += 1
            continue

        try:
            for excel_col, db_field in cfg["field_map"].items():
                col_idx = field_cols[excel_col]
                new_value = matched_db_row.get(db_field)

                if new_value is None or (isinstance(new_value, float) and pd.isna(new_value)):
                    new_value = None
                elif isinstance(new_value, str) and not new_value.strip():
                    new_value = None

                ws.cell(row=row_idx, column=col_idx).value = new_value

            result.matched += 1
        except Exception as e:
            result.errors.append(f"Строка {row_idx}: {e}")

    return result


# =============================================================================
# Публичная функция синхронизации
# =============================================================================

def sync_to_excel(source: str = "postgres") -> SyncResult:
    """Синхронизация БД → Excel (с бэкапом)."""
    from data_loader import LOCAL_FILE_PATH

    path = Path(LOCAL_FILE_PATH)
    if not path.exists():
        return SyncResult(error=f"Файл не найден: {path}")

    backups_dir = path.parent / "backups"

    try:
        backup_path = _make_backup(path, backups_dir)
    except Exception as e:
        logger.exception("Ошибка бэкапа")
        return SyncResult(error=f"Ошибка бэкапа: {e}")

    was_open = is_file_open(path)

    if was_open:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        output_path = backups_dir / f"inventarization_synced_{timestamp}.xlsx"
        shutil.copy2(path, output_path)
    else:
        output_path = path

    db_data = _load_db_data(source)

    try:
        wb = load_workbook(output_path, data_only=True)
        sheets_result: list[SheetSyncResult] = []

        for sheet_name, cfg in SHEET_CONFIG.items():
            if sheet_name not in wb.sheetnames:
                r = SheetSyncResult(sheet_name=sheet_name)
                r.errors.append(f"Лист «{sheet_name}» не найден в Excel.")
                sheets_result.append(r)
                continue
            ws = wb[sheet_name]
            db_df = db_data.get(cfg["table"], pd.DataFrame())
            sheets_result.append(_sync_sheet(ws, cfg, db_df))

        wb.save(output_path)
        wb.close()
        logger.info("Синхронизация завершена: %s", output_path)

        return SyncResult(
            sheets=sheets_result,
            backup_path=str(backup_path),
            output_path=str(output_path),
            file_was_open=was_open,
            success=True,
        )
    except Exception as e:
        logger.exception("Ошибка синхронизации")
        return SyncResult(
            backup_path=str(backup_path),
            error=f"Ошибка синхронизации: {e}",
            success=False,
        )