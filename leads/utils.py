"""Utility funkce pro zpracování dat v aplikaci leads"""
import re


def normalize_phone_number(phone: str) -> str:
    """
    Normalizuje telefonní číslo odstraněním mezer, pomlček a dalších znaků.
    Zachovává + na začátku pro mezinárodní předvolby.

    Příklady:
        "605 877 000" -> "605877000"
        "605-877-000" -> "605877000"
        "+421 905 123 456" -> "+421905123456"
        "+420 605 877 000" -> "+420605877000"

    Args:
        phone: Telefonní číslo k normalizaci

    Returns:
        Normalizované telefonní číslo (pouze číslice, případně + na začátku)
    """
    if not phone:
        return phone

    phone = phone.strip()

    # Zachováme + na začátku, pokud tam je
    has_plus = phone.startswith('+')

    # Odstraníme všechny znaky kromě číslic
    normalized = re.sub(r'[^\d]', '', phone)

    # Přidáme zpět + na začátek, pokud tam byl
    if has_plus:
        normalized = '+' + normalized

    return normalized