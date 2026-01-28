# Generated migration for removing the old OneToOne field
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('leads', '0018_migrate_lead_data'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='deal',
            name='lead',
        ),
    ]
