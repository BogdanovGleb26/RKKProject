import io
import pandas as pd
import requests
from dotenv import load_dotenv
import os

load_dotenv()
PUBLIC_URL = str(os.getenv("YADISK_PATH_GLEB_TEST"))
API_URL = 'https://cloud-api.yandex.net/v1/disk/public/resources/download'

# def get_download_url(public_url: str) -> str | None:
#     """Получает прямую ссылку на скачивание файла через API Яндекс Диска."""
#     api_url = 'https://cloud-api.yandex.net/v1/disk/public/resources/download'
#     params = {'public_key': public_url}

#     try:
#         response = requests.get(api_url, params=params, timeout=10)
#         response.raise_for_status()
#         return response.json().get('href')
#     except requests.RequestException as e:
#         print(f"Ошибка HTTP при получении ссылки на скачивание: {e}")
#         return None


# def fetch_sheet_data(public_url: str) -> pd.DataFrame | None:
#     """Загружает данные таблицы в Pandas DataFrame (поддерживает .xlsx и .csv)."""
#     download_url = get_download_url(public_url)
#     if not download_url:
#         return None

#     try:
#         response = requests.get(download_url, timeout=30)
#         response.raise_for_status()

#         # Читаем файл из бинарного потока в память
#         df = pd.read_excel(io.BytesIO(response.content))
#         return df.to_string(index=False)
#     except requests.RequestException as e:
#         print(f"Ошибка при скачивании файла: {e}")
#     except Exception as e:
#         print(f"Ошибка при обработке таблицы Pandas: {e}")
    
#     return None

def fetch_sheet_data() -> str | None:
    """Загружает данные таблицы с Яндекс Диска и возвращает их в виде строки."""
    try:
        # 1. Получаем прямую ссылку на скачивание через API
        api_response = requests.get(
            API_URL, 
            params={'public_key': PUBLIC_URL}, 
            timeout=10
        )
        api_response.raise_for_status()

        download_url = api_response.json().get('href')
        if not download_url:
            print("Ссылка на скачивание не найдена в ответе API.")
            return None

        # 2. Скачиваем сам файл
        file_response = requests.get(download_url, timeout=30)
        file_response.raise_for_status()

        # 3. Читаем таблицу и преобразуем в строку
        df = pd.read_excel(io.BytesIO(file_response.content))
        return df.to_string(index=False)

    except requests.RequestException as e:
        print(f"Ошибка при работе с сетью/API: {e}")
    except Exception as e:
        print(f"Ошибка при обработке таблицы: {e}")

    return None


if __name__ == "__main__":
    print("Запуск мониторинга таблицы...")
    print(fetch_sheet_data())


    # def get_download_url(self, public_url: str) -> str:
    #     """
    #     Получает прямую ссылку на скачивание файла через API Яндекс Диска.
    #     """

    #     full_api_url = self.valves.api_url
    #     params = {"public_key": public_url}

    #     try:
    #         response = requests.get(full_api_url, params=params, timeout=10)
    #         response.raise_for_status()
    #         return response.json().get("href")
    #     except requests.RequestException as e:
    #         return f"Ошибка HTTP при получении ссылки на скачивание: {e}"

    # def fetch_sheet_data(self, public_url: str) -> str:
    #     """
    #     Загружает данные таблицы Яндекс диска и возвращает в виде строки.
    #     """

    #     full_api_url = self.valves.api_url
    #     params = {"public_key": public_url}

    #     try:
    #         response = requests.get(full_api_url, params=params, timeout=10)
    #         response.raise_for_status()
    #         return response.json().get("href")
    #     except requests.RequestException as e:
    #         return f"Ошибка HTTP при получении ссылки на скачивание: {e}"

    #     download_url = get_download_url(self.valves.yadisk_path)

    #     try:
    #         response = requests.get(download_url, timeout=30)
    #         response.raise_for_status()

    #         df = pd.read_excel(io.BytesIO(response.content))
    #         return df.to_string(index=False)
    #     except requests.RequestException as e:
    #         return f"Ошибка при скачивании файла: {e}"
    #     except Exception as e:
    #         return f"Ошибка при обработке таблицы Pandas: {e}"

    #     return None

    # def fetch_sheet_data(public_url: str) -> str | None:
    #     """Загружает данные таблицы с Яндекс Диска и возвращает их в виде строки."""
    #     try:
    #         api_response = requests.get(
    #             self.valves.api_url, params={"public_key": public_url}, timeout=10
    #         )
    #         api_response.raise_for_status()

    #         download_url = api_response.json().get("href")
    #         if not download_url:
    #             print("Ссылка на скачивание не найдена в ответе API.")
    #             return None

    #         # 2. Скачиваем сам файл
    #         file_response = requests.get(download_url, timeout=30)
    #         file_response.raise_for_status()

    #         # 3. Читаем таблицу и преобразуем в строку
    #         df = pd.read_excel(io.BytesIO(file_response.content))
    #         return df.to_string(index=False)

    #     except requests.RequestException as e:
    #         print(f"Ошибка при работе с сетью/API: {e}")
    #     except Exception as e:
    #         print(f"Ошибка при обработке таблицы: {e}")

    #     return None