import os
import requests
from datetime import datetime
import pandas as pd
from pydantic import BaseModel, Field


class Tools:

    class Valves(BaseModel):
        excel_path: str = Field(
            default=r"C:\Users\user\Desktop\inventarization_data\test_reaL_data.xlsx",
            description="Путь к Excel-файлу",
        )

    def __init__(self):
        self.valves = self.Valves()

    def search_excel(self, query: str) -> str:
        """
        Ищет информацию в Excel-таблице.
        :param query: Текст для поиска (имя, ID или значение)
        :return: Найденные строки
        """
        df = pd.read_excel(self.valves.excel_path)

        # Ищем совпадения во всех текстовых колонках
        mask = (
            df.astype(str)
            .apply(lambda col: col.str.contains(query, case=False, na=False))
            .any(axis=1)
        )

        results = df[mask]

        if results.empty:
            return "Ничего не найдено."

        return results.to_string(index=False)

        return None