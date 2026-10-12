import os
import threading
import pandas as pd
from pydantic import BaseModel, Field


class Tools:
    class Valves(BaseModel):
        excel_path: str = Field(
            default=r"C:\Users\user\Desktop\inventarization_data\test_reaL_data.xlsx",
            description="Путь к локальному Excel-файлу с учётными данными",
        )
        max_results: int = Field(
            default=20,
            description="Максимум строк в ответе, чтобы не перегружать контекст модели",
        )
        max_cell_len: int = Field(
            default=200,
            description="Обрезка слишком длинных ячеек (символов)",
        )
        default_sheets: str = Field(
            default="Закупки,ОС Главная,Пластик",
            description="Список листов по умолчанию через запятую, если sheet_name='Все'",
        )

    # ---------- кэш ----------
    _cache_lock = threading.Lock()
    _cache = {"mtime": None, "excel_file": None, "sheets": None}

    def __init__(self):
        self.valves = self.Valves()

    # ---------- внутренние утилиты ----------
    @classmethod
    def _load_excel(cls, path: str):
        """Читает ExcelFile с кэшем по mtime. Потокобезопасно."""
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Файл не найден: {path}")

        mtime = os.path.getmtime(path)
        with cls._cache_lock:
            if cls._cache["mtime"] == mtime and cls._cache["excel_file"] is not None:
                return cls._cache["excel_file"], cls._cache["sheets"]

        excel_file = pd.ExcelFile(path)
        sheets = excel_file.sheet_names

        with cls._cache_lock:
            cls._cache["mtime"] = mtime
            cls._cache["excel_file"] = excel_file
            cls._cache["sheets"] = sheets

        return excel_file, sheets

    @staticmethod
    def _truncate(df: pd.DataFrame, max_cell_len: int) -> pd.DataFrame:
        """Обрезает длинные строковые ячейки, чтобы не раздувать контекст."""

        def clip(v):
            if isinstance(v, str) and len(v) > max_cell_len:
                return v[:max_cell_len] + "…"
            return v

        return df.map(clip) if hasattr(df, "map") else df.applymap(clip)

    # ---------- основной метод ----------
    def search_warehouse(self, query: str, sheet_name: str = "Все") -> str:
        """
        Поиск по складу и учётным данным компании (Закупки, ОС Главная, Пластик).

        :param query: Поисковый запрос. Поддерживает:
                      - несколько слов через пробел (логика AND по всем колонкам),
                      - спец-запрос 'без места' — позиции с пустым 'Место хранения'.
        :param sheet_name: 'Закупки', 'ОС Главная', 'Пластик' или 'Все' (по всем листам).
        :return: Markdown-таблица с найденными позициями.
        """
        try:
            excel_path = str(self.valves.excel_path)
            excel_file, available_sheets = self._load_excel(excel_path)

            # --- какие листы обрабатываем ---
            if sheet_name and sheet_name != "Все" and sheet_name in available_sheets:
                target_sheets = [sheet_name]
            else:
                preferred = [
                    s.strip()
                    for s in str(self.valves.default_sheets).split(",")
                    if s.strip()
                ]
                target_sheets = [
                    s for s in preferred if s in available_sheets
                ] or available_sheets

            search_query = (query or "").strip().lower()
            if not search_query:
                return "Ошибка: задан пустой поисковый запрос."

            tokens = search_query.split()
            search_columns = [
                "Номенклатура",
                "Код",
                "Место хранения",
                "Проект",
                "Куратор МТО",
                "Отдел МТО",
                "QR Код",
                "Название",
                "Тип",
                "Цвет",
            ]

            all_results = []

            for sheet in target_sheets:
                df = excel_file.parse(sheet_name=sheet)
                if df.empty:
                    continue

                df = df.fillna("")

                if "Код" in df.columns:
                    df["Код"] = (
                        df["Код"].astype(str).str.replace(r"\.0$", "", regex=True)
                    )

                # --- маска поиска ---
                if search_query == "без места":
                    if "Место хранения" in df.columns:
                        mask = df["Место хранения"].astype(str).str.strip() == ""
                    else:
                        mask = pd.Series([False] * len(df))
                else:
                    avail_cols = [c for c in search_columns if c in df.columns]
                    if avail_cols and tokens:
                        corpus = (
                            df[avail_cols].astype(str).agg(" ".join, axis=1).str.lower()
                        )
                        mask = corpus.apply(lambda s: all(t in s for t in tokens))
                    else:
                        mask = pd.Series([False] * len(df))

                filtered_df = df[mask]
                if filtered_df.empty:
                    continue

                keep_cols = [c for c in filtered_df.columns if not c.startswith("_")]
                res_subset = filtered_df[keep_cols].copy()
                res_subset.insert(0, "Лист", sheet)
                all_results.append(res_subset)

            if not all_results:
                return f"По запросу «{query}» ничего не найдено."

            combined_df = pd.concat(all_results, ignore_index=True)
            total_found = len(combined_df)

            max_rows = int(self.valves.max_results)
            max_cell_len = int(self.valves.max_cell_len)

            limited_df = combined_df.head(max_rows).pipe(self._truncate, max_cell_len)

            output = (
                f"**Результаты поиска по запросу «{query}»** "
                f"(Найдено: {total_found}):\n\n"
            )
            output += limited_df.to_markdown(index=False)

            if total_found > max_rows:
                output += (
                    f"\n\n*Показаны первые {max_rows} из {total_found} записей. "
                    f"Уточните запрос, если нужная позиция не найдена.*"
                )

            return output

        except FileNotFoundError as e:
            return f"Ошибка: {e}"
        except PermissionError:
            return (
                "Ошибка: нет доступа к файлу. Возможно, он открыт в Excel — "
                "закройте его и повторите запрос."
            )
        except Exception as e:
            return f"Ошибка выполнения поиска: {e}"