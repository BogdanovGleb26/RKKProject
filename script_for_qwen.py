import io
import re
import urllib.parse
from typing import Optional
import pandas as pd
import requests
from pydantic import BaseModel, Field, SecretStr


class Tools:

    class Valves(BaseModel):
        yandex_token: SecretStr = Field(
            default=SecretStr("y0_AgAAAA...ЗАМЕНИТЬ НА ТОКЕН НА ЗАПИСЬ"),
            description="OAuth-токен Яндекс.Диска",
        )
        disk_path: str = Field(
            default="/rkk_test_dataset.xlsx",
            description="Путь к Excel-файлу на Яндекс.Диске",
        )
        max_results: int = Field(
            default=50,
            description="Максимальное количество возвращаемых строк",
        )

    def __init__(self):
        self.valves = self.Valves()

    def _download_excel_from_yandex_disk(self) -> bytes:
        """Скачивает бинарное содержимое Excel-файла с Яндекс.Диска через OAuth API."""
        if not self.valves.yandex_token or self.valves.yandex_token.startswith("y0_AgAAAA..."):
            raise ValueError("Укажите корректный YANDEX_TOKEN в настройках инструмента (Valves).")

        base_url = "https://cloud-api.yandex.net/v1/disk/resources/download"
        headers = {"Authorization": f"OAuth {self.valves.yandex_token}"}
        params = {"path": self.valves.disk_path}

        # 1. Запрос ссылки на скачивание
        response = requests.get(base_url, headers=headers, params=params, timeout=15)
        if response.status_code != 200:
            error_msg = response.json().get("message", response.text)
            raise RuntimeError(f"Ошибка получения ссылки Яндекс.Диска [{response.status_code}]: {error_msg}")

        download_url = response.json().get("href")
        if not download_url:
            raise RuntimeError("Яндекс API не вернул прямую ссылку на скачивание.")

        # 2. Скачивание самого файла
        file_response = requests.get(download_url, timeout=30)
        if file_response.status_code != 200:
            raise RuntimeError(f"Ошибка скачивания файла [{file_response.status_code}]")

        return file_response.content

    def search_excel_from_yandex_disk(self, query: str, sheet_name: Optional[str] = None) -> str:
        """
        Ищет предметы, деталь, позицию закупки, ОС или пластик в реестре склада на Яндекс.Диске.

        :param query: Поисковый запрос (название, код товара, QR-код, ФИО куратора или место хранения)
        :param sheet_name: Необязательное имя листа для поиска: 'Закупки', 'ОС Главная' или 'Пластик'. Если не указано, ищет по всем листам.
        :return: Найденные позиции в текстовом формате или сообщение об отсутствии результатов.
        """
        try:
            excel_bytes = self._download_excel_from_yandex_disk()
            
            # Читаем все листы или конкретный
            excel_file = pd.ExcelFile(io.BytesIO(excel_bytes), engine="calamine")
            sheets_to_search = [sheet_name] if sheet_name and sheet_name in excel_file.sheet_names else excel_file.sheet_names

            all_results = []
            words = [w.strip().lower() for w in query.strip().split() if w.strip()]

            if not words:
                return "Поисковый запрос пуст."

            for sheet in sheets_to_search:
                df = pd.read_excel(excel_file, sheet_name=sheet)
                df = df.fillna("")  # Убираем NaN для корректного поиска

                if df.empty:
                    continue

                # Применяем мульти-словный поиск (все слова из запроса должны присутствовать в строке)
                # Формируем объединенный текст по всем колонкам для каждой строки
                row_texts = df.astype(str).apply(lambda row: " ".join(row.values).lower(), axis=1)

                mask = pd.Series(True, index=df.index)
                for word in words:
                    mask = mask & row_texts.str.contains(re.escape(word), regex=True)

                matched_df = df[mask].copy()

                if not matched_df.empty:
                    matched_df["Лист/Раздел"] = sheet
                    all_results.append(matched_df)

            if not all_results:
                return f"По запросу «{query}» ничего не найдено на складе."

            # Объединяем результаты
            final_df = pd.concat(all_results, ignore_index=True)

            # Ограничиваем выдачу, чтобы не перегружать контекст модели (Context Window limit)
            total_found = len(final_df)
            if total_found > self.valves.max_results:
                final_df = final_df.head(self.valves.max_results)
                limit_warning = f"\n\n*(Показано первые {self.valves.max_results} из {total_found} найденных записей)*"
            else:
                limit_warning = ""

            return final_df.to_string(index=False) + limit_warning

        except Exception as e:
            return f"Ошибка при выполнении поиска по складу: {str(e)}"