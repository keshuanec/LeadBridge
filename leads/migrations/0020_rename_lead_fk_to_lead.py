# Generated migration for renaming lead_fk to lead and making it NOT NULL
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('leads', '0019_remove_old_lead_field'),
    ]

    operations = [
        migrations.RenameField(
            model_name='deal',
            old_name='lead_fk',
            new_name='lead',
        ),
        migrations.AlterField(
            model_name='deal',
            name='lead',
            field=models.ForeignKey(
                'Lead',
                on_delete=models.PROTECT,
                related_name='deals',
                verbose_name="Lead",
            ),
        ),
    ]
