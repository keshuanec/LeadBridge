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
    """Opraví meeting_done pro všechny leady které mají obchod"""

    print("=" * 60)
    print("OPRAVA MEETING STATISTIK")
    print("=" * 60)
    print()

    # Najít leady které mají obchod ale meeting_done=False
    leads_to_fix = Lead.objects.filter(
        communication_status='DEAL_CREATED',
        meeting_done=False
    )

    count = leads_to_fix.count()

    if count == 0:
        print("✓ Všechny leady s obchodem mají správně nastavené meeting_done=True")
        print("  Není třeba nic opravovat.")
        return

    print(f"Nalezeno {count} leadů s obchodem ale meeting_done=False")
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
        lead.meeting_done = True
        if not lead.meeting_done_at:
            # Použít updated_at nebo current time jako fallback
            lead.meeting_done_at = lead.updated_at or timezone.now()
        lead.save(update_fields=['meeting_done', 'meeting_done_at'])
        print(f"  ✓ Opraven Lead #{lead.pk} - {lead.client_name}")
        fixed_count += 1

    print()
    print("=" * 60)
    print(f"HOTOVO! Opraveno {fixed_count} leadů.")
    print("=" * 60)

    # Zkontrolovat výsledek
    fixed = Lead.objects.filter(communication_status='DEAL_CREATED', meeting_done=True).count()
    total_with_deal = Lead.objects.filter(communication_status='DEAL_CREATED').count()
    print(f"Výsledek: {fixed}/{total_with_deal} leadů s obchodem má meeting_done=True")
    print()


if __name__ == "__main__":
    fix_meeting_stats()
