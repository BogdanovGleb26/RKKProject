import pandas as pd
import streamlit as st
import re
from data_loader import load_data
from utils import highlight_text, create_badge, get_item_image_bytes, get_item_qr_bytes
import config


# Сколько результатов показывать на одной странице
PAGE_SIZE = 50


def render():
    st.title("📦 Поиск по складу")

    source = st.session_state.get("data_source", config.DEFAULT_DATA_SOURCE)
    source_label = "Локальный ПК" if source == "local" else "Яндекс.Диск"

    # Список листов + ключ для сохранения выбора между вкладками
    SHEET_OPTIONS = ["Закупки", "ОС Главная", "Пластик"]

    if "selected_sheet_search" not in st.session_state:
        st.session_state.selected_sheet_search = SHEET_OPTIONS[0]

    col_sheet, col_btn = st.columns([4, 1], vertical_alignment="bottom")

    with col_sheet:
        # ← 4.2: segmented_control вместо radio(horizontal=True)
        # ← 2.3: key сохраняет выбор между вкладками
        selected_sheet = st.segmented_control(
            "📄 Раздел учета:",
            options=SHEET_OPTIONS,
            default=st.session_state.selected_sheet_search,
            key="selected_sheet_search",
            selection_mode="single",
        ) or SHEET_OPTIONS[0]

    with col_btn:
        if st.button(
            "🔄 Обновить",
            width="stretch",
            help=f"Сбросить кэш и перечитать данные из источника ({source_label})",
        ):
            load_data.clear()
            from utils import load_item_image_bytes, get_placeholder_bytes, generate_qr_png_bytes
            load_item_image_bytes.clear()
            get_placeholder_bytes.clear()
            generate_qr_png_bytes.clear()
            st.toast(f"Кэш сброшен! Данные перечитаны ({source_label})", icon="🎉")
            st.rerun()

    # Загрузка данных
    try:
        with st.spinner(f"Загрузка раздела «{selected_sheet}» из {source_label}..."):
            # ← прокидываем source (сделано ранее)
            df, last_updated = load_data(selected_sheet, source=source)
            df_print_settings = pd.DataFrame()
            if selected_sheet == "Пластик":
                df_print_settings, _ = load_data("Настройка печати", source=source)
    except Exception as e:
        st.error(f"Ошибка загрузки базы: {e}")
        st.stop()

    # ← 4.3: убрали «на Диске», источник уже виден в сайдбаре
    st.caption(f"🕒 Данные обновлены: **{last_updated}**")

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
            st.dataframe(df_display, width="stretch", hide_index=True)  # ← 4.1

    if "search_input_field" not in st.session_state:
        st.session_state.search_input_field = ""

        # Колбэки для безопасного изменения session_state
    def _set_search(term: str):
        st.session_state.search_input_field = term

    def _clear_search():
        st.session_state.search_input_field = ""

    # Быстрые фильтры
    QUICK_FILTERS = {
        "Закупки": [("🖨️ Пластик", "пластик"), ("🔌 Принтер", "принтер"), ("📍 Ларец", "ларец"), ("👤 Широкова", "Широкова")],
        "ОС Главная": [("⚙️ Система", "система"), ("🚉 Станция", "станция"), ("📷 Камера", "камера"), ("🔢 Цифровой", "цифровой")],
        "Пластик": [("🧵 PLA", "PLA"), ("⚙️ PETG", "PETG"), ("👌 ABS", "ABS"), ("🖤 Чёрный", "черный"), ("PLA + 💚", "PLA зеленый")]
    }

    current_filters = QUICK_FILTERS.get(selected_sheet, [])
    if current_filters:
        st.caption("⚡ Быстрый поиск:")
        chip_cols = st.columns(len(current_filters))
        for idx, (btn_label, search_term) in enumerate(current_filters):
            with chip_cols[idx]:
                st.button(
                    btn_label,
                    width="stretch",
                    key=f"btn_{selected_sheet}_{idx}",
                    on_click=_set_search,
                    args=(search_term,),
                )

    # ← 2.5: кнопка «Сбросить поиск» рядом с полем ввода
    col_search, col_clear = st.columns([5, 1], vertical_alignment="bottom")

    with col_search:
        raw_input = st.text_input(
            "Поиск",
            placeholder="Название, код, место хранения... (например: «без места»)",
            key="search_input_field",
        )
    with col_clear:
        st.button(
            "✖ Сброс",
            width="stretch",
            help="Очистить поиск",
            on_click=_clear_search,
            disabled=not st.session_state.search_input_field,
        )

    search_query = raw_input.strip().lower()

    if not search_query:
        st.info(f"👋 Раздел **«{selected_sheet}»**. Введите название детали, код или локацию, чтобы начать поиск.")
        col1, col2 = st.columns(2)
        with col1:
            st.metric(label="Всего позиций", value=len(df))
        with col2:
            # ← 1.4: пустое место больше не считается за ячейку
            if "Место хранения" in df.columns:
                locations_count = df.loc[
                    df["Место хранения"].astype(str).str.strip() != "",
                    "Место хранения",
                ].nunique()
            else:
                locations_count = 0
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
                        if len(t) <= 3:
                            pattern = r"(?<!\w)" + re.escape(t) + r"(?!\w)"
                        else:
                            pattern = r"(?<!\w)" + re.escape(t)
                        if not re.search(pattern, corpus_str):
                            return False
                    return True

                mask = df["_search_corpus"].apply(matches_exact_words)
            else:
                mask = pd.Series([False] * len(df))

        filtered_df = df[mask]

        # ← Fallback: если основной поиск (по границам слов) ничего не нашёл,
        # а запрос целиком цифровой — пробуем найти как подстроку
        # в колонках «Код» и «QR Код». Это позволяет найти позицию
        # с кодом «ОБ00000000122», введя «122».
        fallback_used = False
        if (
            filtered_df.empty
            and search_query.isdigit()
            and len(search_query) >= 3
        ):
            fallback_cols = [c for c in ("Код", "QR код") if c in df.columns]
            if fallback_cols:
                fallback_mask = pd.Series(False, index=df.index)
                for col in fallback_cols:
                    fallback_mask |= (
                        df[col]
                        .astype(str)
                        .str.lower()
                        .str.contains(search_query, regex=False)
                    )
                if fallback_mask.any():
                    filtered_df = df[fallback_mask]
                    fallback_used = True

        # total_found теперь считаем ПОСЛЕ fallback —
        # иначе пагинация не увидит новые результаты

        total_found = len(filtered_df)

        if filtered_df.empty:
            st.warning("Ничего не найдено.")
        else:
            # ← 2.1: пагинация — 50 результатов на страницу
            total_pages = (total_found + PAGE_SIZE - 1) // PAGE_SIZE

            # Подпись о результатах — своя для обычного поиска и fallback
            if fallback_used:
                caption_base = (
                    f"🔎 По запросу «{search_query}» найдено по коду/QR: **{total_found}**"
                )
            else:
                caption_base = f"Найдено позиций: **{total_found}**"

            if total_pages > 1:
                st.caption(f"{caption_base} — страница 1 из {total_pages}")
                page = st.number_input(
                    "Страница",
                    min_value=1,
                    max_value=total_pages,
                    value=1,
                    step=1,
                    key=f"page_{selected_sheet}_{search_query}",
                    label_visibility="collapsed",
                )
            else:
                st.caption(caption_base)
                page = 1

            start = (page - 1) * PAGE_SIZE
            end = start + PAGE_SIZE
            page_df = filtered_df.iloc[start:end]

            for index, row in page_df.iterrows():
                raw_name = str(row.get("Название", "")).strip()
                raw_nom = str(row.get("Номенклатура", "")).strip()
                name = raw_name if raw_name else (raw_nom if raw_nom else "Без названия")

                code = str(row.get("Код", "Нет кода")).strip()
                storage = str(row.get("Место хранения", "")).strip()
                status = str(row.get("Статус", "")).strip()
                project = str(row.get("Проект", "")).strip()
                dept = str(row.get("Отдел МТО", "")).strip()
                curator = str(row.get("Куратор МТО", "")).strip()
                qr_code = str(row.get("QR код", "—")).strip()
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
                if plastic_type:
                    extra_info.append(plastic_type)
                if plastic_color:
                    extra_info.append(plastic_color)
                extra_suffix = f" | {' '.join(extra_info)}" if extra_info else ""

                expander_title = f"{loc_tag} {name} | Код: {code}{extra_suffix}"

                with st.expander(expander_title):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown(f"**📍 Место хранения:** {hl_storage}", unsafe_allow_html=True)
                        if "Сумма" in df.columns:
                            st.markdown(f"**📦 Сумма:** {sum_val}")
                    with col2:
                        if "Статус" in df.columns:
                            st.markdown(f"**📌 Статус:** {status if status else '—'}")
                        if "QR код" in df.columns:
                            st.markdown(f"**🏷️ QR код:** {qr_code}")

                    st.divider()

                    # ← 1.1: create_badge теперь сам экранирует сырые значения
                    badges = [
                        create_badge("🚀", "Проект", hl_project, "#eef2ff", "#3730a3") if project else "",
                        create_badge("🏢", "Отдел", hl_dept, "#f3f4f6", "#1f2937") if dept else "",
                        create_badge("👤", "Куратор", hl_curator, "#f0fdf4", "#166534") if curator else "",
                        create_badge("📄", "Заявка", doc, "#fef3c7", "#92400e") if doc else "",
                        create_badge("🧵", "Тип", hl_plastic_type, "#e0f2fe", "#0369a1") if plastic_type else "",
                        create_badge("🎨", "Цвет", hl_plastic_color, "#fce7f3", "#be185d") if plastic_color else "",
                        create_badge("⚖️", "Остаток", f"{weight} г", "#fef3c7", "#78350f") if weight else "",
                    ]

                    badges_html = "".join([b for b in badges if b != ""])

                    if badges_html:
                        st.markdown(
                            f'<div style="display: flex; gap: 8px; flex-wrap: wrap; margin-top: 4px; margin-bottom: 4px;">{badges_html}</div>',
                            unsafe_allow_html=True,
                        )
                    
                    # ← Картинки: фото + QR (с генерацией)
                    code_for_image = str(row.get("Код", "")).strip()
                    qr_value_for_image = str(row.get("QR код", "")).strip()

                    photo_bytes = get_item_image_bytes(code_for_image, "photo")
                    qr_bytes = get_item_qr_bytes(code_for_image, qr_value_for_image)

                    st.divider()

                    col_photo, col_qr = st.columns([1, 1])
                    with col_photo:
                        if photo_bytes:
                            st.image(photo_bytes, width=400)
                        else:
                            st.caption("📷 Нет фото")
                    with col_qr:
                        if qr_bytes:
                            st.image(qr_bytes, width=400)
                        else:
                            st.caption("📱 Нет QR")