import io
import re
from typing import Optional
import pandas as pd
import yadisk
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
        """Скачивает бинарное содержимое Excel-файла с Яндекс.Диска с помощью библиотеки yadisk."""
        token_str = self.valves.yandex_token.get_secret_value() if isinstance(self.valves.yandex_token, SecretStr) else str(self.valves.yandex_token)
        
        if not token_str or token_str.startswith("y0_AgAAAA..."):
            raise ValueError("Укажите корректный YANDEX_TOKEN в настройках инструмента (Valves).")

        # Инициализируем клиент yadisk
        y = yadisk.YaDisk(token=token_str)
        if not y.check_token():
            raise RuntimeError("Неверный токен Яндекс.Диска или истек срок его действия.")

        # Скачиваем файл в оперативную память через буфер
        buffer = io.BytesIO()
        try:
            y.download(self.valves.disk_path, buffer)
        except Exception as e:
            raise RuntimeError(f"Не удалось скачать файл по пути '{self.valves.disk_path}': {str(e)}")
            
        buffer.seek(0)
        return buffer.read()

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

                # Очистка колонки "Код" от ".0", аналогично data_loader
                if "Код" in df.columns:
                    df["Код"] = df["Код"].astype(str).str.replace(r"\.0$", "", regex=True)

                # Формирование поискового корпуса по ключевым колонкам
                search_columns = [
                    "Номенклатура", "Код", "Место хранения", "Проект",
                    "Куратор МТО", "Отдел МТО", "QR Код", "Название", "Тип", "Цвет"
                ]
                available_search_cols = [col for col in search_columns if col in df.columns]

                if available_search_cols:
                    df["_search_corpus"] = (
                        df[available_search_cols].astype(str).agg(" ".join, axis=1).str.lower()
                    )
                else:
                    df["_search_corpus"] = df.astype(str).apply(lambda row: " ".join(row.values).lower(), axis=1)

                # Применяем мульти-словный поиск по созданному корпусу
                mask = pd.Series(True, index=df.index)
                for word in words:
                    mask = mask & df["_search_corpus"].str.contains(re.escape(word), regex=True)

                matched_df = df[mask].copy()

                if not matched_df.empty:
                    # Удаляем временную колонку корпуса перед выводом
                    if "_search_corpus" in matched_df.columns:
                        matched_df = matched_df.drop(columns=["_search_corpus"])
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