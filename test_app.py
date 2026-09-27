import io
import os
import datetime
import re
import pandas as pd
import streamlit as st
import yadisk
from dotenv import load_dotenv

# --- 1. Настройка страницы Streamlit ---
st.set_page_config(
    page_title="Где что лежит 📦",
    page_icon="🔍",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# --- 2. Загрузка конфигурации и переменных окружения ---
load_dotenv()
TOKEN = os.getenv("YANDEX_TOKEN")
DISK_PATH = os.getenv("DISK_PATH")

if not TOKEN or not DISK_PATH:
    st.error("❌ Не найдены переменные YANDEX_TOKEN или DISK_PATH в файле .env!")
    st.stop()

# --- 3. Функция загрузки и подготовки данных с кэшированием ---
@st.cache_data(ttl=300)
def load_data(sheet_name: str) -> tuple[pd.DataFrame, str]:
    """Загружает конкретный лист из Excel-файла на Яндекс.Диске
    и возвращает DataFrame вместе с датой последнего изменения файла.
    """
    y = yadisk.YaDisk(token=TOKEN)
    if not y.check_token():
        raise Exception("Неверный токен Яндекс.Диска")

    # 1. Получаем метаданные файла для определения даты модификации
    meta = y.get_meta(DISK_PATH)
    raw_modified = getattr(meta, "modified", None)

    if raw_modified:
        # Переводим из UTC в Московское время (UTC+3)
        msk_time = raw_modified + datetime.timedelta(hours=3)
        formatted_modified = msk_time.strftime("%d.%m.%Y в %H:%M")
    else:
        formatted_modified = "Неизвестно"

    # 2. Скачиваем файл в память
    buffer = io.BytesIO()
    y.download(DISK_PATH, buffer)
    buffer.seek(0)

    # Убедитесь, что у вас установлен python-calamine (pip install python-calamine)
    excel_file = pd.ExcelFile(buffer, engine="calamine")

    # Проверяем наличие листа в файле
    if sheet_name not in excel_file.sheet_names:
        return pd.DataFrame(), formatted_modified

    df = excel_file.parse(sheet_name=sheet_name)

    if df.empty:
        return df, formatted_modified

    # Очищаем от NaN
    df = df.fillna("")

    # Приводим типы к строкам и зачищаем .0 у кодов
    if "Код" in df.columns:
        df["Код"] = df["Код"].astype(str).str.replace(r"\.0$", "", regex=True)

    # Создаем поисковый корпус
    search_columns = [
        "Номенклатура",
        "Код",
        "Место хранения",
        "Проект",
        "Куратор МТО",
        "Отдел МТО",
        "QR Код",
        "Название", # Специфично для Пластика
        "Тип",      # Специфично для Пластика
        "Цвет"      # Специфично для Пластика
    ]
    available_search_cols = [col for col in search_columns if col in df.columns]

    if available_search_cols:
        df["_search_corpus"] = (
            df[available_search_cols].astype(str).agg(" ".join, axis=1).str.lower()
        )
    else:
        df["_search_corpus"] = ""

    return df, formatted_modified


def highlight_text(text: str, query_tokens: list[str]) -> str:
    """Подсвечивает найденные токены запроса тегом <mark>."""
    if not text or not query_tokens:
        return text

    tokens = sorted(
        [re.escape(t) for t in query_tokens if len(t) > 0],
        key=len,
        reverse=True,
    )
    if not tokens:
        return text

    pattern = re.compile(f"({'|'.join(tokens)})", re.IGNORECASE)

    def replace_func(match):
        return f'<mark style="background-color: #ffe066; padding: 2px 4px; border-radius: 4px; color: #000;">{match.group(0)}</mark>'

    return pattern.sub(replace_func, text)

# Функция-помощник для создания красивых бейджей (цветовых подсказок)
def create_badge(icon: str, label: str, value: str, bg_color: str, text_color: str) -> str:
    if not value or value == "—":
        return ""
    return f'<span style="background-color: {bg_color}; color: {text_color}; padding: 4px 10px; border-radius: 6px; font-size: 13px; font-weight: 500; white-space: nowrap; margin-bottom: 4px;">{icon} {label}: {value}</span>'


# --- Интерфейс ---

st.title("📦 Где что лежит")

# --- Блок управления: Выбор листа и Кнопка обновления ---
col_sheet, col_btn = st.columns([4, 1], vertical_alignment="bottom")

with col_sheet:
    SHEET_OPTIONS = ["Закупки", "ОС Главная", "Пластик"]
    selected_sheet = st.radio(
        "📄 Раздел учета:",
        options=SHEET_OPTIONS,
        index=0,
        horizontal=True,
    )

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

# Вывод справочника настроек печати (Только для листа «Пластик»)
if selected_sheet == "Пластик" and not df_print_settings.empty:
    with st.expander("⚙️ Справочник: Настройки печати", expanded=True):
        # Исключаем техническую колонку _search_corpus из отображения
        display_cols = [c for c in df_print_settings.columns if c != "_search_corpus"]
        df_display = df_print_settings[display_cols].copy()

        # Форматируем значение 1 или 1.0 обратно в 100% (а также любые другие проценты)
        for col in df_display.columns:
            # Преобразуем числовые/строковые значения 1 или 1.0 в "100%"
            df_display[col] = df_display[col].apply(
                lambda x: "100%" if str(x).strip() in ["1", "1.0"] 
                else (f"{round(float(x)*100)}%" if isinstance(x, (int, float)) and 0 < x < 1 else x)
            )

        st.dataframe(df_display, use_container_width=True, hide_index=True)

if "search_input_field" not in st.session_state:
    st.session_state.search_input_field = ""

# Быстрые фильтры
QUICK_FILTERS = {
    "Закупки": [
        ("🖨️ Пластик", "Пластик"),
        ("🔌 Принтер", "Принтер"),
        ("📍 Цех №4", "Цех №4"),
        ("👤 Смирнова", "Смирнова"),
    ],
    "ОС Главная": [
        ("⚙️ Система", "система"),
        ("🚉 Станция", "станция"),
        ("📷 Камера", "камера"),
        ("🔢 Цифровой", "цифровой"),
    ],
    "Пластик": [
        ("🧵 PLA", "PLA"),
        ("⚙️ PETG", "PETG"),
        ("👌 Filamentarno", "Filamentarno"),
        ("🖤 Чёрный", "черный"),
    ],
}

current_filters = QUICK_FILTERS.get(selected_sheet, [])

if current_filters:
    st.caption("⚡ Быстрый фильтр:")
    chip_cols = st.columns(len(current_filters))
    for idx, (btn_label, search_term) in enumerate(current_filters):
        with chip_cols[idx]:
            if st.button(btn_label, use_container_width=True, key=f"btn_{selected_sheet}_{idx}"):
                st.session_state.search_input_field = search_term
                st.rerun()

# Поисковая строка
raw_input = st.text_input(
    "Поиск по складу",
    placeholder="Название, код, локация (напр. Стеллаж А1), проект...",
    help="Ищет по совпадению всех слов в названии, коде, локации, проекте, кураторе и свойствах.",
    key="search_input_field",
)

search_query = raw_input.strip().lower()

# Базовый экран
if not search_query:
    st.info(f"👋 Раздел **«{selected_sheet}»**. Введите название детали, код или локацию, чтобы начать поиск.")

    col1, col2 = st.columns(2)
    with col1:
        st.metric(label="Всего позиций", value=len(df))
    with col2:
        locations_count = df["Место хранения"].replace("", None).nunique() if "Место хранения" in df.columns else 0
        st.metric(label="Занято ячеек", value=locations_count)

else:
    # --- ЛОГИКА МУЛЬТИ-ПОИСКА ---
    if search_query == "без места":
        if "Место хранения" in df.columns:
            mask = df["Место хранения"].astype(str).str.strip() == ""
        else:
            mask = pd.Series([True] * len(df))
        tokens = []
    else:
        tokens = [t for t in search_query.split() if len(t) > 0]
        if tokens and "_search_corpus" in df.columns:
            mask = df["_search_corpus"].apply(lambda corpus: all(t in corpus for t in tokens))
        else:
            mask = pd.Series([False] * len(df))

    filtered_df = df[mask]
    st.caption(f"Найдено позиций: {len(filtered_df)}")

    if filtered_df.empty:
        st.warning("Ничего не найдено. Проверьте запрос или выберите другой раздел.")
    else:
        for index, row in filtered_df.iterrows():
            # ДИНАМИЧЕСКИЙ ВЫБОР ИМЕНИ (учитываем, что в Пластике колонка называется "Название")
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
            
            # Свойства, специфичные для Пластика
            plastic_type = str(row.get("Тип", "")).strip()
            plastic_color = str(row.get("Цвет", "")).strip()

            # Подсветка токенов
            hl_name = highlight_text(name, tokens)
            hl_code = highlight_text(code, tokens)
            hl_storage = highlight_text(storage if storage else "Не указано", tokens)
            hl_project = highlight_text(project if project else "—", tokens)
            hl_curator = highlight_text(curator if curator else "—", tokens)
            
            hl_plastic_type = highlight_text(plastic_type, tokens)
            hl_plastic_color = highlight_text(plastic_color, tokens)

            # Наглядный заголовок: [Локация] -> Название детали
            loc_tag = f"✅ [{storage}]" if storage else "❓ [Без локации]"
            
            # Добавляем тип/цвет в заголовок, если они есть
            extra_info = []
            if plastic_type: extra_info.append(plastic_type)
            if plastic_color: extra_info.append(plastic_color)
            extra_suffix = f" | {' '.join(extra_info)}" if extra_info else ""
            
            expander_title = f"{loc_tag} {name} | Код: {code}{extra_suffix}"

            with st.expander(expander_title):
                col1, col2 = st.columns(2)

                with col1:
                    st.markdown(f"**📍 Локация:** {hl_storage}", unsafe_allow_html=True)
                    if "Сумма" in df.columns:
                        st.markdown(f"**📦 Сумма:** {sum_val}")

                with col2:
                    if "Статус" in df.columns:
                        st.markdown(f"**📌 Статус:** {status if status else '—'}")
                    if "QR Код" in df.columns:
                        st.markdown(f"**🏷️ QR код:** {qr_code}")

                st.divider()

                # Формируем динамический список бейджей на основе наличия данных
                badges = [
                    create_badge("🚀", "Проект", hl_project, "#eef2ff", "#3730a3") if project else "",
                    create_badge("🏢", "Отдел", dept, "#f3f4f6", "#1f2937") if dept else "",
                    create_badge("👤", "Куратор", hl_curator, "#f0fdf4", "#166534") if curator else "",
                    create_badge("📄", "Заявка", doc, "#fef3c7", "#92400e") if doc else "",
                    
                    # Бейджи специфчные для Пластика:
                    create_badge("🧵", "Тип", hl_plastic_type, "#e0f2fe", "#0369a1") if plastic_type else "",
                    create_badge("🎨", "Цвет", hl_plastic_color, "#fce7f3", "#be185d") if plastic_color else ""
                ]
                
                badges_html = "".join([b for b in badges if b != ""])

                # Выводим единый адаптивный блок
                if badges_html:
                    st.markdown(
                        f"""<div style="display: flex; gap: 8px; flex-wrap: wrap; margin-top: 4px; margin-bottom: 4px;">
                            {badges_html}
                        </div>""",
                        unsafe_allow_html=True,
                    )