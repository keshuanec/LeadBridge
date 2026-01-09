# Generated migration to fix advisor assignments
from django.db import migrations


def fix_advisors(apps, schema_editor):
    """Ensure all ReferrerProfiles have correct advisors assigned"""
    User = apps.get_model('accounts', 'User')
    ReferrerProfile = apps.get_model('accounts', 'ReferrerProfile')

    # Find advisors by username (from export)
    try:
        jiri = User.objects.get(username='poradce1')
        michaela = User.objects.get(username='poradce2')
    except User.DoesNotExist as e:
        print(f"SKIP: Could not find advisors - {e}")
        return

    print(f"Found advisors: {jiri.get_full_name()}, {michaela.get_full_name()}")

    # Count profiles
    all_profiles = ReferrerProfile.objects.all()
    total = all_profiles.count()
    print(f"Total ReferrerProfiles: {total}")

    # Fix each profile
    fixed = 0
    for profile in all_profiles:
        current_advisors = set(profile.advisors.all())
        needed_advisors = {jiri, michaela}

        if current_advisors != needed_advisors:
            profile.advisors.set(needed_advisors)
            fixed += 1
            print(f"  Fixed advisors for: {profile.user.username}")

    print(f"✓ Fixed {fixed} profiles (total: {total})")


def reverse_fix(apps, schema_editor):
    """This migration cannot be reversed"""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0012_import_production_users'),
    ]

    operations = [
        migrations.RunPython(fix_advisors, reverse_fix),
    ]
