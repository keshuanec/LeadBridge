#!/usr/bin/env python3
"""
Skript pro opravu meeting statistik ve starých datech.

Problém: Staré leady které mají obchod (DEAL_CREATED) nemají správně nastavené
meeting_done=True, protože toto pole se nastavovalo až po implementaci nové logiky.

Řešení: Nastavit meeting_done=True pro všechny leady které mají status DEAL_CREATED,
protože pokud byl vytvořen obchod, musela předcházet realizovaná schůzka.

Použití:
    python3 fix_meeting_stats.py
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'leadbridge.settings')
django.setup()

from leads.models import Lead
from django.utils import timezone


def fix_meeting_stats():
    """Opraví meeting_scheduled a meeting_done pro všechny leady které mají obchod"""

    print("=" * 60)
    print("OPRAVA MEETING STATISTIK")
    print("=" * 60)
    print()

    # Najít všechny leady které mají obchod (Deal objekt)
    # ale nemají správně nastavené meeting_scheduled nebo meeting_done
    all_leads = Lead.objects.all()
    leads_to_fix = []

    for lead in all_leads:
        if hasattr(lead, 'deal'):
            if not lead.meeting_scheduled or not lead.meeting_done:
                leads_to_fix.append(lead)

    count = len(leads_to_fix)

    if count == 0:
        print("✓ Všechny leady s obchodem mají správně nastavené meeting_scheduled=True a meeting_done=True")
        print("  Není třeba nic opravovat.")
        return

    print(f"Nalezeno {count} leadů s obchodem ale špatnými meeting fieldy:")
    print()
    for lead in leads_to_fix:
        print(f"  Lead #{lead.pk} - {lead.client_name}")
        print(f"    meeting_scheduled={lead.meeting_scheduled}, meeting_done={lead.meeting_done}")
    print()

    # Požádat o potvrzení
    response = input(f"Chcete opravit těchto {count} leadů? (ano/ne): ")
    if response.lower() != "ano":
        print("Zrušeno.")
        return

    print()
    print("Opravuji...")
    print()

    fixed_count = 0
    for lead in leads_to_fix:
        lead.meeting_scheduled = True
        lead.meeting_done = True
        if not lead.meeting_done_at:
            # Použít updated_at nebo current time jako fallback
            lead.meeting_done_at = lead.updated_at or timezone.now()
        lead.save(update_fields=['meeting_scheduled', 'meeting_done', 'meeting_done_at'])
        print(f"  ✓ Opraven Lead #{lead.pk} - {lead.client_name}")
        fixed_count += 1

    print()
    print("=" * 60)
    print(f"HOTOVO! Opraveno {fixed_count} leadů.")
    print("=" * 60)

    # Zkontrolovat výsledek
    total_with_deals = 0
    correctly_set = 0
    for lead in Lead.objects.all():
        if hasattr(lead, 'deal'):
            total_with_deals += 1
            if lead.meeting_scheduled and lead.meeting_done:
                correctly_set += 1

    print(f"Výsledek: {correctly_set}/{total_with_deals} leadů s obchodem má správně nastavené meeting fieldy")
    print()


if __name__ == "__main__":
    fix_meeting_stats()
