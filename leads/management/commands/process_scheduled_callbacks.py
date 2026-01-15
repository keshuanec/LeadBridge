from django.core.management.base import BaseCommand
from django.utils import timezone
from leads.models import Lead, LeadHistory
from leads.services import notifications


class Command(BaseCommand):
    help = 'Zpracuje odložené hovory - vrátí leady do stavu NEW a odešle notifikace'

    def handle(self, *args, **options):
        today = timezone.now().date()

        # Najdi leady s plánovaným hovorov na dnes nebo dříve
        leads_to_process = Lead.objects.filter(
            callback_scheduled_date__lte=today,
            communication_status=Lead.CommunicationStatus.WAITING_FOR_CLIENT
        ).select_related('advisor', 'referrer')

        processed_count = 0

        for lead in leads_to_process:
            old_date = lead.callback_scheduled_date
            callback_note = lead.callback_note

            # Změň stav zpět na NEW
            lead.communication_status = Lead.CommunicationStatus.NEW
            lead.callback_scheduled_date = None
            lead.callback_note = ""
            lead.save()

            # Přidej záznam do historie
            LeadHistory.objects.create(
                lead=lead,
                event_type=LeadHistory.EventType.STATUS_CHANGED,
                user=None,  # Automatický proces
                description=f"Plánovaný hovor ({old_date.strftime('%d.%m.%Y')}) - lead vrácen do stavu 'Nový'."
            )

            # Odešli notifikaci poradci
            if lead.advisor:
                notifications.notify_callback_due(lead, callback_note)

            processed_count += 1
            self.stdout.write(
                self.style.SUCCESS(f'Zpracován lead #{lead.id} - {lead.client_name}')
            )

        self.stdout.write(
            self.style.SUCCESS(f'Celkem zpracováno: {processed_count} leadů')
        )
