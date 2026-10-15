import re
from html import escape

import io
from pathlib import Path

import streamlit as st
from PIL import Image

import qrcode
from config import IMAGES_DIR, QR_FORM_URL

HIGHLIGHT_STYLE = (
    "background-color: #ffe066; padding: 2px 4px; "
    "border-radius: 4px; color: #000;"
)

BADGE_STYLE = (
    "padding: 4px 10px; border-radius: 6px; font-size: 13px; "
    "font-weight: 500; white-space: nowrap; margin-bottom: 4px;"
)


def highlight_text(text: str, query_tokens: list[str]) -> str:
    """Подсвечивает найденные токены запроса тегом <mark>.

    ВАЖНО: возвращает HTML-safe строку. Результат нельзя повторно
    прогонять через html.escape — иначе тег <mark> превратится в текст.
    """
    text = "" if text is None else str(text)
    safe_text = escape(text)

    if not query_tokens:
        return safe_text

    escaped_tokens = sorted(
        [re.escape(escape(str(t))) for t in query_tokens if str(t).strip()],
        key=len,
        reverse=True,
    )
    if not escaped_tokens:
        return safe_text

    pattern = re.compile(f"({'|'.join(escaped_tokens)})", re.IGNORECASE)
    return pattern.sub(
        lambda m: f'<mark style="{HIGHLIGHT_STYLE}">{m.group(0)}</mark>',
        safe_text,
    )


def create_badge(
    icon: str,
    label: str,
    value: str,
    bg_color: str,
    text_color: str,
) -> str:
    """Генерирует HTML для бейджа.

    ВАЖНО: `value` может приходить:
      - как «сырое» значение из Excel → экранируется здесь;
      - как результат highlight_text → уже HTML, повторное экранирование
        сломает <mark>.

    Чтобы не путаться, используем маркер: если в value есть '<mark',
    считаем его уже готовым HTML.
    """
    if value is None:
        return ""
    value_str = str(value)
    if not value_str or value_str == "—":
        return ""

    # Экранируем только если это НЕ наш собственный <mark>-HTML
    if "<mark" not in value_str:
        value_str = escape(value_str)

    safe_icon = escape(str(icon))
    safe_label = escape(str(label))
    # bg_color/text_color ожидаем как CSS — но подстрахуемся от кавычек
    safe_bg = str(bg_color).replace('"', "")
    safe_fg = str(text_color).replace('"', "")

    return (
        f'<span style="background-color: {safe_bg}; color: {safe_fg}; '
        f'{BADGE_STYLE}">{safe_icon} {safe_label}: {value_str}</span>'
    )

# =============================================================================
# КАРТИНКИ ТОВАРОВ
# =============================================================================

# Приоритет расширений: чем раньше — тем выше.
IMAGE_EXTENSIONS_PRIORITY = (".jpg", ".jpeg", ".png", ".webp")

# Плейсхолдер, если фото или QR нет. Лежит в IMAGES_DIR.
PLACEHOLDER_FILENAME = "no_photo.jpg"

# Ресайз фото: до 800 px по большей стороне.
PHOTO_MAX_SIZE = 800

# TTL кеша картинок — синхронно с данными (300 сек).
IMAGE_CACHE_TTL = 300


def ensure_images_dir() -> None:
    """Создаёт папку IMAGES_DIR, если её нет. Идемпотентно."""
    try:
        Path(IMAGES_DIR).mkdir(parents=True, exist_ok=True)
    except OSError:
        # Молча игнорируем — если не смогли создать, просто не будет картинок.
        # Логировать тут нечего, это не критично для работы приложения.
        pass


def _pick_best_file(base_path: Path) -> Path | None:
    """Ищет файл с именем base_path + одно из поддерживаемых расширений.

    Возвращает путь или None. Если найдено несколько — по приоритету расширений.
    """
    stem = base_path.name  # например, "00000000119"
    parent = base_path.parent

    if not parent.exists():
        return None

    for ext in IMAGE_EXTENSIONS_PRIORITY:
        candidate = parent / f"{stem}{ext}"
        if candidate.is_file():
            return candidate
    return None


def find_item_image(code: str, kind: str) -> Path | None:
    """Ищет картинку для позиции.

    :param code: значение колонки «Код» (например, "00000000119").
    :param kind: "photo" → <code>.<ext>; "qr" → <code>_qr.<ext>.
    :return: Path или None, если файл не найден.
    """
    if not code:
        return None

    code_clean = str(code).strip()
    if not code_clean:
        return None

    images_dir = Path(IMAGES_DIR)

    if kind == "qr":
        base = images_dir / f"{code_clean}_qr"
    else:
        base = images_dir / code_clean

    return _pick_best_file(base)


def _read_and_resize_to_bytes(path: Path, kind: str, max_size: int) -> bytes:
    """Читает картинку, ресайзит (для фото) и возвращает bytes.

    Для kind='photo' — JPEG, ресайз до max_size.
    Для kind='qr'    — PNG без ресайза (сохраняем чёткость).
    """
    img = Image.open(path)

    if kind == "photo":
        # Для фото — ресайз и JPEG.
        # RGBA/P → RGB, иначе JPEG не сохранится.
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        img.thumbnail((max_size, max_size), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue()

    # QR: без ресайза, PNG. Конвертируем только если режим мешает PNG-сохранению.
    # PNG ест почти всё, но палитровые картинки иногда лучше конвертить в RGB.
    if img.mode == "P":
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@st.cache_data(ttl=IMAGE_CACHE_TTL, show_spinner=False)
def load_item_image_bytes(path_str: str, kind: str, max_size: int) -> bytes:
    """Кешируемая обёртка над _read_and_resize_to_bytes.

    Кешируем по (путь, тип, размер), чтобы разные карточки с одинаковым
    файлом не ресайзили его повторно.
    """
    return _read_and_resize_to_bytes(Path(path_str), kind, max_size)


@st.cache_data(ttl=IMAGE_CACHE_TTL, show_spinner=False)
def get_placeholder_bytes(max_size: int = PHOTO_MAX_SIZE) -> bytes | None:
    """Возвращает bytes плейсхолдера no_photo.jpg. None, если файла нет."""
    placeholder_path = Path(IMAGES_DIR) / PLACEHOLDER_FILENAME
    if not placeholder_path.is_file():
        return None
    try:
        return _read_and_resize_to_bytes(placeholder_path, "photo", max_size)
    except Exception:
        return None


def get_item_image_bytes(code: str, kind: str) -> bytes | None:
    """Высокоуровневый хелпер для вьюх.

    Пытается найти реальную картинку; если нет — возвращает плейсхолдер.
    Возвращает None, если и плейсхолдера нет — тогда вьюха рисует текст.
    """
    path = find_item_image(code, kind)
    if path is not None:
        try:
            if kind == "qr":
                return load_item_image_bytes(str(path), kind, 0)
            return load_item_image_bytes(str(path), kind, PHOTO_MAX_SIZE)
        except Exception:
            # Битый файл — покажем плейсхолдер.
            pass
    return get_placeholder_bytes(PHOTO_MAX_SIZE)

# =============================================================================
# ГЕНЕРАЦИЯ QR-КОДОВ
# =============================================================================

# Размер QR-картинки (в пикселях) — соответствует box_size=10, border=4.
QR_GENERATION_SIZE = 400

# Error correction level: M — оптимально для сканирования с экрана.
QR_ERROR_CORRECTION = qrcode.constants.ERROR_CORRECT_M


@st.cache_data(ttl=IMAGE_CACHE_TTL, show_spinner=False)
def generate_qr_png_bytes(qr_value: str) -> bytes | None:
    """Генерирует PNG-байты QR-кода из значения колонки «QR код».

    Собирает полный URL (QR_FORM_URL + qr_value) и генерирует QR.
    Кешируется по значению qr_value — две позиции с одинаковым
    значением получат один и тот же QR из кеша.
    """
    if not qr_value:
        return None
    if not QR_FORM_URL:
        # URL формы не задан в .env — генерация невозможна.
        return None

    qr_value_clean = str(qr_value).strip()
    if not qr_value_clean:
        return None

    full_url = f"{QR_FORM_URL}{qr_value_clean}"

    try:
        qr = qrcode.QRCode(
            version=1,
            error_correction=QR_ERROR_CORRECTION,
            box_size=10,
            border=4,
        )
        qr.add_data(full_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        # Битое значение, слишком длинное, проблемы с кодировкой — вернём None,
        # вьюха отрисует плейсхолдер.
        return None


def get_item_qr_bytes(code: str, qr_value: str) -> bytes | None:
    """Высокоуровневый хелпер для вьюх.

    Приоритет:
      1. Файл <code>_qr.<ext> в IMAGES_DIR — если есть, используем его.
      2. Генерация из qr_value — если файла нет, но есть значение.
      3. Плейсхолдер no_photo.jpg — если ни файла, ни значения.
    """
    # 1. Файл
    path = find_item_image(code, "qr")
    if path is not None:
        try:
            return load_item_image_bytes(str(path), "qr", 0)
        except Exception:
            pass  # битый файл → пробуем генерацию

    # 2. Генерация
    if qr_value:
        generated = generate_qr_png_bytes(str(qr_value))
        if generated:
            return generated

    # 3. Плейсхолдер
    return get_placeholder_bytes(PHOTO_MAX_SIZE)