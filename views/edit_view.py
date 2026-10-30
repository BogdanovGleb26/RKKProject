"""
Страница «Редактирование» — CRUD для procurement.

Пока только для Закупок (пилот).
"""

import streamlit as st

import config
from db import get_sheet_df, fetch_df
from views.crud_views import procurement_form


PAGE_SIZE = 50
SHEET = "Закупки"  # пилотная таблица


def _ensure_user_name() -> str | None:
    """Проверяет, введено ли имя. Если нет — показывает форму ввода.
    Возвращает имя или None (если не введено)."""
    if st.session_state.get("user_name"):
        return st.session_state.user_name

    st.info(
        "👤 Для редактирования нужно представиться — "
        "это нужно для аудита изменений (кто что поменял)."
    )
    with st.form("user_name_form"):
        name = st.text_input(
            "Ваше имя",
            placeholder="Например: Иванов И.И.",
            key="user_name_input",
        )
        submitted = st.form_submit_button("Продолжить", type="primary")

    if submitted:
        if name.strip():
            st.session_state.user_name = name.strip()
            st.rerun()
        else:
            st.warning("Введите имя, чтобы продолжить.")

    return None


def _render_search_panel(df) -> None:
    """Поле поиска + пагинация. Возвращает отфильтрованный df."""
    st.caption("🔎 Поиск по позициям для редактирования")
    query = st.text_input(
        "Поиск",
        placeholder="Код, номенклатура, место хранения...",
        key="edit_search_input",
    ).strip().lower()

    if not query:
        filtered = df
    else:
        tokens = [t for t in query.split() if t]
        mask = df["_search_corpus"].apply(
            lambda corpus: all(t in str(corpus) for t in tokens)
        )
        filtered = df[mask]

    total = len(filtered)
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE

    if total_pages > 1:
        page = st.number_input(
            "Страница",
            min_value=1,
            max_value=total_pages,
            value=1,
            step=1,
            key=f"edit_page_{query}",
            label_visibility="collapsed",
        )
    else:
        page = 1

    start = (page - 1) * PAGE_SIZE
    end = start + PAGE_SIZE

    if total_pages > 1:
        st.caption(f"Найдено: **{total}** — страница {page} из {total_pages}")
    else:
        st.caption(f"Найдено: **{total}**")

    return filtered.iloc[start:end]


def _render_item_card(row, idx: int) -> None:
    """Одна карточка позиции с кнопками Редактировать / Удалить."""
    item_id = row.get("id")
    code = str(row.get("Код", "")).strip()
    name = (
        str(row.get("Номенклатура", "")).strip()
        or str(row.get("Название", "")).strip()
        or "Без названия"
    )
    storage = str(row.get("Место хранения", "")).strip()
    status = str(row.get("Статус", "")).strip()

    title = f"{'✅ [' + storage + ']' if storage else '❓ [Без локации]'} {name}"
    if code:
        title += f" | Код: {code}"

    with st.container(border=True):
        st.markdown(f"**{title}**")
        if status:
            st.caption(f"📌 Статус: {status}")

        col_edit, col_del, col_space = st.columns([1, 1, 2])
        with col_edit:
            if st.button(
                "✏️ Редактировать",
                key=f"edit_{item_id}",
                width="stretch",
            ):
                st.session_state.edit_action = {"action": "edit", "item_id": item_id}
                st.rerun()
        with col_del:
            if st.button(
                "🗑️ Удалить",
                key=f"del_{item_id}",
                width="stretch",
            ):
                st.session_state.edit_action = {"action": "delete", "item_id": item_id}
                st.rerun()


def render():
    st.title("✏️ Редактирование")
    st.caption("Пилот: редактирование доступно **только для листа «Закупки»**.")

    # Проверяем доступ к БД
    if not config.DB_ENABLED:
        st.error(
            "❌ PostgreSQL не сконфигурирован. "
            "Редактирование доступно только в режиме PostgreSQL."
        )
        return

    source = st.session_state.get("data_source", config.DEFAULT_DATA_SOURCE)
    if source != "postgres":
        st.warning(
            "⚠️ Редактирование доступно **только при источнике данных PostgreSQL**. "
            f"Сейчас выбран: **{source}**. Переключите источник в сайдбаре."
        )
        return

    # Проверяем имя
    user = _ensure_user_name()
    if user is None:
        return

    # Если активно действие CRUD — рендерим соответствующую форму и выходим
    action = st.session_state.get("edit_action")
    if action:
        if action["action"] == "create":
            procurement_form.render_create_form(user)
        elif action["action"] == "edit":
            procurement_form.render_edit_form(action["item_id"], user)
        elif action["action"] == "delete":
            procurement_form.render_delete_confirm(action["item_id"], user)
        return

    # Основной экран: кнопка «Добавить» + поиск + список
    col_add, col_space = st.columns([1, 3])
    with col_add:
        if st.button("➕ Добавить позицию", width="stretch", type="primary"):
            st.session_state.edit_action = {"action": "create", "item_id": None}
            st.rerun()

    st.divider()

    # Загружаем данные
    try:
        with st.spinner("Загрузка из PostgreSQL..."):
            df, last_updated = get_sheet_df(SHEET, source="postgres")
    except Exception as e:
        st.error(f"Ошибка загрузки: {e}")
        return

    if df.empty:
        st.info("В таблице пока нет позиций.")
        return

    st.caption(f"🕒 Данные: **{last_updated}**")

    page_df = _render_search_panel(df)
    if page_df.empty:
        st.warning("Ничего не найдено.")
        return

    for idx, (_, row) in enumerate(page_df.iterrows()):
        _render_item_card(row, idx)