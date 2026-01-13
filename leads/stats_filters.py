"""
Utility modul pro časové filtrování statistik.
"""
from datetime import datetime, timedelta
from django.utils import timezone
from django.db.models import Q


def parse_date_filters(request):
    """
    Parsuje GET parametry a vrací slovník s date_from, date_to podle presetu.

    Podporované presety:
    - 'all': žádný časový filtr (default)
    - 'year': aktuální rok (od 1.1.)
    - 'month': aktuální měsíc (od 1. dne)
    - 'custom': vlastní rozsah z date_from a date_to parametrů

    Args:
        request: Django HTTP request objekt

    Returns:
        dict: {'preset': str, 'date_from': date|None, 'date_to': date|None}
    """
    preset = request.GET.get('date_preset', 'all')

    # Validace presetu
    if preset not in ['all', 'year', 'month', 'custom']:
        preset = 'all'

    if preset == 'year':
        # Tento rok od 1.1.
        date_from = datetime(timezone.now().year, 1, 1).date()
        date_to = None
    elif preset == 'month':
        # Tento měsíc od 1. dne
        now = timezone.now()
        date_from = datetime(now.year, now.month, 1).date()
        date_to = None
    elif preset == 'custom':
        # Vlastní rozsah z inputů
        date_from = parse_date_safe(request.GET.get('date_from', ''))
        date_to = parse_date_safe(request.GET.get('date_to', ''))

        # Edge case: date_to je před date_from → prohodit
        if date_from and date_to and date_to < date_from:
            date_from, date_to = date_to, date_from

        # Edge case: oba prázdné → fallback na 'all'
        if not date_from and not date_to:
            preset = 'all'
    else:
        # 'all' nebo neznámý → žádný filtr
        date_from = None
        date_to = None

    return {
        'preset': preset,
        'date_from': date_from,
        'date_to': date_to,
    }


def parse_date_safe(date_str):
    """
    Bezpečně parsuje datum ve formátu YYYY-MM-DD.

    Args:
        date_str: řetězec s datem

    Returns:
        date|None: parsované datum nebo None při chybě
    """
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return None
