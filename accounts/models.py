from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models

phone_validator = RegexValidator(
    regex=r"^\+?[0-9\s\-]{7,15}$",
    message="Enter a valid phone number (7-15 digits, optional leading +).",
)


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Admin"
        MANAGER = "MANAGER", "Manager"
        CASHIER = "CASHIER", "Cashier"
        STAFF = "STAFF", "Staff"

    email = models.EmailField("email address", unique=True)
    phone = models.CharField(max_length=20, blank=True, validators=[phone_validator])
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.STAFF)
    updated_at = models.DateTimeField(auto_now=True)

    REQUIRED_FIELDS = ["email"]

    class Meta:
        ordering = ["id"]
        indexes = [models.Index(fields=["role"], name="user_role_idx")]

    def save(self, *args, **kwargs):
        if self.email:
            self.email = self.email.strip().lower()
        if self.is_superuser:
            # Superusers are always full administrators.
            self.role = self.Role.ADMIN
            self.is_staff = True
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.username} ({self.role})"
