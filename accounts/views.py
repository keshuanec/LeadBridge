from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth import update_session_auth_hash
from django.contrib import messages
from django.shortcuts import render, redirect
from django import forms
from django.http import HttpResponseForbidden
from accounts.models import BrandingSettings, User


class UserProfileForm(forms.Form):
    first_name = forms.CharField(label="Jméno", max_length=150, required=False)
    last_name = forms.CharField(label="Příjmení", max_length=150, required=False)
    email = forms.EmailField(label="E-mail", required=False)
    phone = forms.CharField(label="Telefon", max_length=20, required=False)


@login_required
def user_settings(request):
    user = request.user

    # Zjistíme, jestli má uživatel ReferrerProfile pro odkaz na detail
    referrer_profile = getattr(user, "referrer_profile", None)

    context = {
        "user": user,
        "referrer_profile": referrer_profile,
    }

    return render(request, "accounts/user_settings.html", context)


@login_required
def edit_profile(request):
    user = request.user

    if request.method == "POST":
        form = UserProfileForm(request.POST)
        if form.is_valid():
            user.first_name = form.cleaned_data["first_name"]
            user.last_name = form.cleaned_data["last_name"]
            user.email = form.cleaned_data["email"]
            user.phone = form.cleaned_data.get("phone", "")
            user.save()
            messages.success(request, "Profil byl úspěšně aktualizován.")

            # Přesměruj zpět na správný detail podle role
            from accounts.models import User
            if user.role == User.Role.REFERRER and hasattr(user, 'referrer_profile'):
                return redirect('referrer_detail', pk=user.referrer_profile.pk)
            elif user.role == User.Role.ADVISOR:
                return redirect('advisor_detail', pk=user.pk)
            else:
                return redirect('user_settings')
    else:
        form = UserProfileForm(initial={
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "phone": user.phone,
        })

    return render(request, "accounts/edit_profile.html", {"form": form, "user": user})


@login_required
def change_password(request):
    user = request.user

    if request.method == "POST":
        form = PasswordChangeForm(user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)  # Aby nebyl uživatel odhlášen
            messages.success(request, "Heslo bylo úspěšně změněno.")

            # Přesměruj zpět na správný detail podle role
            from accounts.models import User
            if user.role == User.Role.REFERRER and hasattr(user, 'referrer_profile'):
                return redirect('referrer_detail', pk=user.referrer_profile.pk)
            elif user.role == User.Role.ADVISOR:
                return redirect('advisor_detail', pk=user.pk)
            else:
                return redirect('user_settings')
    else:
        form = PasswordChangeForm(user)

    return render(request, "accounts/change_password.html", {"form": form, "user": user})


class BrandingSettingsForm(forms.ModelForm):
    """Formulář pro nastavení brandingu"""
    class Meta:
        model = BrandingSettings
        fields = ['navbar_color', 'navbar_text_color', 'logo']
        widgets = {
            'navbar_color': forms.TextInput(attrs={
                'type': 'color',
                'class': 'color-picker',
            }),
            'navbar_text_color': forms.TextInput(attrs={
                'type': 'color',
                'class': 'color-picker',
            }),
        }


@login_required
def branding_settings(request):
    """
    Zobrazí a upraví nastavení brandingu.
    Pouze pro advisora s administrativním přístupem.
    """
    user = request.user

    # Kontrola oprávnění
    if user.role != User.Role.ADVISOR or not user.has_admin_access:
        return HttpResponseForbidden("Nemáte oprávnění k úpravě nastavení brandingu.")

    # Získat nebo vytvořit BrandingSettings pro tohoto uživatele
    branding, created = BrandingSettings.objects.get_or_create(owner=user)

    if request.method == "POST":
        form = BrandingSettingsForm(request.POST, request.FILES, instance=branding)
        if form.is_valid():
            form.save()
            messages.success(request, "Nastavení brandingu bylo úspěšně uloženo.")
            return redirect('branding_settings')
    else:
        form = BrandingSettingsForm(instance=branding)

    return render(request, "accounts/branding_settings.html", {
        "form": form,
        "user": user,
        "branding": branding,
    })
