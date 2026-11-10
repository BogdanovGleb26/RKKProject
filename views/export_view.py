"""
Страница «Экспорт в Excel».

Позволяет скачать текущие данные (из активного источника) в формате .xlsx
с 4 листами, как в исходном Excel.
"""

from datetime import datetime

import pandas as pd
import streamlit as st

import config
from db import get_sheet_df, SHEET_REVERSE_MAP
from repositories.excel_exporter import (
    prepare_for_export,
    export_to_excel_bytes,
    COLUMN_ORDER,
    SERVICE_COLUMNS,
)


# =============================================================================
# Служебные (не экспортируются)
# =============================================================================

SHEET_NAMES = ["Закупки", "ОС Главная", "Пластик", "Настройка печати"]


def _format_source_label(source: str) -> str:
    return {
        "local": "Локальный ПК",
        "yadisk": "Яндекс.Диск",
        "postgres": "PostgreSQL",
    }.get(source, source)


def _get_deleted_count(source: str) -> dict:
    """Считает количество soft-deleted записей в каждой таблице.

    Только для postgres. Для local/yadisk возвращает 0.
    """
    result = {name: 0 for name in SHEET_NAMES}
    if source != "postgres":
        return result
    try:
        from db import get_engine
        from sqlalchemy import text
        engine = get_engine()
        if engine is None:
            return result
        with engine.connect() as conn:
            for sheet_name, table in [
                ("Закупки", "procurement"),
                ("ОС Главная", "os_main"),
                ("Пластик", "plastic_spools"),
            ]:
                cnt = conn.execute(
                    text(f"SELECT COUNT(*) FROM {table} WHERE is_deleted = TRUE")
                ).scalar()
                result[sheet_name] = int(cnt or 0)
    except Exception:
        pass
    return result


def render():
    st.title("📤 Экспорт в Excel")
    st.caption(
        "Скачать текущие данные в формате Excel (.xlsx) с 4 листами — "
        "как в исходном файле реестра."
    )

    # --- Источник ---
    source = st.session_state.get("data_source", config.DEFAULT_DATA_SOURCE)
    source_label = _format_source_label(source)
    st.markdown(f"**Источник данных:** {source_label}")

    # --- Загружаем данные ---
    dfs_raw: dict = {}
    stats: dict = {}
    load_errors: dict = {}

    with st.spinner("Загружаю данные..."):
        for sheet_name in SHEET_NAMES:
            try:
                df, last_updated = get_sheet_df(sheet_name, source=source)
                dfs_raw[sheet_name] = df
                stats[sheet_name] = {
                    "rows": len(df),
                    "last_updated": last_updated,
                }
            except Exception as e:
                load_errors[sheet_name] = str(e)
                stats[sheet_name] = {"rows": 0, "last_updated": "—"}

    # --- Ошибки загрузки ---
    if load_errors:
        st.error(f"⚠️ Не удалось загрузить: {', '.join(load_errors.keys())}")

    # --- Статистика ---
    st.divider()
    st.subheader("📊 Текущие данные")

    cols = st.columns(4)
    for sheet_name, col in zip(SHEET_NAMES, cols):
        with col:
            st.metric(sheet_name, stats[sheet_name]["rows"])

    # Последнее обновление (по первому листу)
    first_updated = stats.get(SHEET_NAMES[0], {}).get("last_updated")
    if first_updated and first_updated != "—":
        st.caption(f"🕒 Последнее обновление: **{first_updated}**")

    # --- Удалённые записи ---
    deleted_counts = _get_deleted_count(source)
    total_deleted = sum(deleted_counts.values())
    if total_deleted > 0:
        with st.expander(f"🗑️ Скрытые удалённые записи: {total_deleted}"):
            st.caption(
                "Soft-deleted записи **не экспортируются** в Excel. "
                "Их можно восстановить через администрирование/БД."
            )
            for name, cnt in deleted_counts.items():
                if cnt > 0:
                    st.write(f"- **{name}:** {cnt}")
    else:
        st.caption("✅ Удалённых записей нет.")

    # --- Сопоставление колонок ---
    st.divider()
    st.subheader("🔄 Сопоставление колонок (БД ↔ Excel)")

    with st.expander("Показать сопоставление по всем листам", expanded=False):
        st.caption(
            "✅ — экспортируется · "
            "🚫 — служебная (не экспортируется) · "
            "❓ — нет в текущих данных"
        )
        for sheet_name in SHEET_NAMES:
            st.markdown(f"**{sheet_name}**")
            mapping = SHEET_REVERSE_MAP.get(sheet_name, {})
            if not mapping:
                st.caption("_Нет маппинга_")
                continue

            # Собираем данные для таблицы
            rows = []
            df_cols = set(dfs_raw.get(sheet_name, pd.DataFrame()).columns)
            for eng, rus in mapping.items():
                exists_in_df = rus in df_cols or eng in df_cols

                # Проверка: это служебная колонка?
                is_service = eng in SERVICE_COLUMNS or rus in SERVICE_COLUMNS

                if is_service:
                    status = "🚫 (служебная)"
                elif exists_in_df:
                    status = "✅"
                else:
                    status = "❓ (нет в данных)"

                rows.append({
                    "Колонка в БД": eng,
                    "Колонка в Excel": rus,
                    "Экспортируется": status,
                })

            # Колонки, которых нет в маппинге (могут быть лишними)
            mapped_rus = set(mapping.values())
            extra = [c for c in df_cols if c not in mapped_rus and c not in SERVICE_COLUMNS]
            if extra:
                st.warning(f"Колонки вне маппинга: {', '.join(extra)}")

            st.dataframe(rows, hide_index=True, width="stretch")
            st.write("")  # отступ

    # --- Служебные (не экспортируются) ---
    st.divider()
    st.subheader("🔒 Служебные колонки (не экспортируются)")
    st.write(", ".join(f"`{c}`" for c in SERVICE_COLUMNS))

    # --- Формирование и скачивание ---
    st.divider()
    st.subheader("📄 Формирование файла")

    if st.button("📄 Сформировать Excel", type="primary", width="stretch", key="export_build"):
        if load_errors:
            st.error("Сначала исправьте ошибки загрузки.")
        elif not dfs_raw:
            st.error("Нет данных для экспорта.")
        else:
            with st.spinner("Формирую файл..."):
                try:
                    prepared = {
                        name: prepare_for_export(df, name)
                        for name, df in dfs_raw.items()
                    }
                    xlsx_bytes = export_to_excel_bytes(
                        prepared,
                        mapping_sheets=SHEET_REVERSE_MAP,
                    )
                    st.session_state["_export_bytes"] = xlsx_bytes
                    st.session_state["_export_filename"] = (
                        f"inventarization_{datetime.now():%Y-%m-%d_%H-%M}.xlsx"
                    )
                    st.success("✅ Файл сформирован. Нажмите «Скачать».")
                except Exception as e:
                    st.error(f"Ошибка формирования: {e}")

    if "_export_bytes" in st.session_state:
        st.download_button(
            label="📥 Скачать Excel",
            data=st.session_state["_export_bytes"],
            file_name=st.session_state["_export_filename"],
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            width="stretch",
            key="export_download",
        )