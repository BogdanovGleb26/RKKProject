"""
Страница «Администрирование».

Доступна только для роли admin.

Разделы:
- Импорт из Excel.
- Управление пользователями.
"""

import time

import streamlit as st

import config
from auth import (
    list_users,
    create_user,
    change_password,
    set_active,
    update_role,
    get_user_by_id,
)


def _render_import_section():
    """Импорт из Excel → PostgreSQL."""
    from import_excel import get_excel_preview, run_full_import

    st.subheader("📥 Импорт данных из Excel")
    st.write(
        "Импорт **заменит все данные** в PostgreSQL (TRUNCATE + INSERT)."
    )

    source = st.session_state.get("data_source", config.DEFAULT_DATA_SOURCE)
    source_label = "Локальный ПК" if source == "local" else "Яндекс.Диск"
    st.write(f"Источник данных: **{source_label}**")

    # --- Шаг 1. Проверка ---
    if st.button("🔍 Проверить текущее состояние", width="stretch", key="admin_check"):
        with st.spinner("Читаю Excel и считаю строки в БД..."):
            try:
                preview = get_excel_preview(source)
                st.session_state.import_preview = preview
            except Exception as e:
                st.error(f"Ошибка: {e}")
                st.session_state.pop("import_preview", None)

    preview = st.session_state.get("import_preview")
    if preview is not None and preview.source == source:
        st.divider()
        st.markdown("#### 📊 Данные перед импортом")

        table_labels = {
            "procurement": "Закупки",
            "os_main": "ОС Главная",
            "plastic_spools": "Пластик",
            "plastic_settings": "Настройки пластика",
        }

        rows = []
        for table in ("procurement", "os_main", "plastic_spools", "plastic_settings"):
            db_cnt = preview.db_counts.get(table, 0)
            ex_cnt = preview.excel_counts.get(table, 0)
            if ex_cnt == -1:
                ex_str = "❌ Ошибка чтения"
                delta = "—"
            else:
                ex_str = f"{ex_cnt}"
                delta = f"{ex_cnt - db_cnt:+d}" if db_cnt else f"+{ex_cnt}"
            rows.append({
                "Таблица": table_labels[table],
                "В БД сейчас": db_cnt,
                "В Excel": ex_str,
                "Изменение": delta,
            })

        st.dataframe(rows, width="stretch", hide_index=True)

        total_db = sum(preview.db_counts.values())
        total_ex = sum(c for c in preview.excel_counts.values() if c >= 0)

        if total_db > 0:
            st.warning(
                f"⚠️ **В БД уже есть данные** ({total_db} строк). "
                f"При импорте они будут **удалены** и заменены данными из Excel "
                f"({total_ex} строк)."
            )
        else:
            st.info(f"ℹ️ БД пуста. Будет вставлено {total_ex} строк.")

        # --- Шаг 2. Подтверждение и импорт ---
        st.divider()
        st.markdown("#### ⚠️ Подтверждение импорта")

        if total_db > 0:
            confirm = st.checkbox(
                "Я понимаю, что все текущие данные в БД будут удалены "
                "и заменены данными из Excel.",
                key="admin_import_confirm",
            )
        else:
            confirm = True

        if st.button(
            "🚀 Импортировать всё",
            type="primary",
            width="stretch",
            disabled=not confirm,
            key="admin_import_run",
        ):
            with st.spinner("Импортирую данные в PostgreSQL..."):
                try:
                    results = run_full_import(source)
                    st.session_state.import_results = results
                    st.session_state.pop("import_preview", None)
                except Exception as e:
                    st.error(f"Ошибка импорта: {e}")

    # --- Шаг 3. Результаты ---
    results = st.session_state.get("import_results")
    if results:
        st.divider()
        st.markdown("#### ✅ Результаты импорта")

        for r in results:
            table_label = {
                "procurement": "Закупки",
                "os_main": "ОС Главная",
                "plastic_spools": "Пластик",
                "plastic_settings": "Настройки пластика",
            }.get(r.table, r.table)

            skipped_part = f" (пропущено: {r.rows_skipped})" if r.rows_skipped else ""
            with st.expander(
                f"{table_label}: {r.rows_inserted} / {r.rows_in_excel} строк"
                + skipped_part
                + (f" (ошибок: {r.rows_with_errors})" if r.rows_with_errors else ""),
                expanded=(r.rows_with_errors > 0),
            ):
                st.write(f"**В Excel:** {r.rows_in_excel}")
                st.write(f"**Вставлено в БД:** {r.rows_inserted}")
                if r.rows_skipped:
                    st.info(
                        f"**Пропущено:** {r.rows_skipped} строк(и) — "
                        f"пустые заготовки без значения в колонке «Код»."
                    )
                if r.rows_with_errors:
                    st.warning(f"Строк с ошибками: {r.rows_with_errors} (значения → NULL)")
                if r.missing_columns:
                    st.info(
                        f"Колонки, которых не было в Excel: "
                        f"{', '.join(r.missing_columns)}"
                    )

        if st.button("Очистить результаты", width="stretch", key="admin_clear_results"):
            st.session_state.pop("import_results", None)
            st.rerun()


# =============================================================================
# Управление пользователями
# =============================================================================

ROLE_LABELS = {
    "admin": "Администратор",
    "editor": "Редактор",
    "viewer": "Наблюдатель",
}


def _render_users_section():
    """Управление пользователями."""
    st.subheader("👥 Управление пользователями")
    st.caption(
        "Создание пользователей, смена ролей и паролей, блокировка. "
        "Доступно только администратору."
    )

    current_user = st.session_state.current_user
    current_user_id = current_user["id"]

    # --- Активная форма (create / change_password / edit_role) ---
    action = st.session_state.get("admin_user_action")
    if action:
        if action["action"] == "create":
            _render_create_user_form()
        elif action["action"] == "change_password":
            _render_change_password_form(action["user_id"], current_user_id)
        elif action["action"] == "edit_role":
            _render_edit_role_form(action["user_id"], current_user_id)
        return

    # --- Кнопка «Создать» ---
    if st.button("➕ Создать пользователя", type="primary", width="stretch", key="admin_create_user_btn"):
        st.session_state.admin_user_action = {"action": "create"}
        st.rerun()

    st.divider()

    # --- Список пользователей ---
    users = list_users()
    if not users:
        st.info("Нет пользователей.")
        return

    for u in users:
        _render_user_card(u, current_user_id)


def _render_user_card(user: dict, current_user_id: int):
    """Карточка одного пользователя."""
    is_self = user["id"] == current_user_id
    role_label = ROLE_LABELS.get(user["role"], user["role"])
    status = "🟢 Активен" if user["is_active"] else "🔴 Заблокирован"
    self_mark = " (это вы)" if is_self else ""

    with st.container(border=True):
        st.markdown(
            f"**{user['username']}**{self_mark} · "
            f"{role_label} · {status}"
        )

        col_pwd, col_role, col_active, col_space = st.columns([1, 1, 1, 1])

        with col_pwd:
            if st.button(
                "🔑 Сменить пароль",
                key=f"admin_pwd_{user['id']}",
                width="stretch",
            ):
                st.session_state.admin_user_action = {
                    "action": "change_password",
                    "user_id": user["id"],
                }
                st.rerun()

        with col_role:
            if not is_self:  # себе роль менять нельзя
                if st.button(
                    "✏️ Сменить роль",
                    key=f"admin_role_{user['id']}",
                    width="stretch",
                ):
                    st.session_state.admin_user_action = {
                        "action": "edit_role",
                        "user_id": user["id"],
                    }
                    st.rerun()

        with col_active:
            if not is_self:  # себя блокировать нельзя
                if user["is_active"]:
                    if st.button(
                        "🚫 Блокировать",
                        key=f"admin_block_{user['id']}",
                        width="stretch",
                    ):
                        set_active(user["id"], False)
                        st.success(f"Пользователь «{user['username']}» заблокирован.")
                        time.sleep(1)
                        st.rerun()
                else:
                    if st.button(
                        "✅ Разблокировать",
                        key=f"admin_unblock_{user['id']}",
                        width="stretch",
                    ):
                        set_active(user["id"], True)
                        st.success(f"Пользователь «{user['username']}» разблокирован.")
                        time.sleep(1)
                        st.rerun()


def _render_create_user_form():
    """Форма создания пользователя."""
    st.subheader("➕ Новый пользователь")

    with st.form("admin_create_user_form"):
        username = st.text_input("Логин", key="new_user_username")
        password = st.text_input(
            "Пароль", type="password", key="new_user_password",
            help="Минимум 4 символа. Пользователь сможет сменить его позже.",
        )
        password2 = st.text_input(
            "Повторите пароль", type="password", key="new_user_password2",
        )
        role = st.selectbox(
            "Роль",
            options=["viewer", "editor", "admin"],
            format_func=lambda r: ROLE_LABELS.get(r, r),
            key="new_user_role",
        )

        st.divider()
        col_save, col_cancel = st.columns(2)
        with col_save:
            submitted = st.form_submit_button("💾 Создать", type="primary", width="stretch")
        with col_cancel:
            cancelled = st.form_submit_button("✖ Отмена", width="stretch")

    if cancelled:
        st.session_state.pop("admin_user_action", None)
        st.rerun()

    if submitted:
        if not username.strip():
            st.error("Логин не может быть пустым.")
            return
        if len(password) < 4:
            st.error("Пароль слишком короткий (минимум 4 символа).")
            return
        if password != password2:
            st.error("Пароли не совпадают.")
            return
        try:
            new_id = create_user(username.strip(), password, role)
            st.success(f"✅ Пользователь «{username}» создан (id={new_id}).")
            st.session_state.pop("admin_user_action", None)
            time.sleep(1.5)
            st.rerun()
        except ValueError as e:
            st.error(str(e))
        except Exception as e:
            st.error(f"Ошибка создания: {e}")


def _render_change_password_form(user_id: int, current_user_id: int):
    """Форма смены пароля."""
    user = get_user_by_id(user_id)
    if user is None:
        st.error("Пользователь не найден.")
        if st.button("← Назад"):
            st.session_state.pop("admin_user_action", None)
            st.rerun()
        return

    is_self = user_id == current_user_id
    self_note = " (себе)" if is_self else ""

    st.subheader(f"🔑 Смена пароля: {user['username']}{self_note}")

    with st.form("admin_change_password_form"):
        new_pwd = st.text_input(
            "Новый пароль", type="password", key="chpwd_new",
            help="Минимум 4 символа.",
        )
        new_pwd2 = st.text_input(
            "Повторите пароль", type="password", key="chpwd_new2",
        )

        st.divider()
        col_save, col_cancel = st.columns(2)
        with col_save:
            submitted = st.form_submit_button("💾 Сохранить", type="primary", width="stretch")
        with col_cancel:
            cancelled = st.form_submit_button("✖ Отмена", width="stretch")

    if cancelled:
        st.session_state.pop("admin_user_action", None)
        st.rerun()

    if submitted:
        if len(new_pwd) < 4:
            st.error("Пароль слишком короткий (минимум 4 символа).")
            return
        if new_pwd != new_pwd2:
            st.error("Пароли не совпадают.")
            return
        try:
            if change_password(user_id, new_pwd):
                st.success("✅ Пароль изменён.")
                st.session_state.pop("admin_user_action", None)
                time.sleep(1.5)
                st.rerun()
            else:
                st.error("Не удалось изменить пароль.")
        except ValueError as e:
            st.error(str(e))
        except Exception as e:
            st.error(f"Ошибка: {e}")


def _render_edit_role_form(user_id: int, current_user_id: int):
    """Форма смены роли."""
    user = get_user_by_id(user_id)
    if user is None:
        st.error("Пользователь не найден.")
        if st.button("← Назад"):
            st.session_state.pop("admin_user_action", None)
            st.rerun()
        return

    if user_id == current_user_id:
        st.error("Нельзя менять роль самому себе.")
        if st.button("← Назад"):
            st.session_state.pop("admin_user_action", None)
            st.rerun()
        return

    st.subheader(f"✏️ Смена роли: {user['username']}")
    st.write(f"Текущая роль: **{ROLE_LABELS.get(user['role'], user['role'])}**")

    with st.form("admin_edit_role_form"):
        new_role = st.selectbox(
            "Новая роль",
            options=["viewer", "editor", "admin"],
            index=["viewer", "editor", "admin"].index(user["role"]),
            format_func=lambda r: ROLE_LABELS.get(r, r),
        )

        st.divider()
        col_save, col_cancel = st.columns(2)
        with col_save:
            submitted = st.form_submit_button("💾 Сохранить", type="primary", width="stretch")
        with col_cancel:
            cancelled = st.form_submit_button("✖ Отмена", width="stretch")

    if cancelled:
        st.session_state.pop("admin_user_action", None)
        st.rerun()

    if submitted:
        if new_role == user["role"]:
            st.info("Роль не изменилась.")
            return
        try:
            if update_role(user_id, new_role):
                st.success(f"✅ Роль изменена на «{ROLE_LABELS.get(new_role, new_role)}».")
                st.session_state.pop("admin_user_action", None)
                time.sleep(1.5)
                st.rerun()
            else:
                st.error("Не удалось изменить роль.")
        except ValueError as e:
            st.error(str(e))
        except Exception as e:
            st.error(f"Ошибка: {e}")


# =============================================================================
# Главный render
# =============================================================================

def render():
    st.title("⚙️ Администрирование")

    if not config.DB_ENABLED:
        st.error(
            "❌ PostgreSQL не сконфигурирован. "
            "Проверьте `.env` (DB_HOST, DB_NAME, DB_USER, DB_PASSWORD)."
        )
        return

    # Дополнительная проверка на всякий случай
    current_user = st.session_state.get("current_user")
    if not current_user or current_user.get("role") != "admin":
        st.error("⛔ Недостаточно прав для доступа к этому разделу.")
        return

    tab_import, tab_users = st.tabs(["📥 Импорт из Excel", "👥 Пользователи"])

    with tab_import:
        _render_import_section()

    with tab_users:
        _render_users_section()