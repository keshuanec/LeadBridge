from django.contrib import admin
from .models import Lead, Deal


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

@admin.register(Deal)
class DealAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "client_name",
        "status",
        "commission_status",
        "loan_amount",
        "bank",
        "property_type",
        "created_at",
        "lead",
    )
    list_filter = ("status", "commission_status", "bank", "property_type")
    search_fields = ("client_name", "client_phone", "client_email", "lead__client_name")
    ordering = ("-created_at",)
    autocomplete_fields = ("lead",)  # funguje, pokud je lead FK/O2O