import re
import pandas as pd
import streamlit as st
import plotly.express as px
from data_loader import load_data


def parse_number(val) -> float:
    """Преобразует строку/число из Excel в float."""
    if pd.isna(val) or val == "":
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    # Удаляем пробелы, символы валют и заменяем запятую на точку
    clean_str = re.sub(r"[^\d.,-]", "", str(val)).replace(",", ".")
    try:
        return float(clean_str) if clean_str else 0.0
    except ValueError:
        return 0.0


# =============================================================================
# 1. АНАЛИТИКА: ЗАКУПКИ
# =============================================================================
def render_procurement_analytics(df: pd.DataFrame):
    """Аналитика для раздела 'Закупки' (3 KPI + 2 Графика)."""
    total_positions = len(df)
    if total_positions == 0:
        st.info("Раздел «Закупки» не содержит данных для анализа.")
        return

    status_col = "Статус" if "Статус" in df.columns else None
    curator_col = "Куратор МТО" if "Куратор МТО" in df.columns else None
    storage_col = "Место хранения" if "Место хранения" in df.columns else None

    # --- 3 KPI ---
    received_count = (
        df[df[status_col].astype(str).str.strip().str.lower() == "получено со склада"].shape[0]
        if status_col else 0
    )
    delivery_success_rate = (received_count / total_positions * 100) if total_positions > 0 else 0.0

    TOTAL_CAPACITY = 300
    occupied_cells = (
        df[df[storage_col].astype(str).str.strip() != ""][storage_col].nunique()
        if storage_col else 0
    )
    occupancy_rate = min((occupied_cells / TOTAL_CAPACITY * 100), 100.0)

    if curator_col:
        valid_curators = df[df[curator_col].astype(str).str.strip() != ""][curator_col].nunique()
        avg_orders_per_curator = (total_positions / valid_curators) if valid_curators > 0 else 0.0
    else:
        avg_orders_per_curator = 0.0

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("🎯 Успешность закупок", f"{delivery_success_rate:.1f}%")
    with col2:
        st.metric("📦 Занято ячеек", f"{occupied_cells} шт.", f"{occupancy_rate:.1f}% от емкости")
    with col3:
        st.metric("👤 Заявок на куратора", f"{avg_orders_per_curator:.1f}")

    st.divider()

    # --- 2 Графика ---
    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:
        st.subheader("👥 Нагрузка кураторов МТО")
        if curator_col and status_col:
            df_curator = df[df[curator_col].astype(str).str.strip() != ""].copy()
            if not df_curator.empty:
                curator_data = df_curator.groupby([curator_col, status_col]).size().reset_index(name="Количество")
                fig1 = px.bar(
                    curator_data,
                    x=curator_col,
                    y="Количество",
                    color=status_col,
                    barmode="stack",
                    color_discrete_sequence=px.colors.qualitative.Set2
                )
                fig1.update_layout(xaxis_title=None, yaxis_title="Заявки (шт.)", height=380, margin=dict(l=10, r=10, t=20, b=10))
                st.plotly_chart(fig1, use_container_width=True)
            else:
                st.info("Нет данных по кураторам.")

    with chart_col2:
        st.subheader("🔄 Воронка статусов поставок")
        if status_col:
            status_counts = df[status_col].replace("", "Не указан").value_counts().reset_index()
            status_counts.columns = ["Статус", "Количество"]
            fig2 = px.pie(
                status_counts,
                names="Статус",
                values="Количество",
                hole=0.4,
                color_discrete_sequence=px.colors.qualitative.Safe
            )
            fig2.update_layout(height=380, margin=dict(l=10, r=10, t=20, b=10))
            st.plotly_chart(fig2, use_container_width=True)


# =============================================================================
# 2. АНАЛИТИКА: ОС ГЛАВНАЯ
# =============================================================================
def render_os_analytics(df: pd.DataFrame):
    """Аналитика для раздела 'ОС Главная' (3 KPI + 2 Графика)."""
    total_assets = len(df)
    if total_assets == 0:
        st.info("Раздел «ОС Главная» не содержит данных для анализа.")
        return

    status_col = "Статус" if "Статус" in df.columns else None
    storage_col = "Место хранения" if "Место хранения" in df.columns else None
    project_col = "Проект" if "Проект" in df.columns else None
    dept_col = "Отдел МТО" if "Отдел МТО" in df.columns else None
    sum_col = "Сумма финальная" if "Сумма финальная" in df.columns else ("Сумма" if "Сумма" in df.columns else None)
    stock_col = "Остаток" if "Остаток" in df.columns else None

    # --- 3 KPI ---
    if status_col:
        in_use_count = df[df[status_col].astype(str).str.strip().str.lower() == "в работе"].shape[0]
    else:
        in_use_count = 0
    deployment_rate = (in_use_count / total_assets * 100) if total_assets > 0 else 0.0

    if status_col:
        stock_df = df[df[status_col].astype(str).str.strip().str.lower() == "на складе"]
        if stock_col:
            ready_stock_val = stock_df[stock_col].apply(parse_number).sum()
        else:
            ready_stock_val = len(stock_df)
    else:
        ready_stock_val = 0

    if storage_col:
        unmapped_count = df[df[storage_col].astype(str).str.strip() == ""].shape[0]
    else:
        unmapped_count = total_assets
    unmapped_share = (unmapped_count / total_assets * 100) if total_assets > 0 else 0.0

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(
            label="⚙️ Введено в эксплуатацию",
            value=f"{deployment_rate:.1f}%",
            help="Доля ОС в статусе «В работе» от общего числа"
        )
    with col2:
        st.metric(
            label="📦 Готово к выдаче (На складе)",
            value=f"{ready_stock_val:,.0f}".replace(",", " ") + (" шт." if not stock_col else " ед."),
            help="Суммарный остаток/количество позиций в статусе «На складе»"
        )
    with col3:
        st.metric(
            label="❓ Незакрепленные ОС",
            value=f"{unmapped_share:.1f}%",
            help=f"Позиций без указанного места хранения ({unmapped_count} из {total_assets} шт.)"
        )

    st.divider()

    # --- 2 Графика ---
    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:
        st.subheader("🚀 Размещение ОС по Проектам")
        if project_col:
            df_proj = df.copy()
            df_proj[project_col] = df_proj[project_col].replace("", "Без проекта")
            proj_data = df_proj.groupby(project_col).size().reset_index(name="Количество")
            proj_data = proj_data.sort_values(by="Количество", ascending=True)

            fig_proj = px.bar(
                proj_data,
                x="Количество",
                y=project_col,
                orientation="h",
                text="Количество",
                color_discrete_sequence=["#3730a3"]
            )
            fig_proj.update_layout(
                xaxis_title="Количество ОС (шт.)",
                yaxis_title=None,
                height=380,
                margin=dict(l=10, r=10, t=20, b=10)
            )
            st.plotly_chart(fig_proj, use_container_width=True)
        else:
            st.info("Нет колонки «Проект».")

    with chart_col2:
        st.subheader("💰 Топ-5 затратных Отделов МТО")
        if dept_col and sum_col:
            df_dept = df.copy()
            df_dept["Сумма_число"] = df_dept[sum_col].apply(parse_number)
            df_dept[dept_col] = df_dept[dept_col].replace("", "Не указан")
            
            top_depts = df_dept.groupby(dept_col)["Сумма_число"].sum().reset_index()
            top_depts = top_depts.sort_values(by="Сумма_число", ascending=False).head(5)
            top_depts = top_depts.sort_values(by="Сумма_число", ascending=True)

            fig_top = px.bar(
                top_depts,
                x="Сумма_число",
                y=dept_col,
                orientation="h",
                text_auto=".2s",
                color_discrete_sequence=["#059669"]
            )
            fig_top.update_layout(
                xaxis_title="Стоимость ОС (₽)",
                yaxis_title=None,
                height=380,
                margin=dict(l=10, r=10, t=20, b=10)
            )
            st.plotly_chart(fig_top, use_container_width=True)
        else:
            st.info("Отсутствуют колонки «Отдел МТО» или «Сумма».")


# =============================================================================
# 3. АНАЛИТИКА: ПЛАСТИК
# =============================================================================
def render_plastic_analytics(df: pd.DataFrame):
    """Аналитика для раздела 'Пластик' (3 KPI + 2 Графика)."""
    total_spools = len(df)
    if total_spools == 0:
        st.info("Раздел «Пластик» не содержит данных для анализа.")
        return

    # Поиск колонок с учетом возможных названий
    weight_col = next((c for c in df.columns if "вес" in c.lower() or "масса" in c.lower()), None)
    type_col = next((c for c in df.columns if "тип" in c.lower() or "материал" in c.lower()), None)
    brand_col = next((c for c in df.columns if "производ" in c.lower() or "бренд" in c.lower() or "назван" in c.lower()), None)
    storage_col = next((c for c in df.columns if "место" in c.lower() or "ячейка" in c.lower()), None)

    # --- 3 KPI ---
    # KPI 1: Общий остаток филамента в кг
    if weight_col:
        total_weight_g = df[weight_col].apply(parse_number).sum()
        total_weight_kg = total_weight_g / 1000.0
    else:
        total_weight_kg = 0.0

    # KPI 2: Количество "критических" катушек (Вес < 200 г)
    if weight_col:
        weights = df[weight_col].apply(parse_number)
        low_stock_count = ((weights > 0) & (weights < 200)).sum()
    else:
        low_stock_count = 0

    # KPI 3: Доля неинвентаризированного пластика (без места хранения)
    if storage_col:
        unlocated_count = df[df[storage_col].astype(str).str.strip() == ""].shape[0]
    else:
        unlocated_count = total_spools
    unlocated_share = (unlocated_count / total_spools * 100) if total_spools > 0 else 0.0

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(
            label="🧵 Общий вес пластика",
            value=f"{total_weight_kg:.2f} кг",
            help="Суммарный остаток всех катушек филамента"
        )
    with col2:
        st.metric(
            label="⚠️ Остаток < 200г",
            value=f"{low_stock_count} катушек",
            help="Количество катушек с остатком менее 200 грамм"
        )
    with col3:
        st.metric(
            label="❓ Без места хранения",
            value=f"{unlocated_share:.1f}%",
            help=f"Катушек без указания ячейки ({unlocated_count} из {total_spools} шт.)"
        )

    st.divider()

    # --- 2 Графика ---
    chart_col1, chart_col2 = st.columns(2)

    # График 1: Запасы по типам пластика (PLA, PETG, ABS и т.д.)
    with chart_col1:
        st.subheader("🧪 Запасы по Типам пластика")
        if type_col and weight_col:
            df_type = df.copy()
            df_type["Вес_кг"] = df_type[weight_col].apply(parse_number) / 1000.0
            df_type[type_col] = df_type[type_col].replace("", "Не указан").astype(str).str.upper()

            type_summary = df_type.groupby(type_col)["Вес_кг"].sum().reset_index()
            type_summary = type_summary.sort_values(by="Вес_кг", ascending=False)

            fig_type = px.bar(
                type_summary,
                x=type_col,
                y="Вес_кг",
                text_auto=".1f",
                color=type_col,
                color_discrete_sequence=px.colors.qualitative.Bold
            )
            fig_type.update_layout(
                showlegend=False,
                xaxis_title=None,
                yaxis_title="Запас (кг)",
                height=380,
                margin=dict(l=10, r=10, t=20, b=10)
            )
            st.plotly_chart(fig_type, use_container_width=True)
        else:
            st.info("Не найдены колонки «Тип» или «Вес».")

    # График 2: Запасы по Производителям / Брендам
    with chart_col2:
        st.subheader("🏷️ Катушки по Брендам")
        if brand_col:
            df_brand = df.copy()
            df_brand[brand_col] = df_brand[brand_col].replace("", "Не указан").astype(str)

            brand_summary = df_brand.groupby(brand_col).size().reset_index(name="Катушек")
            brand_summary = brand_summary.sort_values(by="Катушек", ascending=False)

            fig_brand = px.bar(
                brand_summary,
                x=brand_col,
                y="Катушек",
                text="Катушек",
                color_discrete_sequence=["#2563eb"]
            )
            fig_brand.update_layout(
                xaxis_title=None,
                yaxis_title="Катушек (шт.)",
                height=380,
                margin=dict(l=10, r=10, t=20, b=10)
            )
            st.plotly_chart(fig_brand, use_container_width=True)
        else:
            st.info("Не найдена колонка «Производитель / Бренд».")


# =============================================================================
# 4. ОСНОВНОЙ РЕНДЕР МОДУЛЯ
# =============================================================================
def render():
    st.title("📊 Отчеты")

    SHEET_OPTIONS = ["Закупки", "ОС Главная", "Пластик"]
    selected_sheet = st.radio(
        "📄 Раздел для анализа:",
        options=SHEET_OPTIONS,
        index=0,
        horizontal=True,
    )

    try:
        with st.spinner(f"Загрузка данных раздела «{selected_sheet}»..."):
            df, last_updated = load_data(selected_sheet)
    except Exception as e:
        st.error(f"Ошибка при загрузке базы данных: {e}")
        st.stop()

    st.caption(f"🕒 Данные обновлены: **{last_updated}** (МСК)")

    if df.empty:
        st.warning(f"Раздел «{selected_sheet}» пуст.")
        return

    # Роутинг страниц аналитики
    if selected_sheet == "Закупки":
        render_procurement_analytics(df)
    elif selected_sheet == "ОС Главная":
        render_os_analytics(df)
    elif selected_sheet == "Пластик":
        render_plastic_analytics(df)