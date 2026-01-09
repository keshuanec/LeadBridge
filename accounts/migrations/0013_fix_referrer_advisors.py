# Generated migration to fix advisor assignments
from django.db import migrations


def fix_advisors(apps, schema_editor):
    """Ensure all ReferrerProfiles have correct advisors assigned"""
    User = apps.get_model('accounts', 'User')
    ReferrerProfile = apps.get_model('accounts', 'ReferrerProfile')

    # Find CORRECT advisors by production usernames
    try:
        jiri = User.objects.get(username='jirkahavlas')
        michaela = User.objects.get(username='michaela.kubinova@housevip.cz')
    except User.DoesNotExist as e:
        print(f"SKIP: Could not find advisors - {e}")
        return

    print(f"Found advisors: {jiri.get_full_name()} ({jiri.username}), {michaela.get_full_name()} ({michaela.username})")

    # Delete duplicate advisors from import (poradce1, poradce2)
    duplicates_deleted = 0
    for username in ['poradce1', 'poradce2']:
        try:
            duplicate = User.objects.get(username=username)
            # Safety check - only delete if no leads are associated
            if not duplicate.leads_assigned.exists():
                duplicate_name = duplicate.get_full_name()
                duplicate.delete()
                duplicates_deleted += 1
                print(f"  Deleted duplicate advisor: {duplicate_name} ({username})")
            else:
                print(f"  SKIP: {username} has associated leads, not deleting")
        except User.DoesNotExist:
            pass

    if duplicates_deleted > 0:
        print(f"✓ Deleted {duplicates_deleted} duplicate advisors")

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
