# Generated manually on 2026-01-12

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leads', '0006_lead_meeting_done_lead_meeting_done_at_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='lead',
            name='is_personal_contact',
            field=models.BooleanField(default=False, help_text='Pokud je zaškrtnuto, lead je osobní kontakt poradce a nevyplácí se z něj žádné provize.', verbose_name='Vlastní kontakt'),
        ),
    ]
