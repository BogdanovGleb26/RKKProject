import re

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


def create_badge(icon: str, label: str, value: str, bg_color: str, text_color: str) -> str:
    """Генерирует HTML для красивого стикера (бейджа)."""
    if not value or value == "—":
        return ""
    return f'<span style="background-color: {bg_color}; color: {text_color}; padding: 4px 10px; border-radius: 6px; font-size: 13px; font-weight: 500; white-space: nowrap; margin-bottom: 4px;">{icon} {label}: {value}</span>'