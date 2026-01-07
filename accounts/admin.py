from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User, ReferrerProfile, Office, ManagerProfile


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = BaseUserAdmin.fieldsets + (
        ("LeadBridge", {"fields": ("role", "phone", "has_admin_access")}),
        ("Provize", {
            "fields": (
                "commission_total_per_million",
                "commission_referrer_pct",
                "commission_manager_pct",
                "commission_office_pct",
            )
        }),
    )

    # Tohle je formulář pro VYTVOŘENÍ uživatele
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ("Osobní údaje", {
            "classes": ("wide",),
            "fields": ("first_name", "last_name", "email"),
        }),
        ("LeadBridge", {
            "classes": ("wide",),
            "fields": ("role", "phone", "has_admin_access"),
        }),
        ("Provize", {
            "classes": ("wide",),
            "fields": (
                "commission_total_per_million",
                "commission_referrer_pct",
                "commission_manager_pct",
                "commission_office_pct",
            ),
        }),
    )

    list_display = ("get_full_name", "email", "phone", "role", "has_admin_access", "commission_referrer_pct", "is_staff")
    list_filter = ("role", "has_admin_access", "is_staff", "is_superuser", "is_active")

    def get_full_name(self, obj):
        return obj.get_full_name()
    get_full_name.short_description = "Jméno"
    get_full_name.admin_order_field = "first_name"


@admin.register(ReferrerProfile)
class ReferrerProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "manager", "get_advisors")
    list_filter = ("manager",)
    search_fields = ("user__username", "user__first_name", "user__last_name")
    filter_horizontal = ("advisors",)

    def get_advisors(self, obj):
        return ", ".join([advisor.get_full_name() for advisor in obj.advisors.all()]) or "—"
    get_advisors.short_description = "Poradci"

class ManagerProfileInline(admin.TabularInline):
    model = ManagerProfile
    extra = 0
    autocomplete_fields = ["user"]
    show_change_link = True

@admin.register(Office)
class OfficeAdmin(admin.ModelAdmin):
    list_display = ("name", "owner")
    search_fields = ("name",)
    autocomplete_fields = ["owner"]
    inlines = [ManagerProfileInline]

@admin.register(ManagerProfile)
class ManagerProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "office")
    list_filter = ("office",)
    search_fields = ("user__username", "user__first_name", "user__last_name")
    autocomplete_fields = ["user", "office"]