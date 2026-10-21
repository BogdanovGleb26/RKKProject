import os
import threading
import time
import pandas as pd
from pydantic import BaseModel, Field

# --- Windows-специфичные модули для shared-чтения ---
try:
    import win32file
    import win32con
    import msvcrt

    _HAS_WIN32 = True
except ImportError:
    _HAS_WIN32 = False


class Tools:
    class Valves(BaseModel):
        excel_path: str = Field(
            default=r"C:\Users\user\Desktop\inventarization_data\test_real_data.xlsx",
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
        cache_ttl_sec: int = Field(
            default=3,
            description=(
                "Сколько секунд считать кэш актуальным, даже если mtime не изменился. "
                "Уменьшает частоту открытия файла и конфликты с Excel."
            ),
        )

    # ---------- кэш ----------
    _cache_lock = threading.Lock()
    _cache = {"key": None, "data": None, "loaded_at": 0.0}

    def __init__(self):
        self.valves = self.Valves()

    # ---------- внутренние утилиты ----------
    @staticmethod
    def _open_shared(path: str):
        """
        Открывает файл на чтение, НЕ блокируя запись другим процессам (Windows).
        Использует CreateFile с FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE.
        Возвращает file-like объект в бинарном режиме.
        """
        if not _HAS_WIN32:
            # Fallback для не-Windows: обычное чтение (там блокировок нет)
            return open(path, "rb")

        handle = win32file.CreateFile(
            path,
            win32con.GENERIC_READ,
            win32con.FILE_SHARE_READ
            | win32con.FILE_SHARE_WRITE
            | win32con.FILE_SHARE_DELETE,
            None,  # security attributes
            win32con.OPEN_EXISTING,
            win32con.FILE_ATTRIBUTE_NORMAL,
            None,  # template
        )
        # Преобразуем Win32 HANDLE в обычный file descriptor, потом в file-like
        fd = msvcrt.open_osfhandle(handle.Detach(), os.O_RDONLY)
        return os.fdopen(fd, "rb")

    @classmethod
    def _load_excel(cls, path: str, cache_ttl_sec: int) -> dict:
        """
        Возвращает {sheet_name: DataFrame}.
        Оригинал открывается с share-флагами — Excel может его сохранять в это же время.
        Кэш: по (mtime, size) + TTL, чтобы лишний раз не открывать файл.
        """
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Файл не найден: {path}")

        mtime = os.path.getmtime(path)
        size = os.path.getsize(path)
        key = (mtime, size)
        now = time.time()

        with cls._cache_lock:
            cache_ok = (
                cls._cache["key"] == key
                and cls._cache["data"] is not None
                and (now - cls._cache["loaded_at"]) < cache_ttl_sec
            )
            if cache_ok:
                return cls._cache["data"]

        # Перечитываем. Открываем с share-флагами — Excel не блокируем.
        with cls._open_shared(path) as f:
            # pandas умеет читать .xlsx из file-like объекта через openpyxl
            with pd.ExcelFile(f) as xls:
                data = {s: xls.parse(s) for s in xls.sheet_names}

        with cls._cache_lock:
            cls._cache = {"key": key, "data": data, "loaded_at": time.time()}

        return data

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
            sheets_data = self._load_excel(excel_path, int(self.valves.cache_ttl_sec))
            available_sheets = list(sheets_data.keys())

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
                df = sheets_data[sheet].copy()  # обязательно: fillna мутирует
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
            return "Ошибка: нет доступа к файлу. Проверьте права на файл и папку."
        except Exception as e:
            return f"Ошибка выполнения поиска: {e}"
