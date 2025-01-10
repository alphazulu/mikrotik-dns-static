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
MIKROTIK_HOST = os.getenv("MIKROTIK_HOST")
MIKROTIK_USER = os.getenv("MIKROTIK_USER")
MIKROTIK_PASS = os.getenv("MIKROTIK_PASS")
FILE_URL = os.getenv("FILE_URL")
ADDRESS_LIST = os.getenv("ADDRESS_LIST")
RESOLVER_IP = os.getenv("RESOLVER_IP")
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

        normalized_domains.append(domain)

    unique_domains = list(set(normalized_domains))
    print(f"Filtered to {len(unique_domains)} unique second-level domains.")
    return unique_domains

# Добавление DNS-записей через API MikroTik


def add_dns_entry_to_mikrotik(domains):
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
        dns_static_path = connection.path('ip', 'dns', 'static')
        name_key = Key('name')
        address_key = Key('address')

        added_count = 0
        skipped_count = 0

        for domain in domains:
            existing_entries = list(dns_static_path.select(
                name_key, address_key).where(name_key == domain))
            if not existing_entries:
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
                print(
                    f"Added DNS entry: {domain} resolver {RESOLVER_IP} addr list {ADDRESS_LIST}")
            else:
                skipped_count += 1

        print(
            f"Added {added_count} new DNS entries. Skipped {skipped_count} existing entries.")
        connection.close()
        print("API connection closed.")
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
