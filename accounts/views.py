from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth import update_session_auth_hash
from django.contrib import messages
from django.shortcuts import render, redirect
from django import forms


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
            return redirect("user_settings")
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
    if request.method == "POST":
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)  # Aby nebyl uživatel odhlášen
            messages.success(request, "Heslo bylo úspěšně změněno.")
            return redirect("user_settings")
    else:
        form = PasswordChangeForm(request.user)

    return render(request, "accounts/change_password.html", {"form": form, "user": request.user})
