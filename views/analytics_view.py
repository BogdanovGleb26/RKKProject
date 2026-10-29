import re
import pandas as pd
import streamlit as st
import plotly.express as px
from data_loader import load_data
import config
from db import get_sheet_df


# =============================================================================
# КОНСТАНТЫ И ХЕЛПЕРЫ
# =============================================================================

# Нормализованные статусы (сравниваем в lowercase, strip)
STATUS_RECEIVED = "получено со склада"
STATUS_IN_USE = "в работе"
STATUS_IN_STOCK = "на складе"

# Порядок статусов для графиков (по возрастанию «продвинутости»)
STATUS_ORDER_PROCUREMENT = [
    "создано",
    "согласовано",
    "заказано",
    "доставлено",
    "получено со склада",
    "отменено",
    "отказ",
]

LOW_STOCK_THRESHOLD_G = 200
TOTAL_CAPACITY = 300


def _normalize_status(value) -> str:
    """Единая нормализация статуса для сравнений."""
    if value is None:
        return ""
    return str(value).strip().lower()


def parse_number(val) -> float:
    """Совместимость: возвращает float, битые значения → 0.0."""
    return _parse_number_checked(val)[0]


def _parse_number_checked(val) -> tuple[float, bool]:
    """Возвращает (значение, ok). ok=False, если значение было непустым, но не распарсилось."""
    if pd.isna(val) or val == "":
        return 0.0, True
    if isinstance(val, (int, float)):
        return float(val), True

    raw = str(val).strip()
    if not raw:
        return 0.0, True

    clean_str = re.sub(r"[^\d.,-]", "", raw)

    # Определяем формат: если есть и точка, и запятая — какая правее, та и десятичная
    if "," in clean_str and "." in clean_str:
        if clean_str.rfind(",") > clean_str.rfind("."):
            # "1.234,56" → европейский
            clean_str = clean_str.replace(".", "").replace(",", ".")
        else:
            # "1,234.56" → US
            clean_str = clean_str.replace(",", "")
    else:
        clean_str = clean_str.replace(",", ".")

    try:
        return float(clean_str), True
    except ValueError:
        return 0.0, False


def parse_numeric_column(series: pd.Series) -> tuple[pd.Series, int]:
    """Применяет _parse_number_checked к колонке. Возвращает (числа, кол-во битых)."""
    parsed = []
    bad = 0
    for v in series:
        value, ok = _parse_number_checked(v)
        parsed.append(value)
        if not ok:
            bad += 1
    return pd.Series(parsed, index=series.index), bad


def _render_metric_row(metrics: list[dict]):
    """Рендерит ряд из 3 KPI. Каждый элемент: {label, value, help?}."""
    cols = st.columns(len(metrics))
    for col, m in zip(cols, metrics):
        with col:
            st.metric(label=m["label"], value=m["value"], help=m.get("help"))


def _share_blank(df: pd.DataFrame, col: str | None) -> tuple[int, float]:
    """Возвращает (кол-во пустых, доля пустых в %)."""
    total = len(df)
    if not col or total == 0:
        return (total if not col else 0), (100.0 if not col and total else 0.0)
    blank = df[df[col].astype(str).str.strip() == ""].shape[0]
    share = (blank / total * 100) if total else 0.0
    return blank, share


def _warn_bad_numbers(bad_count: int, column_label: str):
    """Показывает предупреждение, если были битые числа."""
    if bad_count > 0:
        st.caption(
            f"⚠️ {bad_count} значений в колонке «{column_label}» "
            f"не удалось распарсить как число — они не учтены."
        )


# =============================================================================
# 1. АНАЛИТИКА: ЗАКУПКИ
# =============================================================================
def render_procurement_analytics(df: pd.DataFrame):
    total_positions = len(df)
    if total_positions == 0:
        st.info("Раздел «Закупки» не содержит данных для анализа.")
        return

    status_col = "Статус" if "Статус" in df.columns else None
    curator_col = "Куратор МТО" if "Куратор МТО" in df.columns else None
    storage_col = "Место хранения" if "Место хранения" in df.columns else None

    # --- 3 KPI ---
    if status_col:
        received_count = df[df[status_col].apply(_normalize_status) == STATUS_RECEIVED].shape[0]
    else:
        received_count = 0
    delivery_success_rate = (received_count / total_positions * 100) if total_positions > 0 else 0.0

    occupied_cells = (
        df.loc[df[storage_col].astype(str).str.strip() != "", storage_col].nunique()
        if storage_col else 0
    )
    occupancy_rate = min((occupied_cells / TOTAL_CAPACITY * 100), 100.0)

    if curator_col:
        valid_curators = df[df[curator_col].astype(str).str.strip() != ""][curator_col].nunique()
        avg_orders_per_curator = (total_positions / valid_curators) if valid_curators > 0 else 0.0
    else:
        avg_orders_per_curator = 0.0

    _render_metric_row([
        {"label": "🎯 Успешность закупок", "value": f"{delivery_success_rate:.1f}%",
         "help": f"Доля позиций со статусом «{STATUS_RECEIVED.title()}»"},
        {"label": "📦 Занято ячеек", "value": f"{occupied_cells} шт.",
         "help": f"{occupancy_rate:.1f}% от ёмкости ({TOTAL_CAPACITY} ячеек)"},
        {"label": "👤 Заявок на куратора", "value": f"{avg_orders_per_curator:.1f}"},
    ])

    st.divider()

    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:
        st.subheader("👥 Нагрузка кураторов МТО")
        if curator_col and status_col:
            df_curator = df[df[curator_col].astype(str).str.strip() != ""].copy()
            if not df_curator.empty:
                df_curator["_status_norm"] = df_curator[status_col].apply(_normalize_status)
                curator_data = (
                    df_curator.groupby([curator_col, "_status_norm"])
                    .size()
                    .reset_index(name="Количество")
                )
                fig1 = px.bar(
                    curator_data,
                    x=curator_col,
                    y="Количество",
                    color="_status_norm",
                    barmode="stack",
                    color_discrete_sequence=px.colors.qualitative.Set2,
                    category_orders={"_status_norm": STATUS_ORDER_PROCUREMENT},
                )
                fig1.update_layout(
                    xaxis_title=None,
                    yaxis_title="Заявки (шт.)",
                    height=380,
                    margin=dict(l=10, r=10, t=20, b=10),
                    legend_title_text="Статус",
                )
                st.plotly_chart(fig1, width="stretch")
            else:
                st.info("Нет данных по кураторам.")
        else:
            st.info("Нет колонок «Куратор МТО» или «Статус».")

    with chart_col2:
        st.subheader("🔄 Распределение по статусам")
        if status_col:
            statuses = df[status_col].apply(lambda v: _normalize_status(v) or "не указан")
            status_counts = statuses.value_counts().reset_index()
            status_counts.columns = ["Статус", "Количество"]
            fig2 = px.pie(
                status_counts,
                names="Статус",
                values="Количество",
                hole=0.4,
                color_discrete_sequence=px.colors.qualitative.Safe,
                category_orders={"Статус": STATUS_ORDER_PROCUREMENT},
            )
            fig2.update_layout(height=380, margin=dict(l=10, r=10, t=20, b=10))
            st.plotly_chart(fig2, width="stretch")
        else:
            st.info("Нет колонки «Статус».")


# =============================================================================
# 2. АНАЛИТИКА: ОС ГЛАВНАЯ
# =============================================================================
def render_os_analytics(df: pd.DataFrame):
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
        in_use_count = df[df[status_col].apply(_normalize_status) == STATUS_IN_USE].shape[0]
    else:
        in_use_count = 0
    deployment_rate = (in_use_count / total_assets * 100) if total_assets > 0 else 0.0

    if status_col:
        stock_df = df[df[status_col].apply(_normalize_status) == STATUS_IN_STOCK]
        if stock_col:
            stock_vals, bad = parse_numeric_column(stock_df[stock_col])
            ready_stock_val = stock_vals.sum()
        else:
            ready_stock_val = len(stock_df)
            bad = 0
    else:
        ready_stock_val = 0
        bad = 0

    unmapped_count, unmapped_share = _share_blank(df, storage_col)

    _render_metric_row([
        {"label": "⚙️ Введено в эксплуатацию", "value": f"{deployment_rate:.1f}%",
         "help": f"Доля ОС в статусе «{STATUS_IN_USE.title()}» от общего числа"},
        {"label": "📦 Готово к выдаче", "value": f"{ready_stock_val:,.0f}".replace(",", " "),
         "help": f"Позиции в статусе «{STATUS_IN_STOCK.title()}»" + (" (сумма остатков)" if stock_col else " (кол-во позиций)")},
        {"label": "❓ Незакрепленные ОС", "value": f"{unmapped_share:.1f}%",
         "help": f"Позиций без места хранения ({unmapped_count} из {total_assets})"},
    ])
    _warn_bad_numbers(bad, stock_col or "Остаток")

    st.divider()

    chart_col1, chart_col2 = st.columns(2)

    # --- График 1: Топ-10 позиций по стоимости ---
    with chart_col1:
        st.subheader("💰 Топ-10 позиций по стоимости")
        if sum_col:
            df_sum = df.copy()

            # Имя позиции: «Название», иначе «Номенклатура», иначе — код
            def _name_for_chart(row):
                name = str(row.get("Название", "")).strip()
                if not name:
                    name = str(row.get("Номенклатура", "")).strip()
                if not name:
                    code = str(row.get("Код", "")).strip()
                    name = f"Код {code}" if code else "Без названия"
                # Обрезаем для читаемости на графике
                return name if len(name) <= 50 else name[:47] + "..."

            df_sum["_name"] = df_sum.apply(_name_for_chart, axis=1)
            df_sum["_sum"], bad_sums = parse_numeric_column(df_sum[sum_col])
            _warn_bad_numbers(bad_sums, sum_col)

            # Отбрасываем позиции без суммы (0 или пусто)
            df_sum = df_sum[df_sum["_sum"] > 0]

            if df_sum.empty:
                st.info("Нет данных по стоимости — все суммы пустые или не распарсились.")
            else:
                top_items = df_sum.nlargest(10, "_sum").sort_values("_sum", ascending=True)

                fig_top = px.bar(
                    top_items,
                    x="_sum",
                    y="_name",
                    orientation="h",
                    text_auto=".2s",
                    color_discrete_sequence=["#059669"],
                )
                fig_top.update_layout(
                    xaxis_title="Стоимость (₽)",
                    yaxis_title=None,
                    height=380,
                    margin=dict(l=10, r=10, t=20, b=10),
                )
                st.plotly_chart(fig_top, width="stretch")
                st.caption(
                    f"Показано 10 из {len(df_sum)} позиций с указанной стоимостью."
                )
        else:
            st.info("Нет колонки «Сумма финальная» или «Сумма».")

    # --- График 2: Распределение по местам хранения ---
    with chart_col2:
        st.subheader("📍 Топ-10 мест хранения")
        if storage_col:
            df_loc = df.copy()
            df_loc[storage_col] = df_loc[storage_col].astype(str).str.strip()
            df_loc = df_loc[df_loc[storage_col] != ""]

            if df_loc.empty:
                st.info("Нет позиций с указанным местом хранения.")
            else:
                loc_counts = (
                    df_loc.groupby(storage_col)
                    .size()
                    .reset_index(name="Количество")
                )
                total_locations = len(loc_counts)
                top_locs = loc_counts.nlargest(10, "Количество").sort_values(
                    "Количество", ascending=True
                )

                fig_loc = px.bar(
                    top_locs,
                    x="Количество",
                    y=storage_col,
                    orientation="h",
                    text="Количество",
                    color_discrete_sequence=["#3730a3"],
                )
                fig_loc.update_layout(
                    xaxis_title="Позиций (шт.)",
                    yaxis_title=None,
                    height=380,
                    margin=dict(l=10, r=10, t=20, b=10),
                )
                st.plotly_chart(fig_loc, width="stretch")
                st.caption(
                    f"Показано 10 из {total_locations} ячеек. "
                    f"Всего позиций с местом: {int(loc_counts['Количество'].sum())}."
                )
        else:
            st.info("Нет колонки «Место хранения».")


# =============================================================================
# 3. АНАЛИТИКА: ПЛАСТИК
# =============================================================================
def render_plastic_analytics(df: pd.DataFrame):
    total_spools = len(df)
    if total_spools == 0:
        st.info("Раздел «Пластик» не содержит данных для анализа.")
        return

    weight_col = next((c for c in df.columns if "вес" in c.lower() or "масса" in c.lower()), None)
    type_col = next((c for c in df.columns if "тип" in c.lower() or "материал" in c.lower()), None)
    brand_col = next((c for c in df.columns if "производ" in c.lower() or "бренд" in c.lower() or "назван" in c.lower()), None)
    storage_col = next((c for c in df.columns if "место" in c.lower() or "ячейка" in c.lower()), None)

    # --- 3 KPI ---
    if weight_col:
        weights, bad_w = parse_numeric_column(df[weight_col])
        total_weight_kg = weights.sum() / 1000.0
        low_stock_count = ((weights > 0) & (weights < LOW_STOCK_THRESHOLD_G)).sum()
    else:
        total_weight_kg = 0.0
        low_stock_count = 0
        bad_w = 0

    unlocated_count, unlocated_share = _share_blank(df, storage_col)

    _render_metric_row([
        {"label": "🧵 Общий вес пластика", "value": f"{total_weight_kg:.2f} кг",
         "help": "Суммарный остаток всех катушек филамента"},
        {"label": f"⚠️ Остаток < {LOW_STOCK_THRESHOLD_G}г", "value": f"{low_stock_count} катушек",
         "help": f"Катушки с остатком менее {LOW_STOCK_THRESHOLD_G} грамм"},
        {"label": "❓ Без места хранения", "value": f"{unlocated_share:.1f}%",
         "help": f"Катушек без указания ячейки ({unlocated_count} из {total_spools})"},
    ])
    _warn_bad_numbers(bad_w, weight_col or "Вес")

    st.divider()

    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:
        st.subheader("🧪 Запасы по Типам пластика")
        if type_col and weight_col:
            df_type = df.copy()
            df_type["Вес_кг"] = df_type[weight_col].apply(parse_number) / 1000.0
            df_type[type_col] = df_type[type_col].replace("", "Не указан").astype(str).str.upper()

            type_summary = df_type.groupby(type_col)["Вес_кг"].sum().reset_index()
            type_summary = type_summary.sort_values(by="Вес_кг", ascending=False)

            fig_type = px.bar(
                type_summary, x=type_col, y="Вес_кг", text_auto=".1f",
                color=type_col, color_discrete_sequence=px.colors.qualitative.Bold,
            )
            fig_type.update_layout(
                showlegend=False, xaxis_title=None, yaxis_title="Запас (кг)",
                height=380, margin=dict(l=10, r=10, t=20, b=10),
            )
            st.plotly_chart(fig_type, width="stretch")
        else:
            st.info("Не найдены колонки «Тип» или «Вес».")

    with chart_col2:
        st.subheader("🏷️ Катушки по Брендам")
        if brand_col:
            df_brand = df.copy()
            df_brand[brand_col] = df_brand[brand_col].replace("", "Не указан").astype(str)

            brand_summary = df_brand.groupby(brand_col).size().reset_index(name="Катушек")
            brand_summary = brand_summary.sort_values(by="Катушек", ascending=False)

            fig_brand = px.bar(
                brand_summary, x=brand_col, y="Катушек", text="Катушек",
                color_discrete_sequence=["#2563eb"],
            )
            fig_brand.update_layout(
                xaxis_title=None, yaxis_title="Катушек (шт.)",
                height=380, margin=dict(l=10, r=10, t=20, b=10),
            )
            st.plotly_chart(fig_brand, width="stretch")
        else:
            st.info("Не найдена колонка «Производитель / Бренд».")


# =============================================================================
# 4. ОСНОВНОЙ РЕНДЕР
# =============================================================================
def render():
    st.title("📊 Отчеты")

    source = st.session_state.get("data_source", config.DEFAULT_DATA_SOURCE)
    source_label = "Локальный ПК" if source == "local" else "Яндекс.Диск"

    SHEET_OPTIONS = ["Закупки", "ОС Главная", "Пластик"]

    if "selected_sheet_analytics" not in st.session_state:
        st.session_state.selected_sheet_analytics = SHEET_OPTIONS[0]

    selected_sheet = st.segmented_control(
        "📄 Раздел для анализа:",
        options=SHEET_OPTIONS,
        default=st.session_state.selected_sheet_analytics,
        key="selected_sheet_analytics",
        selection_mode="single",
    ) or SHEET_OPTIONS[0]

    try:
        with st.spinner(f"Загрузка данных раздела «{selected_sheet}» из {source_label}..."):
            df, last_updated = get_sheet_df(selected_sheet, source=source)
    except Exception as e:
        st.error(f"Ошибка при загрузке базы данных: {e}")
        st.stop()

    st.caption(f"🕒 Данные обновлены: **{last_updated}**")

    if df.empty:
        st.warning(f"Раздел «{selected_sheet}» пуст.")
        return

    if selected_sheet == "Закупки":
        render_procurement_analytics(df)
    elif selected_sheet == "ОС Главная":
        render_os_analytics(df)
    elif selected_sheet == "Пластик":
        render_plastic_analytics(df)