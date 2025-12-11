from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User, ReferrerProfile, Office, ManagerProfile


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = BaseUserAdmin.fieldsets + (
        ("LeadBridge role", {"fields": ("role",)}),
    )

    # Tohle je formulář pro VYTVOŘENÍ uživatele
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ("LeadBridge role", {
            "classes": ("wide",),
            "fields": ("role",),
        }),
    )

    list_display = ("username", "email", "first_name", "last_name", "role", "is_staff")
    list_filter = ("role", "is_staff", "is_superuser", "is_active")


@admin.register(ReferrerProfile)
class ReferrerProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "manager", "get_advisors")
    list_filter = ("manager",)
    search_fields = ("user__username", "user__first_name", "user__last_name")
    filter_horizontal = ("advisors",)

    def get_advisors(self, obj):
        return ", ".join([advisor.username for advisor in obj.advisors.all()]) or "—"
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