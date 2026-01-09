# Generated migration for one-time production user import
from django.db import migrations
import json
import os


def import_users(apps, schema_editor):
    """Import users from JSON export"""
    User = apps.get_model('accounts', 'User')
    ReferrerProfile = apps.get_model('accounts', 'ReferrerProfile')

    # Path to JSON file
    json_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        'temp_import', 'users_export.json'
    )

    # Check if file exists
    if not os.path.exists(json_path):
        print(f"SKIP: {json_path} not found - already imported or not needed")
        return

    print(f"Loading data from {json_path}...")
    with open(json_path, 'r') as f:
        data = json.load(f)

    print(f"Loaded {len(data)} objects")

    # Import users first
    for item in data:
        if item['model'] == 'accounts.user':
            fields = item['fields']
            username = fields['username']

            # Skip if user already exists
            if User.objects.filter(username=username).exists():
                continue

            User.objects.create(
                username=username,
                first_name=fields['first_name'],
                last_name=fields['last_name'],
                email=fields['email'],
                phone=fields.get('phone', ''),
                password=fields['password'],  # Already hashed
                role=fields['role'],
                commission_total_per_million=fields['commission_total_per_million'],
                commission_referrer_pct=fields['commission_referrer_pct'],
                commission_manager_pct=fields['commission_manager_pct'],
                commission_office_pct=fields['commission_office_pct'],
                is_staff=fields['is_staff'],
                is_superuser=fields['is_superuser'],
                is_active=fields['is_active'],
            )
            print(f"  Created user: {username}")

    # Import ReferrerProfiles
    for item in data:
        if item['model'] == 'accounts.referrerprofile':
            fields = item['fields']
            user_username = fields['user'][0]  # natural key

            try:
                user = User.objects.get(username=user_username)
            except User.DoesNotExist:
                print(f"  SKIP: User {user_username} not found")
                continue

            # Skip if profile exists
            if ReferrerProfile.objects.filter(user=user).exists():
                continue

            manager = None
            if fields.get('manager'):
                try:
                    manager = User.objects.get(username=fields['manager'][0])
                except User.DoesNotExist:
                    pass

            profile = ReferrerProfile.objects.create(
                user=user,
                manager=manager
            )

            # Add advisors
            if fields.get('advisors'):
                for advisor_key in fields['advisors']:
                    try:
                        advisor = User.objects.get(username=advisor_key[0])
                        profile.advisors.add(advisor)
                    except User.DoesNotExist:
                        pass

            print(f"  Created profile for: {user_username}")

    print("✓ Import completed!")


def reverse_import(apps, schema_editor):
    """This migration cannot be reversed"""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0011_add_branding_settings'),
    ]

    operations = [
        migrations.RunPython(import_users, reverse_import),
    ]
