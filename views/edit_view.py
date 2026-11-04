"""
Страница «Редактирование» — CRUD для таблиц.

Поддерживаемые таблицы: procurement (Закупки), os_main (ОС Главная).
"""

import streamlit as st

import config
from db import get_sheet_df, fetch_df
from views.crud_views import procurement_form, os_main_form, plastic_form, plastic_settings_form


PAGE_SIZE = 50

# Маппинг: human label → (sheet_name, table_id, form_module)
SHEET_OPTIONS = {
    "Закупки": {
        "sheet": "Закупки",
        "table": "procurement",
        "form": procurement_form,
    },
    "ОС Главная": {
        "sheet": "ОС Главная",
        "table": "os_main",
        "form": os_main_form,
    },
    "Пластик": {
        "sheet": "Пластик",
        "table": "plastic_spools",
        "form": plastic_form,
    },
    "Настройки пластика": {                    # ← НОВОЕ
        "sheet": "Настройка печати",
        "table": "plastic_settings",
        "form": plastic_settings_form,
    },
}


def _ensure_user_name() -> str | None:
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


def _render_search_panel(df):
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


def _render_item_card(row, idx: int, table_id: str):
    item_id = row.get("id")

    # Для справочника plastic_settings — своё отображение
    if table_id == "plastic_settings":
        plastic_type = str(row.get("Тип пластика", "")).strip() or "Без названия"
        nozzle = str(row.get("Сопло (°C)", "")).strip() or "—"
        bed = str(row.get("Стол (°C)", "")).strip() or "—"
        fan = str(row.get("Обдув, %", "")).strip() or "—"

        with st.container(border=True):
            st.markdown(f"**{plastic_type}**")
            st.caption(
                f"🌡️ Сопло: {nozzle} · 🛏️ Стол: {bed} · 💨 Обдув: {fan}"
            )

            col_edit, col_del, col_space = st.columns([1, 1, 2])
            with col_edit:
                if st.button("✏️ Редактировать", key=f"edit_{table_id}_{item_id}", width="stretch"):
                    st.session_state.edit_action = {
                        "action": "edit",
                        "item_id": item_id,
                        "table": table_id,
                    }
                    st.rerun()
            with col_del:
                if st.button("🗑️ Удалить", key=f"del_{table_id}_{item_id}", width="stretch"):
                    st.session_state.edit_action = {
                        "action": "delete",
                        "item_id": item_id,
                        "table": table_id,
                    }
                    st.rerun()
        return  # ← выходим, для остальных таблиц не рендерим

    # Обычные таблицы (procurement, os_main, plastic_spools)
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
            if st.button("✏️ Редактировать", key=f"edit_{table_id}_{item_id}", width="stretch"):
                st.session_state.edit_action = {
                    "action": "edit",
                    "item_id": item_id,
                    "table": table_id,
                }
                st.rerun()
        with col_del:
            if st.button("🗑️ Удалить", key=f"del_{table_id}_{item_id}", width="stretch"):
                st.session_state.edit_action = {
                    "action": "delete",
                    "item_id": item_id,
                    "table": table_id,
                }
                st.rerun()


def render():
    st.title("✏️ Редактирование")

    if not config.DB_ENABLED:
        st.error("❌ PostgreSQL не сконфигурирован.")
        return

    source = st.session_state.get("data_source", config.DEFAULT_DATA_SOURCE)
    if source != "postgres":
        st.warning(
            "⚠️ Редактирование доступно **только при источнике данных PostgreSQL**. "
            f"Сейчас выбран: **{source}**."
        )
        return

    user = _ensure_user_name()
    if user is None:
        return

    # --- Выбор листа ---
    if "edit_sheet" not in st.session_state:
        st.session_state.edit_sheet = "Закупки"

    selected_label = st.segmented_control(
        "📄 Раздел для редактирования:",
        options=list(SHEET_OPTIONS.keys()),
        key="edit_sheet",
        selection_mode="single",
    ) or "Закупки"

    config_for_sheet = SHEET_OPTIONS[selected_label]
    sheet_name = config_for_sheet["sheet"]
    table_id = config_for_sheet["table"]
    form_module = config_for_sheet["form"]

    # --- Активное действие (create / edit / delete) ---
    action = st.session_state.get("edit_action")
    if action:
        # Проверка, что действие относится к текущей таблице
        if action.get("table") and action["table"] != table_id:
            # Таблица сменилась — сбрасываем действие
            st.session_state.pop("edit_action", None)
            st.rerun()

        if action["action"] == "create":
            form_module.render_create_form(user)
        elif action["action"] == "edit":
            form_module.render_edit_form(action["item_id"], user)
        elif action["action"] == "delete":
            form_module.render_delete_confirm(action["item_id"], user)
        return

    # --- Кнопки: Добавить + Обновить ---
    col_add, col_refresh, col_space = st.columns([2, 1, 2])
    with col_add:
        if st.button("➕ Добавить позицию", width="stretch", type="primary", key="add_btn"):
            st.session_state.edit_action = {
                "action": "create",
                "item_id": None,
                "table": table_id,
            }
            st.rerun()
    with col_refresh:
        if st.button("🔄 Обновить", width="stretch",
                     help="Перечитать данные из PostgreSQL (сброс кеша)"):
            fetch_df.clear()
            st.toast("Кэш сброшен! Данные перечитаны.", icon="🎉")
            st.rerun()

    st.divider()

    # --- Загрузка ---
    try:
        with st.spinner(f"Загрузка «{sheet_name}» из PostgreSQL..."):
            df, last_updated = get_sheet_df(sheet_name, source="postgres")
    except Exception as e:
        st.error(f"Ошибка загрузки: {e}")
        return

    if df.empty:
        st.info(f"В таблице «{sheet_name}» пока нет позиций.")
        return

    st.caption(f"🕒 Данные: **{last_updated}**")

    if table_id == "plastic_settings":
        # Справочник: без поиска и пагинации
        page_df = df
        st.caption(f"Всего записей: **{len(df)}**")
    else:
        page_df = _render_search_panel(df)
        if page_df.empty:
            st.warning("Ничего не найдено.")
            return

    for idx, (_, row) in enumerate(page_df.iterrows()):
        _render_item_card(row, idx, table_id)