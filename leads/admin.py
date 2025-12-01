from django.contrib import admin
from .models import Lead


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = (
        "client_name",
        "referrer",
        "advisor",
        "communication_status",
        "commission_status",
        "created_at",
    )
    list_filter = ("communication_status", "commission_status", "created_at")
    search_fields = ("client_name", "client_phone", "client_email")