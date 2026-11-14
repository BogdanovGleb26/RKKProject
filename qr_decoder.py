"""Распознавание QR-кодов: каскад декодеров + предобработка + масштабы + тайлинг.

Зависимости:
    pip install opencv-contrib-python-headless zxing-cpp
(opencv-python и opencv-contrib-python вместе ставить нельзя — только один из них)

Если какого-то декодера нет (zxing-cpp или wechat_qrcode), он просто пропускается.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Iterator

import cv2
import numpy as np

try:
    import zxingcpp
except ImportError:  # необязательная зависимость
    zxingcpp = None

log = logging.getLogger(__name__)

_local = threading.local()


# ──────────────────────────── декодеры ────────────────────────────
def _dec_zxing(img: np.ndarray) -> list[str]:
    if zxingcpp is None:
        return []
    try:
        results = zxingcpp.read_barcodes(img, formats=zxingcpp.BarcodeFormat.QRCode)
    except TypeError:  # старые версии без параметра formats
        results = zxingcpp.read_barcodes(img)
    return [r.text for r in results if r.text]


def _get_wechat():
    """WeChat-детектор: по одному экземпляру на поток (безопасно для Streamlit)."""
    if not hasattr(cv2, "wechat_qrcode_WeChatQRCode"):
        return None
    det = getattr(_local, "wechat", None)
    if det is None:
        det = cv2.wechat_qrcode_WeChatQRCode()
        _local.wechat = det
    return det


def _dec_wechat(img: np.ndarray) -> list[str]:
    det = _get_wechat()
    if det is None:
        return []
    texts, _ = det.detectAndDecode(img)
    return [t for t in texts if t]


def _dec_opencv(img: np.ndarray) -> list[str]:
    det = cv2.QRCodeDetector()  # локальный экземпляр — thread-safe
    try:
        ok, info, _, _ = det.detectAndDecodeMulti(img)
    except cv2.error:
        return []
    return [i for i in info if i] if ok else []


Decoder = tuple[str, Callable[[np.ndarray], list[str]]]
DECODERS: tuple[Decoder, ...] = (
    ("zxing", _dec_zxing),
    ("wechat", _dec_wechat),
    ("opencv", _dec_opencv),
)
FAST_DECODERS: tuple[Decoder, ...] = DECODERS[:2]  # для тайлов (opencv там слишком медленный)


# ──────────────────────────── предобработка ────────────────────────────
def _to_gray(img_np: np.ndarray) -> np.ndarray:
    if img_np.dtype != np.uint8:
        img_np = cv2.normalize(img_np, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    if img_np.ndim == 3:
        if img_np.shape[2] == 4:
            img_np = cv2.cvtColor(img_np, cv2.COLOR_RGBA2RGB)
        return cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
    return np.ascontiguousarray(img_np)


def _clahe(gray: np.ndarray) -> np.ndarray:
    return cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)


def _variants(gray: np.ndarray) -> Iterator[tuple[str, np.ndarray]]:
    """Ленивая генерация вариантов — останавливаемся, как только что-то нашли."""
    h, w = gray.shape[:2]
    m = max(h, w)

    yield "gray", gray
    yield "clahe", _clahe(gray)

    # Выравнивание освещения: делим на сильно размытый фон
    sigma = max(15, m / 30)
    bg = cv2.GaussianBlur(gray, (0, 0), sigmaX=sigma)
    yield "flat", cv2.divide(gray, bg, scale=255)

    # Резкость для слегка смазанных кадров
    blur = cv2.GaussianBlur(gray, (0, 0), 3)
    yield "sharp", cv2.addWeighted(gray, 1.6, blur, -0.6, 0)

    # Otsu по слегка размытому
    _, otsu = cv2.threshold(
        cv2.GaussianBlur(gray, (5, 5), 0), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )
    yield "otsu", otsu

    # Адаптивный порог: размер блока зависит от размера кадра (раньше было жёстко 11)
    block = min(max(int(m / 40), 11), 101) | 1
    yield "adaptive", cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, block, 2
    )

    # Инверсия: светлый код на тёмном фоне
    yield "invert", cv2.bitwise_not(gray)


def _scaled_images(gray: np.ndarray) -> Iterator[np.ndarray]:
    """Дополнительные масштабы (родной масштаб уже отработан раньше)."""
    h, w = gray.shape[:2]
    m = max(h, w)
    if m < 1200:
        yield cv2.resize(gray, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)
    elif m > 2000:
        s = 1200 / m
        yield cv2.resize(gray, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)


def _starts(n: int, size: int, step: int) -> list[int]:
    if n <= size:
        return [0]
    s = list(range(0, n - size + 1, step))
    if s[-1] != n - size:
        s.append(n - size)
    return s


def _tiles(gray: np.ndarray, size: int = 1200, step: int = 800) -> Iterator[np.ndarray]:
    h, w = gray.shape[:2]
    for y in _starts(h, size, step):
        for x in _starts(w, size, step):
            yield np.ascontiguousarray(gray[y : y + size, x : x + size])


# ──────────────────────────── основной вход ────────────────────────────
def scan_qr_code(img_np: np.ndarray, time_budget: float = 10.0) -> list[str]:
    """Ищет QR-коды на изображении (RGB/RGBA/Gray, uint8). Возвращает список уникальных строк.

    Стадии (переходим к следующей, только если предыдущая ничего не нашла):
      0. исходное изображение, все декодеры;
      1. варианты предобработки;
      2. другой масштаб (апскейл мелких / даунскейл крупных кадров);
      3. тайлинг по полному разрешению (для маленького кода на большом фото).
    Внутри стадии результаты объединяются — несколько QR на кадре не теряются.
    """
    deadline = time.monotonic() + time_budget
    gray = _to_gray(img_np)
    found: dict[str, str] = {}  # текст -> имя декодера, нашедшего первым

    def run(img: np.ndarray, decoders: tuple[Decoder, ...] = DECODERS) -> None:
        for name, fn in decoders:
            try:
                texts = fn(img)
            except Exception:  # один сбойный декодер не должен ронять всё
                log.exception("QR decoder %s failed", name)
                continue
            for t in texts:
                t = t.strip()
                if t and t not in found:
                    found[t] = name

    def timed_out() -> bool:
        return time.monotonic() > deadline

    # Стадия 0
    run(gray)
    if found:
        log.debug("QR stage 0: %s", found)
        return list(found)

    # Стадия 1
    for _, variant in list(_variants(gray))[1:]:
        run(variant)
        if timed_out():
            break
    if found:
        log.debug("QR stage 1: %s", found)
        return list(found)

    # Стадия 2
    for scaled in _scaled_images(gray):
        for i, (_, variant) in enumerate(_variants(scaled)):
            run(variant)
            if i >= 3 or timed_out():  # первых вариантов достаточно
                break
    if found:
        log.debug("QR stage 2: %s", found)
        return list(found)

    # Стадия 3
    if max(gray.shape[:2]) > 1500 and not timed_out():
        for tile in _tiles(gray):
            run(tile, FAST_DECODERS)
            if not found:
                run(_clahe(tile), FAST_DECODERS)
            if timed_out():
                break
        log.debug("QR stage 3: %s", found)

    return list(found)
