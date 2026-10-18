from typing import Any, ClassVar

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models

from commandr.core.ids import uuid7


class UserManager(BaseUserManager["User"]):
    use_in_migrations = True

    def _create(self, email: str, password: str | None, **extra: Any) -> "User":
        if not email:
            raise ValueError("An email address is required.")
        user = self.model(email=self.normalize_email(email).lower(), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra: Any) -> "User":
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create(email, password, **extra)

    def create_superuser(self, email: str, password: str | None = None, **extra: Any) -> "User":
        extra["is_staff"] = True
        extra["is_superuser"] = True
        return self._create(email, password, **extra)


class User(AbstractUser):
    """A person. Signs in with their email; belongs to organizations via Membership.

    Platform staff (`is_staff`) reach the Django admin only; they get no access
    to customer data through it beyond what the admin registrations expose.
    """

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    username = None  # type: ignore[assignment]
    email = models.EmailField("email address", unique=True)
    display_name = models.CharField(max_length=120, blank=True)
    language = models.CharField(max_length=8, default="en")

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: ClassVar[list[str]] = []

    objects = UserManager()  # type: ignore[assignment, misc]

    def __str__(self) -> str:
        return self.email
