import pandas as pd
import streamlit as st
import re
from data_loader import load_data
from utils import highlight_text, create_badge

def render():
    st.title("📦 Поиск по складу")

    col_sheet, col_btn = st.columns([4, 1], vertical_alignment="bottom")

    with col_sheet:
        SHEET_OPTIONS = ["Закупки", "ОС Главная", "Пластик"]
        selected_sheet = st.radio("📄 Раздел учета:", options=SHEET_OPTIONS, index=0, horizontal=True)

    with col_btn:
        if st.button("🔄 Обновить", use_container_width=True, help="Скачать свежую версию с Яндекс.Диска (задержка несколько минут)"):
            load_data.clear()
            st.toast("Данные успешно обновлены с Диска!", icon="🎉")
            st.rerun()

    # Загрузка данных
    try:
        with st.spinner(f"Загрузка раздела «{selected_sheet}»..."):
            df, last_updated = load_data(selected_sheet)
            df_print_settings = pd.DataFrame()
            if selected_sheet == "Пластик":
                df_print_settings, _ = load_data("Настройка печати")
    except Exception as e:
        st.error(f"Ошибка загрузки базы: {e}")
        st.stop()

    st.caption(f"🕒 Данные в последний раз обновлены на Диске: **{last_updated}** (МСК)")

    if df.empty:
        st.info(f"📭 Лист **«{selected_sheet}»** пока пуст или не содержит данных.")
        st.stop()

    # Вывод справочника
    if selected_sheet == "Пластик" and not df_print_settings.empty:
        with st.expander("⚙️ Справочник: Настройки печати", expanded=True):
            display_cols = [c for c in df_print_settings.columns if c != "_search_corpus"]
            df_display = df_print_settings[display_cols].copy()

            for col in df_display.columns:
                df_display[col] = df_display[col].apply(
                    lambda x: "100%" if str(x).strip() in ["1", "1.0"] 
                    else (f"{round(float(x)*100)}%" if isinstance(x, (int, float)) and 0 < x < 1 else x)
                )
            st.dataframe(df_display, use_container_width=True, hide_index=True)

    if "search_input_field" not in st.session_state:
        st.session_state.search_input_field = ""

    # Быстрые фильтры
    QUICK_FILTERS = {
        "Закупки": [("🖨️ Пластик", "пластик"), ("🔌 Принтер", "принтер"), ("📍 Цех №4", "цех №4"), ("👤 Смирнова", "смирнова")],
        "ОС Главная": [("⚙️ Система", "система"), ("🚉 Станция", "станция"), ("📷 Камера", "камера"), ("🔢 Цифровой", "цифровой")],
        "Пластик": [("🧵 PLA", "PLA"), ("⚙️ PETG", "PETG"),("👌 ABS", "ABS"),("🖤 Чёрный", "черный"), ("PLA + 💚", "PLA зеленый")]
    }

    current_filters = QUICK_FILTERS.get(selected_sheet, [])
    if current_filters:
        st.caption("⚡ Быстрый поиск:")
        chip_cols = st.columns(len(current_filters))
        for idx, (btn_label, search_term) in enumerate(current_filters):
            with chip_cols[idx]:
                if st.button(btn_label, use_container_width=True, key=f"btn_{selected_sheet}_{idx}"):
                    st.session_state.search_input_field = search_term
                    st.rerun()

    raw_input = st.text_input("Поиск", placeholder="Название, код, место хранения...", key="search_input_field")
    search_query = raw_input.strip().lower()

    if not search_query:
        st.info(f"👋 Раздел **«{selected_sheet}»**. Введите название детали, код или локацию, чтобы начать поиск.")
        col1, col2 = st.columns(2)
        with col1:
            st.metric(label="Всего позиций", value=len(df))
        with col2:
            locations_count = df["Место хранения"].replace("", None).nunique() if "Место хранения" in df.columns else 0
            st.metric(label="Занято ячеек", value=locations_count)
    else:
        if search_query == "без места":
            if "Место хранения" in df.columns:
                mask = df["Место хранения"].astype(str).str.strip() == ""
            else:
                mask = pd.Series([True] * len(df))
            tokens = []
        else:
            tokens = [t for t in search_query.split() if len(t) > 0]
            if tokens and "_search_corpus" in df.columns:
                
                def matches_exact_words(corpus: str) -> bool:
                    corpus_str = str(corpus)
                    for t in tokens:
                        # Для коротких кодов/материалов (PLA, ASA, PA, №4) ищем точное совпадение
                        if len(t) <= 3:
                            pattern = r"(?<!\w)" + re.escape(t) + r"(?!\w)"
                        # Для длинных слов (принтер, желтый) проверяем начало слова, разрешая окончания (принтеры)
                        else:
                            pattern = r"(?<!\w)" + re.escape(t)

                        if not re.search(pattern, corpus_str):
                            return False
                    return True

                mask = df["_search_corpus"].apply(matches_exact_words)
            else:
                mask = pd.Series([False] * len(df))

        filtered_df = df[mask]
        st.caption(f"Найдено позиций: {len(filtered_df)}")

        if filtered_df.empty:
            st.warning("Ничего не найдено.")
        else:
            for index, row in filtered_df.iterrows():
                raw_name = str(row.get("Название", "")).strip()
                raw_nom = str(row.get("Номенклатура", "")).strip()
                name = raw_name if raw_name else (raw_nom if raw_nom else "Без названия")

                code = str(row.get("Код", "Нет кода")).strip()
                storage = str(row.get("Место хранения", "")).strip()
                status = str(row.get("Статус", "")).strip()
                project = str(row.get("Проект", "")).strip()
                dept = str(row.get("Отдел МТО", "")).strip()
                curator = str(row.get("Куратор МТО", "")).strip()
                qr_code = str(row.get("QR Код", "—")).strip()
                sum_val = str(row.get("Сумма", "—")).strip()
                doc = str(row.get("Заявка на оплату", "")).strip()
                
                plastic_type = str(row.get("Тип", "")).strip()
                plastic_color = str(row.get("Цвет", "")).strip()

                weight = str(row.get("Вес", "")).strip()

                hl_name = highlight_text(name, tokens)
                hl_code = highlight_text(code, tokens)
                hl_storage = highlight_text(storage if storage else "Не указано", tokens)
                hl_project = highlight_text(project if project else "—", tokens)
                hl_curator = highlight_text(curator if curator else "—", tokens)
                hl_dept = highlight_text(dept if dept else "—", tokens)
                hl_plastic_type = highlight_text(plastic_type, tokens)
                hl_plastic_color = highlight_text(plastic_color, tokens)

                loc_tag = f"✅ [{storage}]" if storage else "❓ [Без локации]"
                
                extra_info = []
                if plastic_type: extra_info.append(plastic_type)
                if plastic_color: extra_info.append(plastic_color)
                extra_suffix = f" | {' '.join(extra_info)}" if extra_info else ""
                
                expander_title = f"{loc_tag} {name} | Код: {code}{extra_suffix}"

                with st.expander(expander_title):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown(f"**📍 Место хранения:** {hl_storage}", unsafe_allow_html=True)
                        if "Сумма" in df.columns: st.markdown(f"**📦 Сумма:** {sum_val}")
                    with col2:
                        if "Статус" in df.columns: st.markdown(f"**📌 Статус:** {status if status else '—'}")
                        if "QR Код" in df.columns: st.markdown(f"**🏷️ QR код:** {qr_code}")

                    st.divider()

                    badges = [
                        create_badge("🚀", "Проект", hl_project, "#eef2ff", "#3730a3") if project else "",
                        create_badge("🏢", "Отдел", hl_dept, "#f3f4f6", "#1f2937") if dept else "",
                        create_badge("👤", "Куратор", hl_curator, "#f0fdf4", "#166534") if curator else "",
                        create_badge("📄", "Заявка", doc, "#fef3c7", "#92400e") if doc else "",
                        create_badge("🧵", "Тип", hl_plastic_type, "#e0f2fe", "#0369a1") if plastic_type else "",
                        create_badge("🎨", "Цвет", hl_plastic_color, "#fce7f3", "#be185d") if plastic_color else "",
                        create_badge("⚖️", "Остаток", f"{weight} г", "#fef3c7", "#78350f") if weight else ""
                    ]
                    
                    badges_html = "".join([b for b in badges if b != ""])

                    if badges_html:
                        st.markdown(
                            f'<div style="display: flex; gap: 8px; flex-wrap: wrap; margin-top: 4px; margin-bottom: 4px;">{badges_html}</div>',
                            unsafe_allow_html=True,
                        )