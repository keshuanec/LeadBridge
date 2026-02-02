"""Custom template filters pro Lead Bridge"""
from django import template
from django.utils.safestring import mark_safe
from django.utils.html import escape

register = template.Library()


@register.filter(name='mailto')
def mailto(email):
    """
    Převede email na klikatelný mailto: odkaz.

    Použití v šabloně:
        {% load custom_filters %}
        {{ lead.client_email|mailto }}

    Args:
        email: Emailová adresa k zobrazení

    Returns:
        HTML odkaz s mailto: nebo prázdný řetězec
    """
    if not email:
        return ""

    email = str(email).strip()
    if not email:
        return ""

    # Escapujeme email pro bezpečnost
    escaped_email = escape(email)

    # Vrátíme HTML odkaz
    return mark_safe(f'<a href="mailto:{escaped_email}">{escaped_email}</a>')
