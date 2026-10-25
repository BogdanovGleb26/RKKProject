import streamlit as st

import config
from import_excel import get_excel_preview, run_full_import


def render():
    st.title("⚙️ Администрирование")
    st.caption(
        "Раздел для управления данными. "
        "Действия здесь влияют на все данные приложения."
    )

    if not config.DB_ENABLED:
        st.error(
            "❌ PostgreSQL не сконфигурирован. "
            "Проверьте `.env` (DB_HOST, DB_NAME, DB_USER, DB_PASSWORD)."
        )
        return

    source = st.session_state.get("data_source", config.DEFAULT_DATA_SOURCE)
    source_label = "Локальный ПК" if source == "local" else "Яндекс.Диск"

    st.subheader("📥 Импорт данных из Excel")
    st.write(
        f"Источник данных: **{source_label}**. "
        f"Импорт **заменит все данные** в PostgreSQL."
    )

    # --- Шаг 1. Проверка ---
    if st.button("🔍 Проверить текущее состояние", width="stretch"):
        with st.spinner("Читаю Excel и считаю строки в БД..."):
            try:
                preview = get_excel_preview(source)
                st.session_state.import_preview = preview
            except Exception as e:
                st.error(f"Ошибка: {e}")
                st.session_state.pop("import_preview", None)

    preview = st.session_state.get("import_preview")
    if preview is not None and preview.source == source:
        st.divider()
        st.markdown("#### 📊 Данные перед импортом")

        table_labels = {
            "procurement": "Закупки",
            "os_main": "ОС Главная",
            "plastic_spools": "Пластик",
            "plastic_settings": "Настройки пластика",
        }

        rows = []
        for table in ("procurement", "os_main", "plastic_spools", "plastic_settings"):
            db_cnt = preview.db_counts.get(table, 0)
            ex_cnt = preview.excel_counts.get(table, 0)
            if ex_cnt == -1:
                ex_str = "❌ Ошибка чтения"
                delta = "—"
            else:
                ex_str = f"{ex_cnt}"
                delta = f"{ex_cnt - db_cnt:+d}" if db_cnt else f"+{ex_cnt}"
            rows.append({
                "Таблица": table_labels[table],
                "В БД сейчас": db_cnt,
                "В Excel": ex_str,
                "Изменение": delta,
            })

        st.dataframe(rows, width="stretch", hide_index=True)

        total_db = sum(preview.db_counts.values())
        total_ex = sum(c for c in preview.excel_counts.values() if c >= 0)

        if total_db > 0:
            st.warning(
                f"⚠️ **В БД уже есть данные** ({total_db} строк). "
                f"При импорте они будут **удалены** и заменены данными из Excel "
                f"({total_ex} строк)."
            )
        else:
            st.info(f"ℹ️ БД пуста. Будет вставлено {total_ex} строк.")

        # --- Шаг 2. Подтверждение и импорт ---
        st.divider()
        st.markdown("#### ⚠️ Подтверждение импорта")

        if total_db > 0:
            confirm = st.checkbox(
                "Я понимаю, что все текущие данные в БД будут удалены "
                "и заменены данными из Excel.",
                key="import_confirm",
            )
        else:
            confirm = True

        if st.button(
            "🚀 Импортировать всё",
            type="primary",
            width="stretch",
            disabled=not confirm,
        ):
            with st.spinner("Импортирую данные в PostgreSQL..."):
                try:
                    results = run_full_import(source)
                    st.session_state.import_results = results
                    st.session_state.pop("import_preview", None)
                except Exception as e:
                    st.error(f"Ошибка импорта: {e}")

    # --- Шаг 3. Результаты ---
    results = st.session_state.get("import_results")
    if results:
        st.divider()
        st.markdown("#### ✅ Результаты импорта")

        for r in results:
            table_label = {
                "procurement": "Закупки",
                "os_main": "ОС Главная",
                "plastic_spools": "Пластик",
                "plastic_settings": "Настройки пластика",
            }.get(r.table, r.table)

            with st.expander(
                f"{table_label}: {r.rows_inserted} / {r.rows_in_excel} строк"
                + (f" (ошибок: {r.rows_with_errors})" if r.rows_with_errors else ""),
                expanded=(r.rows_with_errors > 0),
            ):
                st.write(f"**В Excel:** {r.rows_in_excel}")
                st.write(f"**Вставлено в БД:** {r.rows_inserted}")
                if r.rows_with_errors:
                    st.warning(f"Строк с ошибками: {r.rows_with_errors} (значения → NULL)")
                if r.missing_columns:
                    st.info(
                        f"Колонки, которых не было в Excel: "
                        f"{', '.join(r.missing_columns)}"
                    )
                if r.error_messages:
                    st.write("**Первые ошибки:**")
                    for msg in r.error_messages:
                        st.code(msg, language="text")

        if st.button("Очистить результаты", width="stretch"):
            st.session_state.pop("import_results", None)
            st.rerun()