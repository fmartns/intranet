import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


class UserProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        related_name="profile",
        on_delete=models.CASCADE,
    )
    mfa_enabled = models.BooleanField(default=False)
    mfa_secret = models.CharField(max_length=32, blank=True)

    def __str__(self) -> str:
        return f"Profile for {self.user.username}"


class SocialAccount(models.Model):
    PROVIDER_GITHUB = "github"
    PROVIDER_CHOICES = [(PROVIDER_GITHUB, "GitHub")]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="social_accounts",
        on_delete=models.CASCADE,
    )
    provider = models.CharField(max_length=32, choices=PROVIDER_CHOICES)
    provider_user_id = models.CharField(max_length=255)
    extra_data = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "provider_user_id"],
                name="unique_social_account",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.provider}:{self.provider_user_id}"


class MemberInvite(models.Model):
    token = models.CharField(max_length=64, unique=True, editable=False)
    email = models.EmailField()
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="sent_invites",
        on_delete=models.CASCADE,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="accepted_invites",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )

    class Meta:
        indexes = [
            models.Index(fields=["email", "accepted_at"]),
            models.Index(fields=["token"]),
        ]

    def __str__(self) -> str:
        return f"Invite for {self.email}"

    @classmethod
    def generate_token(cls) -> str:
        return secrets.token_urlsafe(32)

    @classmethod
    def default_expires_at(cls):
        return timezone.now() + timedelta(days=settings.INVITE_EXPIRY_DAYS)

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    @property
    def is_accepted(self) -> bool:
        return self.accepted_at is not None

    @property
    def is_valid(self) -> bool:
        return not self.is_accepted and not self.is_expired
