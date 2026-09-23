import io
import os
import re
import pandas as pd
import streamlit as st
import yadisk
from dotenv import load_dotenv

# --- Настройка страницы ---
st.set_page_config(
    page_title="Где что лежит 📦",
    page_icon="🔍",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# Загрузка конфигурации из .env
load_dotenv()
TOKEN = os.getenv("YANDEX_TOKEN")
DISK_PATH = os.getenv("DISK_PATH")


@st.cache_data(ttl=300)
def load_data(sheet_name: str) -> pd.DataFrame:
    """Загружает конкретный лист из Excel-файла на Яндекс.Диске."""
    y = yadisk.YaDisk(token=TOKEN)
    if not y.check_token():
        raise Exception("Неверный токен Яндекс.Диска")

    buffer = io.BytesIO()
    y.download(DISK_PATH, buffer)
    buffer.seek(0)

    excel_file = pd.ExcelFile(buffer, engine="calamine")

    # Проверяем наличие листа в файле
    if sheet_name not in excel_file.sheet_names:
        return pd.DataFrame()

    df = excel_file.parse(sheet_name=sheet_name)

    # Если лист полностью пустой
    if df.empty:
        return df

    # Очищаем от NaN
    df = df.fillna("")

    # Приводим типы к строкам и зачищаем .0 у кодов (если колонка есть)
    if "Код" in df.columns:
        df["Код"] = df["Код"].astype(str).str.replace(r"\.0$", "", regex=True)

    # Создаем объединение всех полей в одну нижнерегистровую строку для быстрого мульти-поиска
    search_columns = [
        "Номенклатура",
        "Код",
        "Место хранения",
        "Проект",
        "Куратор МТО",
        "Отдел МТО",
        "QR код",
    ]
    available_search_cols = [col for col in search_columns if col in df.columns]

    if available_search_cols:
        df["_search_corpus"] = (
            df[available_search_cols].astype(str).agg(" ".join, axis=1).str.lower()
        )
    else:
        df["_search_corpus"] = ""

    return df


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


# --- Интерфейс ---

st.title("📦 Где что лежит")

# 1. Переключатель листов Excel (ОС Главная по умолчанию)
SHEET_OPTIONS = ["Закупки", "ОС Главная", "Пластик"]
selected_sheet = st.radio(
    "📄 Раздел учета:",
    options=SHEET_OPTIONS,
    index=0,  # "Закупки" по умолчанию
    horizontal=True,
)

# 2. Загрузка данных выбранного листа
try:
    with st.spinner(f"Загрузка раздела «{selected_sheet}»..."):
        df = load_data(selected_sheet)
except Exception as e:
    st.error(f"Ошибка загрузки базы: {e}")
    st.stop()

# 3. Проверка на пустой лист
if df.empty:
    st.info(f"📭 Лист **«{selected_sheet}»** пока пуст или не содержит данных.")
    st.stop()

# 4. Инициализация ключа поисковой строки в session_state
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
    ],
}

# Получаем фильтры для активного листа
current_filters = QUICK_FILTERS.get(selected_sheet, [])

if current_filters:
    st.caption("⚡ Быстрый фильтр:")
    # Создаем ровно столько колонок, сколько фильтров определено для раздела
    chip_cols = st.columns(len(current_filters))

    for idx, (btn_label, search_term) in enumerate(current_filters):
        with chip_cols[idx]:
            # Уникальный key предотвращает дублирование кнопок при смене листов
            if st.button(btn_label, use_container_width=True, key=f"btn_{selected_sheet}_{idx}"):
                st.session_state.search_input_field = search_term
                st.rerun()

# 5. Поисковая строка с прямым связыванием key
raw_input = st.text_input(
    "Поиск по складу",
    placeholder="Название, код, локация (напр. Стеллаж А1), проект...",
    help="Ищет по совпадению всех слов в названии, коде, локации, проекте и кураторе.",
    key="search_input_field",
)

search_query = raw_input.strip().lower()

# Базовый экран (без поискового запроса)
if not search_query:
    st.info(
        f"👋 Раздел **«{selected_sheet}»**. Введите название детали, код или локацию, чтобы начать поиск."
    )

    col1, col2 = st.columns(2)
    with col1:
        st.metric(label="Всего позиций", value=len(df))
    with col2:
        locations_count = (
            df["Место хранения"].replace("", None).nunique()
            if "Место хранения" in df.columns
            else 0
        )
        st.metric(label="Занято ячеек", value=locations_count)

else:
    # -------------------------------------------------------------
    # ЛОГИКА МУЛЬТИ-ПОИСКА
    # -------------------------------------------------------------
    if search_query == "без места":
        if "Место хранения" in df.columns:
            mask = df["Место хранения"].astype(str).str.strip() == ""
        else:
            mask = pd.Series([True] * len(df))
        tokens = []
    else:
        tokens = [t for t in search_query.split() if len(t) > 0]
        if tokens and "_search_corpus" in df.columns:
            mask = df["_search_corpus"].apply(
                lambda corpus: all(t in corpus for t in tokens)
            )
        else:
            mask = pd.Series([False] * len(df))

    filtered_df = df[mask]

    st.caption(f"Найдено позиций: {len(filtered_df)}")

    if filtered_df.empty:
        st.warning("Ничего не найдено. Проверьте запрос или выберите другой раздел.")
    else:
        for index, row in filtered_df.iterrows():
            name = str(row.get("Номенклатура", "Без названия")).strip()
            code = str(row.get("Код", "Нет кода")).strip()
            storage = str(row.get("Место хранения", "")).strip()
            status = str(row.get("Статус", "")).strip()
            project = str(row.get("Проект", "")).strip()
            dept = str(row.get("Отдел МТО", "")).strip()
            curator = str(row.get("Куратор МТО", "")).strip()
            qr_code = str(row.get("QR код", "—")).strip()
            sum_val = str(row.get("Сумма", "—")).strip()
            doc = str(row.get("Заявка на оплату", "")).strip()

            # Подсветка токенов
            hl_name = highlight_text(name, tokens)
            hl_code = highlight_text(code, tokens)
            hl_storage = highlight_text(storage if storage else "Не указано", tokens)
            hl_project = highlight_text(project if project else "—", tokens)
            hl_curator = highlight_text(curator if curator else "—", tokens)

            # Наглядный заголовок: [Локация] -> Название детали
            loc_tag = f"✅ [{storage}]" if storage else "❓ [Без локации]"
            expander_title = f"{loc_tag} {name} | Код: {code}"

            with st.expander(expander_title):
                col1, col2 = st.columns(2)

                with col1:
                    st.markdown(f"**📍 Локация:** {hl_storage}", unsafe_allow_html=True)
                    st.markdown(f"**📦 Сумма:** {sum_val}")

                with col2:
                    st.markdown(f"**📌 Статус:** {status if status else '—'}")
                    st.markdown(f"**🏷️ QR код:** {qr_code}")

                st.divider()

                # Формируем стикер для документа в одну строку
                doc_badge = (
                    f'<span style="background-color: #fef3c7; color: #92400e; padding: 4px 10px; border-radius: 6px; font-size: 13px; font-weight: 500;">📄 Заявка: {doc}</span>'
                    if doc
                    else ""
                )

                # Выводим единый адаптивный блок стикеров
                st.markdown(
                    f"""<div style="display: flex; gap: 8px; flex-wrap: wrap; margin-top: 4px; margin-bottom: 4px;">
                        <span style="background-color: #eef2ff; color: #3730a3; padding: 4px 10px; border-radius: 6px; font-size: 13px; font-weight: 500;">🚀 Проект: {hl_project}</span>
                        <span style="background-color: #f3f4f6; color: #1f2937; padding: 4px 10px; border-radius: 6px; font-size: 13px; font-weight: 500;">🏢 Отдел: {dept if dept else '—'}</span>
                        <span style="background-color: #f0fdf4; color: #166534; padding: 4px 10px; border-radius: 6px; font-size: 13px; font-weight: 500;">👤 Куратор: {hl_curator}</span>
                        {doc_badge}
                    </div>""",
                    unsafe_allow_html=True,
                )