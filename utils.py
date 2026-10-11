import re
from html import escape


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