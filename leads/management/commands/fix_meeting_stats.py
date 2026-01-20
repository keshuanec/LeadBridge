from django.core.management.base import BaseCommand
from django.utils import timezone
from leads.models import Lead


class Command(BaseCommand):
    help = 'Opraví meeting_scheduled a meeting_done pro všechny leady které mají obchod'

    def add_arguments(self, parser):
        parser.add_argument(
            '--yes',
            action='store_true',
            help='Automaticky potvrdit opravu bez dotazu',
        )

    def handle(self, *args, **options):
        self.stdout.write("=" * 60)
        self.stdout.write("OPRAVA MEETING STATISTIK")
        self.stdout.write("=" * 60)
        self.stdout.write("")

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
            self.stdout.write(self.style.SUCCESS(
                "✓ Všechny leady s obchodem mají správně nastavené meeting_scheduled=True a meeting_done=True"
            ))
            self.stdout.write("  Není třeba nic opravovat.")
            return

        self.stdout.write(f"Nalezeno {count} leadů s obchodem ale špatnými meeting fieldy:")
        self.stdout.write("")
        for lead in leads_to_fix:
            self.stdout.write(f"  Lead #{lead.pk} - {lead.client_name}")
            self.stdout.write(f"    meeting_scheduled={lead.meeting_scheduled}, meeting_done={lead.meeting_done}")
        self.stdout.write("")

        # Požádat o potvrzení (pokud není --yes)
        if not options['yes']:
            response = input(f"Chcete opravit těchto {count} leadů? (ano/ne): ")
            if response.lower() != "ano":
                self.stdout.write("Zrušeno.")
                return

        self.stdout.write("")
        self.stdout.write("Opravuji...")
        self.stdout.write("")

        fixed_count = 0
        for lead in leads_to_fix:
            lead.meeting_scheduled = True
            lead.meeting_done = True
            if not lead.meeting_done_at:
                # Použít updated_at nebo current time jako fallback
                lead.meeting_done_at = lead.updated_at or timezone.now()
            lead.save(update_fields=['meeting_scheduled', 'meeting_done', 'meeting_done_at'])
            self.stdout.write(f"  ✓ Opraven Lead #{lead.pk} - {lead.client_name}")
            fixed_count += 1

        self.stdout.write("")
        self.stdout.write("=" * 60)
        self.stdout.write(self.style.SUCCESS(f"HOTOVO! Opraveno {fixed_count} leadů."))
        self.stdout.write("=" * 60)

        # Zkontrolovat výsledek
        total_with_deals = 0
        correctly_set = 0
        for lead in Lead.objects.all():
            if hasattr(lead, 'deal'):
                total_with_deals += 1
                if lead.meeting_scheduled and lead.meeting_done:
                    correctly_set += 1

        self.stdout.write(f"Výsledek: {correctly_set}/{total_with_deals} leadů s obchodem má správně nastavené meeting fieldy")
        self.stdout.write("")