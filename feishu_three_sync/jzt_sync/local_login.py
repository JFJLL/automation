# -*- coding: utf-8 -*-
import os

USERNAME = os.getenv('JZT_USERNAME', '')
PASSWORD = os.getenv('JZT_PASSWORD', '')

def get_credentials():
    username = os.getenv('JZT_USERNAME', '')
    password = os.getenv('JZT_PASSWORD', '')
    if not username or not password:
        try:
            import keyring
            username = username or keyring.get_password('jzt_sync', 'username') or ''
            password = password or keyring.get_password('jzt_sync', 'password') or ''
        except Exception:
            pass
    return username, password
