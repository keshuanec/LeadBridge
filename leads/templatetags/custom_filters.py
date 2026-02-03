"""Custom template filters pro Lead Bridge"""
from django import template
from django.utils.safestring import mark_safe
from django.utils.html import escape
import re

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


@register.filter(name='format_phone')
def format_phone(phone):
    """
    Formátuje telefonní číslo s vizuálními mezerami pro lepší čitelnost.
    Při kopírování se mezery nezkopírují (díky CSS pseudo-elementům).

    Formát:
    - České číslo (9 číslic): 605 877 000 (3-3-3)
    - Mezinárodní (+předvolba): +421 905 123 456 (předvolba-3-3-3)

    Použití v šabloně:
        {% load custom_filters %}
        {{ lead.client_phone|format_phone }}

    Args:
        phone: Telefonní číslo (např. "605877000" nebo "+421905123456")

    Returns:
        HTML s formátovaným číslem nebo prázdný řetězec
    """
    if not phone:
        return ""

    phone = str(phone).strip()
    if not phone:
        return ""

    # Escapujeme pro bezpečnost
    phone = escape(phone)

    # Rozdělíme číslo na části
    parts = []

    if phone.startswith('+'):
        # Mezinárodní číslo: +421905123456 -> +421 905 123 456
        # Najdeme předvolbu (+ a následující číslice do prvního bloku 3 číslic)
        match = re.match(r'(\+\d+?)(\d{3})(\d{3})(\d+)', phone)
        if match:
            parts = list(match.groups())
        else:
            # Fallback: prostě rozdělíme po 3 číslicích
            parts = [phone[0:4]] + [phone[i:i+3] for i in range(4, len(phone), 3)]
    else:
        # České číslo: 605877000 -> 605 877 000
        # Rozdělíme po 3 číslicích
        parts = [phone[i:i+3] for i in range(0, len(phone), 3)]

    # Vyfiltrujeme prázdné části
    parts = [p for p in parts if p]

    if not parts:
        return phone

    # Obalíme každou část do <span class="phone-part">
    html_parts = [f'<span class="phone-part">{part}</span>' for part in parts]

    # Spojíme do kontejneru
    return mark_safe(f'<span class="phone-formatted">{"".join(html_parts)}</span>')
