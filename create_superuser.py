#!/usr/bin/env python
"""
Jednorázový skript pro vytvoření superusera v produkci.
Po použití tento soubor smažte.
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'leadbridge.settings')
django.setup()

from django.contrib.auth import get_user_model

User = get_user_model()

# Nastavte své údaje zde:
USERNAME = os.environ.get('SUPERUSER_USERNAME', 'admin')
EMAIL = os.environ.get('SUPERUSER_EMAIL', 'admin@leadbridge.cz')
PASSWORD = os.environ.get('SUPERUSER_PASSWORD', 'changeme123')

if not User.objects.filter(username=USERNAME).exists():
    User.objects.create_superuser(
        username=USERNAME,
        email=EMAIL,
        password=PASSWORD
    )
    print(f'✓ Superuser "{USERNAME}" byl úspěšně vytvořen!')
else:
    print(f'✗ Superuser "{USERNAME}" již existuje.')