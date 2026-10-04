import io
import re
import pandas as pd
import requests
from pydantic import BaseModel, Field

class Tools:
    class Valves(BaseModel):
        yadisk_path: str = Field(
            default=os.getenv("YADISK_PATH"),
            description="Путь к Excel-файлу на Яндекс Диске (публичная ссылка)",
        )
        api_url: str = Field(
            default="https://cloud-api.yandex.net/v1/disk/public/resources/download",
            description="Путь к API Яндекс Диска для получения ссылки на скачивание",
        )
        max_results: int = Field(
            default=20,
            description="Максимальное количество выводимых строк, чтобы не перегружать контекст модели",
        )

    def __init__(self):
        self.valves = self.Valves()

    def search_warehouse(self, query: str, sheet_name: str = "Все") -> str:
        """
        Поиск по складу и учетным данным компании (Закупки, ОС Главная, Пластик).
        
        :param query: Поисковый запрос (название детали, код, локация, фамилия куратора или спец-запрос 'без места').
        :param sheet_name: Название раздела учетных данных: 'Закупки', 'ОС Главная', 'Пластик' или 'Все' для поиска по всем листам.
        :return: Отформатированная текстовая таблица с найденными позициями.
        """
        try:
            yadisk_url = getattr(
                self.valves.yadisk_path, "default", self.valves.yadisk_path
            )
            api_endpoint = getattr(
                self.valves.api_url, "default", self.valves.api_url
            )

            # 1. Получение прямой ссылки на скачивание с Яндекс.Диска
            api_response = requests.get(
                str(api_endpoint),
                params={"public_key": str(yadisk_url)},
                timeout=10,
            )
            api_response.raise_for_status()

            download_url = api_response.json().get("href")
            if not download_url:
                return "Ошибка: Не удалось получить ссылку на скачивание файла."

            # 2. Скачивание файла в память
            file_response = requests.get(download_url, timeout=30)
            file_response.raise_for_status()

            excel_file = pd.ExcelFile(io.BytesIO(file_response.content))

            # Определяем, какие листы будем обрабатывать
            available_sheets = excel_file.sheet_names
            if sheet_name != "Все" and sheet_name in available_sheets:
                target_sheets = [sheet_name]
            else:
                target_sheets = [s for s in ["Закупки", "ОС Главная", "Пластик"] if s in available_sheets]
                if not target_sheets:
                    target_sheets = available_sheets

            search_query = query.strip().lower()
            if not search_query:
                return "Ошибка: Задан пустой поисковый запрос."

            tokens = [t for t in search_query.split() if len(t) > 0]
            search_columns = [
                "Номенклатура", "Код", "Место хранения", "Проект",
                "Куратор МТО", "Отдел МТО", "QR Код", "Название", "Тип", "Цвет"
            ]

            all_results = []

            # 3. Обработка каждого листа и выполнение поиска
            for sheet in target_sheets:
                df = excel_file.parse(sheet_name=sheet)
                if df.empty:
                    continue

                df = df.fillna("")

                # Очистка формата кодов
                if "Код" in df.columns:
                    df["Код"] = df["Код"].astype(str).str.replace(r"\.0$", "", regex=True)

                # Выполнение фильтрации
                if search_query == "без места":
                    if "Место хранения" in df.columns:
                        mask = df["Место хранения"].astype(str).str.strip() == ""
                    else:
                        mask = pd.Series([True] * len(df))
                else:
                    avail_cols = [c for c in search_columns if c in df.columns]
                    if avail_cols and tokens:
                        corpus = df[avail_cols].astype(str).agg(" ".join, axis=1).str.lower()
                        mask = corpus.apply(lambda c_str: all(t in c_str for t in tokens))
                    else:
                        mask = pd.Series([False] * len(df))

                filtered_df = df[mask]

                if not filtered_df.empty:
                    # Оставляем только содержательные колонки для вывода LLM
                    keep_cols = [c for c in filtered_df.columns if not c.startswith("_")]
                    res_subset = filtered_df[keep_cols].copy()
                    res_subset.insert(0, "Лист", sheet)
                    all_results.append(res_subset)

            if not all_results:
                return f"По запросу «{query}» ничего не найдено."

            # 4. Объединение результатов и ограничение вывода
            combined_df = pd.concat(all_results, ignore_index=True)
            total_found = len(combined_df)
            max_rows = getattr(self.valves.max_results, "default", self.valves.max_results)

            limited_df = combined_df.head(max_rows)

            output = f"**Результаты поиска по запросу «{query}»** (Найдено: {total_found}):\n\n"
            output += limited_df.to_markdown(index=False)

            if total_found > max_rows:
                output += f"\n\n *Показаны первые {max_rows} из {total_found} найденных записей. Уточните запрос, если нужная позиция не найдена.*"

            return output

        except requests.RequestException as e:
            return f"Ошибка сети при обращении к Яндекс Диску: {e}"
        except Exception as e:
            return f"Ошибка выполнения поиска: {e}"