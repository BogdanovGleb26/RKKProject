import streamlit as st
import pandas as pd
import yadisk
from io import BytesIO
import os
from dotenv import load_dotenv

# Настройка страницы для мобильных устройств
st.set_page_config(
    page_title="Где что лежит 📦",
    page_icon="🔍",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# Загрузка переменных окружения
load_dotenv()
TOKEN = os.getenv("YANDEX_TOKEN")
DISK_PATH = os.getenv("DISK_PATH")
TARGET_SHEET = 0 

@st.cache_data(ttl=300) # Кешируем данные на 5 минут
def load_data():
    y = yadisk.YaDisk(token=TOKEN)
    if not y.check_token():
        raise Exception("Неверный токен Яндекс.Диска")
    
    buffer = BytesIO()
    y.download(DISK_PATH, buffer)
    buffer.seek(0)
    
    excel_file = pd.ExcelFile(buffer, engine='calamine')
    df = excel_file.parse(sheet_name=TARGET_SHEET)
    
    # Очищаем данные от NaN
    df = df.fillna("")

    # ВОЗЬМЕМ ПОКА УНИКАЛЬНЫЕ ПО НОМЕНКЛАТУРЕ, ЧТОБЫ НЕ ДУБЛИРОВАТЬ ВЫВОД
    df = df.drop_duplicates(subset=['Номенклатура'], keep='first')
    
    # Приводим типы для корректного поиска
    df['Код'] = df['Код'].astype(str).str.replace(r'\.0$', '', regex=True)
    return df

# --- Интерфейс ---

st.title("📦 Где что лежит")

try:
    with st.spinner('Синхронизация со складом...'):
        df = load_data()
except Exception as e:
    st.error(f"Ошибка загрузки базы: {e}")
    st.stop()

# Поисковая строка
search_query = st.text_input(
    "Поиск по складу", 
    placeholder="Введите название, код или марку...",
    help="Поиск работает по колонкам 'Код' и 'Номенклатура'"
).strip().lower()

# Если поисковая строка пустая — показываем начальный экран
if not search_query:
    st.info("👋 Введите название товара или код в поле поиска выше, чтобы найти место хранения.")
    
    # Можно вывести общую статистику вместо списка
    col1, col2 = st.columns(2)
    with col1:
        st.metric(label="Всего позиций", value=len(df))
    with col2:
        # Считаем уникальные ячейки хранения, исключая пустые
        locations_count = df['Место хранения'].replace('', None).nunique()
        st.metric(label="Занято ячеек", value=locations_count)

else:
    # Логика фильтрации
    mask = (
        df['Номенклатура'].astype(str).str.lower().str.contains(search_query) |
        df['Код'].astype(str).str.lower().str.contains(search_query)
    )
    filtered_df = df[mask]

    st.caption(f"Найдено позиций: {len(filtered_df)}")

    if filtered_df.empty:
        st.warning("Ничего не найдено. Проверьте правильность запроса.")
    else:
        # Вывод найденных результатов
        for index, row in filtered_df.iterrows():
            name = str(row.get('Номенклатура', 'Без названия')).strip()
            code = str(row.get('Код', 'Нет кода')).strip()
            storage = str(row.get('Место хранения', 'Не указано')).strip()
            status = str(row.get('Статус', '')).strip()
            
            # Иконка в зависимости от типа товара
            icon = "🖨️" if any(p in name.lower() for p in ["пластик", "petg", "pla", "abs"]) else "🔧"
            
            # Карточка товара
            with st.expander(f"{icon} {name} | Код: {code}"):
                col1, col2 = st.columns(2)
                
                with col1:
                    st.markdown(f"**📍 Локация:**\n`{storage if storage else 'Не указано'}`")
                    st.markdown(f"**📦 Остаток:**\n{row.get('Остаток', '—')} {row.get('Ед. изм.', '')}")
                    
                with col2:
                    st.markdown(f"**📌 Статус:**\n{status}")
                    st.markdown(f"**🏷️ QR код:**\n{row.get('QR код', '—')}")
                    
                st.divider()
                
                st.markdown(f"**Проект / Отдел:** {row.get('Проект', '')} / {row.get('Отдел МТО', '')}")
                st.markdown(f"**Куратор:** {row.get('Куратор МТО', '—')}")
                
                if row.get('Заявка на оплату'):
                    st.markdown(f"**Документ:** {row.get('Заявка на оплату')}")