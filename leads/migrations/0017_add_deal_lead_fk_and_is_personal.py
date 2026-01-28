# Generated migration for adding ForeignKey and is_personal_deal fields
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('leads', '0016_remove_legacy_client_name'),
    ]

    operations = [
        migrations.AddField(
            model_name='deal',
            name='lead_fk',
            field=models.ForeignKey(
                'Lead',
                on_delete=models.PROTECT,
                related_name='deals',
                null=True,  # Temporarily nullable for data migration
                verbose_name="Lead",
            ),
        ),
        migrations.AddField(
            model_name='deal',
            name='is_personal_deal',
            field=models.BooleanField(
                verbose_name='Vlastní obchod',
                default=False,
                help_text="Obchod je výsledkem dlouhodobé práce poradce (bez provize pro strukturu)."
            ),
        ),
    ]
