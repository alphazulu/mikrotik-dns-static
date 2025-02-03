import requests
import socket
import ssl
from librouteros import connect
from librouteros.exceptions import TrapError
from librouteros.query import Key
from librouteros.login import plain
from functools import partial
from dotenv import load_dotenv
import os

# Загрузка переменных окружения из .env файла
load_dotenv()

# Параметры для подключения из .env
MIKROTIK_HOST = os.getenv("MIKROTIK_HOST", "192.168.88.1")
MIKROTIK_USER = os.getenv("MIKROTIK_USER", "admin")
MIKROTIK_PASS = os.getenv("MIKROTIK_PASS", "admin")
FILE_URL = os.getenv(
    "FILE_URL", "https://raw.githubusercontent.com/itdoginfo/allow-domains/main/Russia/inside-raw.lst")
ADDRESS_LIST = os.getenv("ADDRESS_LIST", "vpn")
RESOLVER_IP = os.getenv("RESOLVER_IP", "8.8.8.8")
USE_SSL = os.getenv("USE_SSL", "False").lower() == "true"
API_PORT = 8729 if USE_SSL else 8728
LOGIN_METHOD = plain

# Функция для настройки SSL-соединения


def get_ssl_context():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.set_ciphers('ADH:@SECLEVEL=0')
    return partial(ctx.wrap_socket, server_hostname=MIKROTIK_HOST)

# Функция для скачивания файла с доменами


def download_file(file_url):
    try:
        response = requests.get(file_url, timeout=10)
        response.raise_for_status()
        print(f"Successfully downloaded the file from {file_url}")
        return response.text.splitlines()
    except requests.RequestException as e:
        print(f"Error downloading file: {e}")
        return []

# Фильтрация доменов до второго уровня и удаление 'www.'


def filter_domains(domains):
    normalized_domains = []

    for domain in domains:
        if domain.startswith("www."):
            domain = domain[4:]

        parts = domain.split('.')
        if len(parts) > 2:
            domain = '.'.join(parts[-2:])

        # Если остался только домен верхнего уровня, убираем точку
        if domain.startswith('.'):
            domain = domain[1:]

        normalized_domains.append(domain)

    unique_domains = list(set(normalized_domains))
    print(f"Filtered to {len(unique_domains)} unique second-level domains.")
    return unique_domains


# Получаем список уже добавленных доменов в роутере

def get_existing_domains():
    """Получение списка доменов, уже добавленных в MikroTik, через API."""
    try:
        connection_params = {
            "username": MIKROTIK_USER,
            "password": MIKROTIK_PASS,
            "host": MIKROTIK_HOST,
            "port": API_PORT,
            "login_method": LOGIN_METHOD,
        }
        if USE_SSL:
            connection_params["ssl_wrapper"] = get_ssl_context()

        connection = connect(**connection_params)
        print("Connected to MikroTik API successfully.")

        # Определяем ключи запроса
        name_key = Key('name')

    # address_key = Key('address')

        # Запрашиваем только список имен (доменных записей)
        dns_static_path = connection.path('ip', 'dns', 'static')
        query = dns_static_path.select(name_key)

    # existing_domains = list(dns_static_path.select(name_key, address_key))
        # existing_domains = list(dns_static_path.select(name_key))
        existing_domains = set(entry.get('name', '')
                               for entry in dns_static_path.select(name_key))

        connection.close()
        print(
            f"Retrieved {len(existing_domains)} existing domains from MikroTik.")

        # Возвращаем множество для быстрого поиска
        return set(existing_domains)

    except (socket.error, TrapError) as e:
        print(f"Connection or API error: {e}")
        return set()
    except Exception as e:
        print(f"Unexpected error: {e}")
        return set()

# Добавление DNS-записей через API MikroTik


def add_dns_entry_to_mikrotik(domains):
    try:
        existing_domains = get_existing_domains()  # Получаем существующие записи

        connection_params = {
            "username": MIKROTIK_USER,
            "password": MIKROTIK_PASS,
            "host": MIKROTIK_HOST,
            "port": API_PORT,
            "login_method": LOGIN_METHOD,
        }
        if USE_SSL:
            connection_params["ssl_wrapper"] = get_ssl_context()

        connection = connect(**connection_params)
        print("Connected to MikroTik API successfully.")
        dns_static_path = connection.path('ip', 'dns', 'static')
        name_key = Key('name')
        address_key = Key('address')

        added_count = 0
        skipped_count = 0

    #     for domain in domains:
    #         existing_entries = list(dns_static_path.select(
    #             name_key, address_key).where(name_key == domain))
    #         if not existing_entries:
    #             dns_static_path.add(
    #                 name=domain,
    #                 type='FWD',
    #                 **{
    #                     'forward-to': RESOLVER_IP,
    #                     'match-subdomain': 'yes',
    #                     'address-list': ADDRESS_LIST
    #                 }
    #             )
    #             added_count += 1
    #             print(
    #                 f"Added DNS entry: {domain} resolver {RESOLVER_IP} addr list {ADDRESS_LIST}")
    #         else:
    #             skipped_count += 1

    #     print(
    #         f"Added {added_count} new DNS entries. Skipped {skipped_count} existing entries.")
    #     connection.close()
    #     print("API connection closed.")
    # except (socket.error, TrapError) as e:
    #     print(f"Connection or API error: {e}")
    # except Exception as e:
    #     print(f"Unexpected error: {e}")

        for domain in domains:
            if domain not in existing_domains:  # Проверяем, есть ли уже такой домен
                dns_static_path.add(
                    name=domain,
                    type='FWD',
                    **{
                        'forward-to': RESOLVER_IP,
                        'match-subdomain': 'yes',
                        'address-list': ADDRESS_LIST
                    }
                )
                added_count += 1
                print(f"Added DNS entry: {domain}")

        connection.close()
        print(f"Added {added_count} new DNS entries.")
    except (socket.error, TrapError) as e:
        print(f"Connection or API error: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")


# Основная логика


def main():
    domains = download_file(FILE_URL)
    if domains:
        print(f"Downloaded {len(domains)} domains.")
        filtered_domains = filter_domains(domains)
        print(
            f"Filtered {len(filtered_domains)} domains (after normalizing to second-level domains).")
        add_dns_entry_to_mikrotik(filtered_domains)
    else:
        print("No domains to add.")


if __name__ == "__main__":
    main()
