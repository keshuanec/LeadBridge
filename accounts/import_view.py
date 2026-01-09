"""
One-time view for importing users in production.
Visit /admin/import-users/ to run the import.
"""
from django.http import HttpResponse
from django.contrib.admin.views.decorators import staff_member_required
from django.db import transaction
from accounts.models import User, ReferrerProfile
import json
import os
import traceback


@staff_member_required
def import_users_view(request):
    """Import users from JSON export"""
    try:
        # Path to the exported data
        json_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'temp_import', 'users_export.json')

        with open(json_path, 'r') as f:
            data = json.load(f)

        created_users = 0
        updated_users = 0
        created_profiles = 0

        with transaction.atomic():
            # Import users
            for item in data:
                if item['model'] == 'accounts.user':
                    fields = item['fields']
                    username = fields['username']

                    user, created = User.objects.update_or_create(
                        username=username,
                        defaults={
                            'first_name': fields['first_name'],
                            'last_name': fields['last_name'],
                            'email': fields['email'],
                            'phone': fields.get('phone', ''),
                            'role': fields['role'],
                            'commission_total_per_million': fields['commission_total_per_million'],
                            'commission_referrer_pct': fields['commission_referrer_pct'],
                            'commission_manager_pct': fields['commission_manager_pct'],
                            'commission_office_pct': fields['commission_office_pct'],
                            'is_staff': fields['is_staff'],
                            'is_superuser': fields['is_superuser'],
                            'is_active': fields['is_active'],
                        }
                    )

                    # Set password from export
                    user.password = fields['password']
                    user.save()

                    if created:
                        created_users += 1
                    else:
                        updated_users += 1

            # Import ReferrerProfiles
            for item in data:
                if item['model'] == 'accounts.referrerprofile':
                    fields = item['fields']
                    user = User.objects.get(username=fields['user'][0])  # natural key

                    manager = None
                    if fields.get('manager'):
                        try:
                            manager = User.objects.get(username=fields['manager'][0])
                        except User.DoesNotExist:
                            pass

                    profile, created = ReferrerProfile.objects.update_or_create(
                        user=user,
                        defaults={'manager': manager}
                    )

                    # Add advisors
                    if fields.get('advisors'):
                        for advisor_key in fields['advisors']:
                            try:
                                advisor = User.objects.get(username=advisor_key[0])
                                profile.advisors.add(advisor)
                            except User.DoesNotExist:
                                pass

                    if created:
                        created_profiles += 1

        return HttpResponse(f"""
            <html>
            <head><title>Import Successful</title></head>
            <body style="font-family: sans-serif; padding: 40px;">
                <h1 style="color: green;">✓ Import Successful!</h1>
                <ul>
                    <li>Created users: {created_users}</li>
                    <li>Updated users: {updated_users}</li>
                    <li>Created profiles: {created_profiles}</li>
                </ul>
                <p><a href="/admin/">Back to Admin</a></p>
            </body>
            </html>
        """)

    except Exception as e:
        error_traceback = traceback.format_exc()
        return HttpResponse(f"""
            <html>
            <head><title>Import Failed</title></head>
            <body style="font-family: sans-serif; padding: 40px;">
                <h1 style="color: red;">✗ Import Failed</h1>
                <p><strong>Error:</strong> {str(e)}</p>
                <pre>{error_traceback}</pre>
                <p><a href="/admin/">Back to Admin</a></p>
            </body>
            </html>
        """, status=500)
