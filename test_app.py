import os
import re
import io
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
TARGET_SHEET = 0


@st.cache_data(ttl=300)
def load_data():
    y = yadisk.YaDisk(token=TOKEN)
    if not y.check_token():
        raise Exception("Неверный токен Яндекс.Диска")

    buffer = io.BytesIO()
    y.download(DISK_PATH, buffer)
    buffer.seek(0)

    excel_file = pd.ExcelFile(buffer, engine="calamine")
    df = excel_file.parse(sheet_name=TARGET_SHEET)

    # Очищаем от NaN
    df = df.fillna("")

    # Приводим типы к строкам и зачищаем .0 у кодов
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
    # Берем только существующие в df колонки
    available_search_cols = [col for col in search_columns if col in df.columns]

    df["_search_corpus"] = (
        df[available_search_cols].astype(str).agg(" ".join, axis=1).str.lower()
    )

    return df


def highlight_text(text: str, query_tokens: list[str]) -> str:
    """Подсвечивает найденные токены запроса тегом <mark>."""
    if not text or not query_tokens:
        return text

    # Экранируем спецсимволы и сортируем по длине (сначала длинные совпадения)
    tokens = sorted(
        [re.escape(t) for t in query_tokens if len(t) > 0],
        key=len,
        reverse=True,
    )
    if not tokens:
        return text

    pattern = re.compile(f"({'|'.join(tokens)})", re.IGNORECASE)

    # Стиль подсвечивания: аккуратная желтая плашка с закруглением
    def replace_func(match):
        return f'<mark style="background-color: #ffe066; padding: 2px 4px; border-radius: 4px; color: #000;">{match.group(0)}</mark>'

    return pattern.sub(replace_func, text)


# --- Интерфейс ---

st.title("📦 Где что лежит")

try:
    with st.spinner("Синхронизация со складом..."):
        df = load_data()
except Exception as e:
    st.error(f"Ошибка загрузки базы: {e}")
    st.stop()

# 1. Инициализация ключа поисковой строки в session_state
if "search_input_field" not in st.session_state:
    st.session_state.search_input_field = ""

# Быстрые фильтры (Идея 3)
st.caption("⚡ Быстрый фильтр:")
chip_cols = st.columns(4)

# При клике прямо меняем значение st.session_state.search_input_field
with chip_cols[0]:
    if st.button("🖨️ Пластик", use_container_width=True):
        st.session_state.search_input_field = "Пластик"
        st.rerun()

with chip_cols[1]:
    if st.button("🔌 Принтер", use_container_width=True):
        st.session_state.search_input_field = "Принтер"
        st.rerun()

with chip_cols[2]:
    if st.button("📍 Цех №4", use_container_width=True):
        st.session_state.search_input_field = "Цех №4"
        st.rerun()

with chip_cols[3]:
    if st.button("👤 Смирнова", use_container_width=True):
        st.session_state.search_input_field = "Смирнова"
        st.rerun()

# 2. Поисковая строка с прямым связыванием key
raw_input = st.text_input(
    "Поиск по складу",
    placeholder="Название, код, локация (напр. Стеллаж А1), проект...",
    help="Ищет по совпадению всех слов в названии, коде, локации, проекте и кураторе.",
    key="search_input_field",  # Streamlit сам берет значение из st.session_state.search_input_field
)

search_query = raw_input.strip().lower()

# Если поисковая строка пустая — базовый экран
if not search_query:
    st.info("👋 Введите название товара, код или локацию (например, **Стеллаж A1**), чтобы посмотреть содержимое.")

    col1, col2 = st.columns(2)
    with col1:
        st.metric(label="Всего позиций", value=len(df))
    with col2:
        locations_count = df["Место хранения"].replace("", None).nunique()
        st.metric(label="Занято ячеек", value=locations_count)

else:
    # -------------------------------------------------------------
    # ЛОГИКА МУЛЬТИ-ПОИСКА (включая поиск по полю 'Место хранения')
    # -------------------------------------------------------------
    if search_query == "без места":
        mask = df["Место хранения"].astype(str).str.strip() == ""
        tokens = []
    else:
        tokens = [t for t in search_query.split() if len(t) > 0]
        if tokens:
            mask = df["_search_corpus"].apply(
                lambda corpus: all(t in corpus for t in tokens)
            )
        else:
            mask = pd.Series([False] * len(df))

    filtered_df = df[mask]

    st.caption(f"Найдено позиций: {len(filtered_df)}")

    if filtered_df.empty:
        st.warning("Ничего не найдено. Проверьте название детали или номер локации.")
    else:
        for index, row in filtered_df.iterrows():
            name = str(row.get("Номенклатура", "Без названия")).strip()
            code = str(row.get("Код", "Нет кода")).strip()
            storage = str(row.get("Место хранения", "")).strip()
            status = str(row.get("Статус", "")).strip()
            project = str(row.get("Проект", "")).strip()
            dept = str(row.get("Отдел МТО", "")).strip()
            curator = str(row.get("Куратор МТО", "—")).strip()
            qr_code = str(row.get("QR код", "—")).strip()
            sum_val = str(row.get("Сумма", "—")).strip()
            doc = str(row.get("Заявка на оплату", "")).strip()

            # Подсветка токенов
            hl_name = highlight_text(name, tokens)
            hl_code = highlight_text(code, tokens)
            hl_storage = highlight_text(storage if storage else "Не указано", tokens)
            hl_project = highlight_text(project, tokens)
            hl_curator = highlight_text(curator, tokens)

            icon = "🖨️" if any(p in name.lower() for p in ["пластик", "petg", "pla", "abs", "flex"]) else "🔧"

            # Наглядный заголовок: [Локация] -> Название товара
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

                st.markdown(f"**🚀 Проект:** {hl_project if project else '—'}", unsafe_allow_html=True)
                st.markdown(f"**🏢 Отдел МТО:** {dept if dept else '—'}")

                st.markdown(
                    f"**👤 Куратор:** {hl_curator}", unsafe_allow_html=True
                )

                if doc:
                    st.markdown(f"**📄 Документ:** {doc}")