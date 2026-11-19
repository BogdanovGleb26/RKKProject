"""
Страница «Синхронизация в Excel».

Переносит из БД в Excel ТОЛЬКО «Место хранения» и «Кол-во» (для Пластика — «Вес»).
Остальные поля не трогает. Новые записи из БД не добавляет.
Доступ — только admin/editor, только при источнике postgres.
"""

from datetime import datetime
from pathlib import Path

import streamlit as st

import config
from data_loader import LOCAL_FILE_PATH
from sync_to_excel import (
    get_sync_summary,
    sync_to_excel,
    is_file_open,
    SHEET_CONFIG,
)


SHEET_LABELS = {
    "Закупки": "Закупки",
    "ОС Главная": "ОС Главная",
    "Пластик": "Пластик",
}


def _render_file_info(path: Path) -> None:
    """Показывает информацию о файле Excel."""
    st.markdown("### 📁 Файл Excel")
    st.code(str(path), language="text")

    if not path.exists():
        st.error("❌ Файл не найден. Проверьте LOCAL_FILE_PATH в .env.")
        return

    # Дата модификации
    mtime = path.stat().st_mtime
    mod_time = datetime.fromtimestamp(mtime)
    st.caption(f"🕒 Последнее изменение: **{mod_time.strftime('%d.%m.%Y %H:%M')}**")

    # Открыт ли в Excel
    if is_file_open(path):
        st.warning(
            "⚠️ Файл **открыт** в Excel (или другой программе). "
            "Синхронизация будет выполнена **в копию** в папке `backups/`, "
            "исходный файл **не будет изменён**."
        )
    else:
        st.success("✅ Файл не открыт — синхронизация перезапишет его (с бэкапом).")


def _render_summary(results) -> None:
    """Показывает сводку по листам (с подробным пояснением колонок)."""
    st.markdown("### 📊 Сводка")

    # --- Краткая расшифровка сверху ---
    st.info(
        "**Что означают колонки:**\n\n"
        "- **Всего в Excel** — сколько строк в Excel-файле (включая пустые).\n"
        "- **Всего в БД** — сколько записей в базе данных по этому листу.\n"
        "- **✅ Совпадёт (будет обновлено)** — сколько строк найдено по `Код` (при дублях — по `QR код`) и **будет обновлено**.\n"
        "- **⚠️ Пропущено (нет в БД)** — строки в Excel, которых нет в БД. **Не будут изменены** — сначала нужен импорт через «Администрирование».\n"
        "- **❓ Неоднозначно (дубли)** — несколько записей с одинаковым `Код`/`QR`, невозможно однозначно сопоставить. **Не будут изменены**.\n"
        "- **⛔ Без ключей (пустые)** — строки без `Код` и `QR код` (пустые заготовки). **Не трогаются**."
    )

    # --- Таблица ---
    rows = []
    for r in results:
        rows.append({
            "Лист": SHEET_LABELS.get(r.sheet_name, r.sheet_name),
            "Всего в Excel": r.rows_excel,
            "Всего в БД": r.rows_db,
            "✅ Совпадёт": r.matched,
            "⚠️ Пропущено (нет в БД)": r.skipped_not_in_db,
            "❓ Неоднозначно": r.skipped_ambiguous,
            "⛔ Без ключей": r.skipped_no_keys,
        })

    st.dataframe(rows, hide_index=True, width="stretch")

    # --- Итоговая строка ---
    total_excel = sum(r.rows_excel for r in results)
    total_db = sum(r.rows_db for r in results)
    total_matched = sum(r.matched for r in results)
    total_skipped = sum(r.skipped_not_in_db for r in results)
    total_ambiguous = sum(r.skipped_ambiguous for r in results)
    total_no_keys = sum(r.skipped_no_keys for r in results)

    st.caption(
        f"**Итого:** {total_matched} строк будет обновлено, "
        f"{total_skipped} пропущено (нет в БД), "
        f"{total_ambiguous} неоднозначно, "
        f"{total_no_keys} без ключей."
    )

    # --- Ошибки ---
    errors = [e for r in results for e in r.errors]
    if errors:
        with st.expander("⚠️ Ошибки", expanded=True):
            for e in errors:
                st.warning(e)


def _render_sync_result(result) -> None:
    """Показывает результат синхронизации."""
    if not result.success:
        st.error(f"❌ Ошибка: {result.error}")
        return

    st.success("✅ Синхронизация выполнена успешно!")

    # Бэкап
    if result.backup_path:
        st.markdown("### 💾 Бэкап")
        st.code(result.backup_path, language="text")
        st.caption("Создан до синхронизации. Если что-то пошло не так — восстановите из него.")

    # Куда записано
    st.markdown("### 📝 Куда записано")
    if result.file_was_open:
        st.warning(
            "Файл был **открыт** в Excel. Синхронизация выполнена **в копию**. "
            "Исходный файл **не изменён**."
        )
    st.code(result.output_path or "—", language="text")

    # Статистика
    st.markdown("### 📊 Результат по листам")
    st.caption(
        "**Обновлено** — строки, в которых «Место хранения» и «Кол-во»/«Вес» "
        "были перезаписаны значениями из БД. "
        "**Остальные поля** — **не тронуты**."
    )
    rows = []
    for r in result.sheets:
        rows.append({
            "Лист": SHEET_LABELS.get(r.sheet_name, r.sheet_name),
            "✅ Обновлено": r.matched,
            "⚠️ Пропущено (нет в БД)": r.skipped_not_in_db,
            "❓ Неоднозначно": r.skipped_ambiguous,
            "⛔ Без ключей": r.skipped_no_keys,
        })
    st.dataframe(rows, hide_index=True, width="stretch")

    total_matched = sum(r.matched for r in result.sheets)
    st.caption(f"**Итого обновлено:** **{total_matched}** строк.")

    errors = [e for r in result.sheets for e in r.errors]
    if errors:
        with st.expander("⚠️ Ошибки"):
            for e in errors:
                st.warning(e)


def render():
    st.title("🔄 Синхронизация в Excel")
    st.caption(
        "Перенос **из БД** в исходный Excel-файл изменений **только по двум полям**: "
        "«Место хранения» и «Количество» (для Пластика — «Вес»)."
    )

    # --- Проверка источника ---
    source = st.session_state.get("data_source", config.DEFAULT_DATA_SOURCE)
    if source != "postgres":
        st.warning(
            f"⚠️ Синхронизация доступна **только при источнике данных PostgreSQL**. "
            f"Сейчас выбран: **{source}**. Переключите источник в сайдбаре."
        )
        return

    if not config.DB_ENABLED:
        st.error("❌ PostgreSQL не сконфигурирован.")
        return

    # --- ВАЖНО: ограничение по полям ---
    st.info(
        "⚠️ **ВАЖНО:** синхронизация переносит **только два поля**:\n\n"
        "- **«Место хранения»** (все листы)\n"
        "- **«Кол-во»** (Закупки, ОС Главная) / **«Вес»** (Пластик)\n\n"
        "**Остальные поля** (цена, статус, проект и т.д.) **НЕ переносятся** — "
        "они остаются как в Excel.\n\n"
        "**Новые записи** из БД в Excel **НЕ добавляются** "
        "(для полного экспорта — раздел «📤 Экспорт»)."
    )

    path = Path(LOCAL_FILE_PATH)
    _render_file_info(path)

    if not path.exists():
        return

    st.divider()

    # --- Сводка ---
    if st.button("🔍 Проверить (без изменения файла)", width="stretch", key="sync_check"):
        with st.spinner("Читаю файл и БД..."):
            try:
                results = get_sync_summary("postgres")
                st.session_state["_sync_results"] = results
            except Exception as e:
                st.error(f"Ошибка: {e}")
                st.session_state.pop("_sync_results", None)

    results = st.session_state.get("_sync_results")
    if results:
        st.divider()
        _render_summary(results)

        st.divider()

        # --- Кнопка синхронизации ---
        file_open = is_file_open(path)
        confirm_text = (
            "Я понимаю, что изменения будут записаны **в копию** (файл открыт)."
            if file_open
            else "Я понимаю, что исходный файл будет **перезаписан** (с бэкапом)."
        )

        confirm = st.checkbox(confirm_text, key="sync_confirm")

        if st.button(
            "🔄 Синхронизировать",
            type="primary",
            width="stretch",
            disabled=not confirm,
            key="sync_run",
        ):
            with st.spinner("Синхронизирую..."):
                try:
                    result = sync_to_excel("postgres")
                    st.session_state["_sync_result"] = result
                    st.session_state.pop("_sync_results", None)
                except Exception as e:
                    st.error(f"Ошибка синхронизации: {e}")

    # --- Результат ---
    result = st.session_state.get("_sync_result")
    if result:
        st.divider()
        _render_sync_result(result)

        if st.button("Очистить результат", key="sync_clear"):
            st.session_state.pop("_sync_result", None)
            st.rerun()