import pandas as pd
import urllib.parse
import requests
import time
import io

PUBLIC_URL = 'https://disk.yandex.ru/i/ixCs6geytgc61Q'

def get_download_url(public_url):
    """Получает прямую ссылку на скачивание файла через API Яндекс Диска."""
    base_url = 'https://cloud-api.yandex.net/v1/disk/public/resources/download?'
    final_url = base_url + urllib.parse.urlencode({'public_key': public_url})
    
    try:
        response = requests.get(final_url)
        response.raise_for_status()
        return response.json().get('href')
    except Exception as e:
        print(f"Ошибка при получении ссылки на скачивание: {e}")
        return None

def fetch_sheet_data(public_url):
    """Загружает данные таблицы в Pandas DataFrame (поддерживает .xlsx и .csv)."""
    download_url = get_download_url(public_url)
    
    if download_url:
        try:
            response = requests.get(download_url)
            response.raise_for_status()
            
            # Читаем файл из бинарного потока в память как Excel
            df = pd.read_excel(io.BytesIO(response.content))
            return df
        except Exception as e:
            print(f"Ошибка при чтении таблицы: {e}")
            return None
    return None

# Переменная для отслеживания количества обработанных строк
processed_rows_count = 0

def check_for_new_data():
    global processed_rows_count
    df = fetch_sheet_data(PUBLIC_URL)
    
    if df is not None:
        total_rows = len(df)
        
        if total_rows > processed_rows_count:
            # Выделяем только новые строки
            new_rows = df.iloc[processed_rows_count:]
            print(f"[{time.strftime('%H:%M:%S')}] Найдено новых строк: {len(new_rows)}")
            print(new_rows)
            print("-" * 40)
            
            # Обновляем счетчик
            processed_rows_count = total_rows
        else:
            print(f"[{time.strftime('%H:%M:%S')}] Новых данных нет.")

if __name__ == "__main__":
    print("Запуск мониторинга таблицы...")
    while True:
        check_for_new_data()
        time.sleep(10)  # Интервал проверки в секундах