from __future__ import annotations

from allauth.account.decorators import secure_admin_login
from django.conf import settings
from django.contrib import admin
from django.contrib.auth import admin as auth_admin
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin
from unfold.admin import StackedInline

from .forms import UserAdminChangeForm
from .forms import UserAdminCreationForm
from .models import Profile
from .models import User

if settings.DJANGO_ADMIN_FORCE_ALLAUTH:
    # Force the `admin` sign in process to go through the `django-allauth` workflow:
    # https://docs.allauth.org/en/latest/common/admin.html#admin
    admin.autodiscover()
    admin.site.login = secure_admin_login(admin.site.login)  # type: ignore[method-assign]


class ProfileInline(StackedInline):
    model = Profile
    can_delete = False
    fk_name = "user"


@admin.register(User)
class UserAdmin(auth_admin.UserAdmin, ModelAdmin):
    form = UserAdminChangeForm
    add_form = UserAdminCreationForm
    inlines = [ProfileInline]

    def get_inlines(self, request, obj=None):
        if obj is None:
            return []
        return super().get_inlines(request, obj)
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (_("Personal info"), {"fields": ("name",)}),
        (
            _("Permissions"),
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
    )
    list_display = ["email", "name", "is_superuser"]
    search_fields = ["name", "email"]
    ordering = ["id"]
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2"),
            },
        ),
    )


@admin.register(Profile)
class ProfileAdmin(ModelAdmin):
    list_display = [
        "user",
        "full_name",
        "company_name",
        "default_currency",
        "default_tax_rate",
    ]
    search_fields = ["user__email", "full_name", "company_name"]
