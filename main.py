import io
import socket
import qrcode
import streamlit as st

# Настройка страницы всегда должна быть самым первым вызовом Streamlit!
st.set_page_config(
    page_title="Инвентаризация 📦",
    page_icon="🔍",
    layout="centered",
    initial_sidebar_state="expanded",  # Сайдбар по умолчанию открыт
)

# Импортируем модули после настройки страницы
import config
from views import analytics_view, scanning_view, search_view


# --- Вспомогательные функции для QR-кода и IP ---
def get_local_ip() -> str:
  """Определяет локальный IPv4 адрес компьютера в сети."""
  try:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    ip = s.getsockname()[0]
    s.close()
    return ip
  except Exception:
    return "127.0.0.1"


def generate_qr_code(url: str) -> bytes:
  """Генерирует QR-код в формате PNG (в памяти)."""
  qr = qrcode.QRCode(
      version=1,
      error_correction=qrcode.constants.ERROR_CORRECT_L,
      box_size=10,
      border=2,
  )
  qr.add_data(url)
  qr.make(fit=True)

  img = qr.make_image(fill_color="black", back_color="white")
  buf = io.BytesIO()
  img.save(buf, format="PNG")
  return buf.getvalue()


@st.dialog("📱 Подключение с мобильного")
def show_qr_modal(app_url: str):
  """Модальное окно с QR-кодом и ссылкой."""
  st.write("Отсканируйте QR-код камерой телефона для входа в приложение:")

  qr_image = generate_qr_code(app_url)
  st.image(qr_image, use_container_width=True)

  st.caption("Прямая ссылка на приложение:")
  st.code(app_url, language="text")

  st.info(
      "📌 **Важно:** Телефон и ПК должны быть подключены к одной Wi-Fi /"
      " локальной сети."
  )


# --- Инициализация состояния ---
if "app_mode" not in st.session_state:
  st.session_state.app_mode = "Поиск"

# --- Боковое меню (Сайдбар) ---
st.sidebar.title("🎛️ Меню")

# Радио-кнопка для переключения между разделами
app_mode = st.sidebar.radio(
    "Выберите раздел:",
    options=["Поиск", "Аналитика", "Сканирование"],
    index=0,
)

st.sidebar.divider()

# Кнопка вызова модального окна с QR-кодом
local_ip = get_local_ip()
# Укажите порт вашего приложения (по умолчанию Streamlit использует 8501)
app_port = 8501
app_url = f"http://{local_ip}:{app_port}"

if st.sidebar.button(
    "📲 Открыть на телефоне", use_container_width=True, type="primary"
):
  show_qr_modal(app_url)

st.sidebar.link_button(
    "💻 Исходный код на GitHub",
    "https://github.com/BogdanovGleb26/RKKProject",
    use_container_width=True,
)

st.sidebar.caption("© 2026 Инвентаризация v1.0.0")

# --- Маршрутизация (Роутинг) ---
if app_mode == "Поиск":
  search_view.render()
elif app_mode == "Аналитика":
  analytics_view.render()
elif app_mode == "Сканирование":
  scanning_view.render()