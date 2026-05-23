import pyotp
import requests
from typing import cast
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import User as UserType
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from .models import MemberInvite, SocialAccount, UserProfile

User = get_user_model()


class InviteRequiredError(Exception):
    """Raised when a new account requires a valid member invite."""


def registration_open_without_invite() -> bool:
    return not User.objects.exists()


def get_user_profile(user: UserType) -> UserProfile:
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile


def generate_mfa_secret() -> str:
    return pyotp.random_base32()


def get_mfa_provisioning_uri(user: UserType, secret: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(
        name=user.email or user.username,
        issuer_name=settings.MFA_ISSUER_NAME,
    )


def verify_mfa_code(secret: str, code: str) -> bool:
    if not secret or not code:
        return False
    return pyotp.TOTP(secret).verify(code, valid_window=1)


def send_password_reset_email(user: UserType) -> None:
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    reset_url = f"{settings.FRONTEND_URL}/reset-password?uid={uid}&token={token}"

    send_mail(
        subject="Password reset",
        message=(
            f"Use the link below to reset your password:\n\n{reset_url}\n\n"
            "If you did not request this, you can ignore this email."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )


def validate_password_reset_token(uid: str, token: str) -> UserType | None:
    try:
        user_id = force_str(urlsafe_base64_decode(uid))
        user = User.objects.get(pk=user_id)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        return None

    if not default_token_generator.check_token(user, token):
        return None

    return cast(UserType, user)


def github_oauth_configured() -> bool:
    return bool(settings.GITHUB_CLIENT_ID and settings.GITHUB_CLIENT_SECRET)


def build_github_authorization_url(state: str) -> str:
    params = {
        "client_id": settings.GITHUB_CLIENT_ID,
        "redirect_uri": settings.GITHUB_CALLBACK_URL,
        "scope": "read:user user:email",
        "state": state,
    }
    return f"https://github.com/login/oauth/authorize?{urlencode(params)}"


def exchange_github_code(code: str) -> dict:
    response = requests.post(
        "https://github.com/login/oauth/access_token",
        headers={"Accept": "application/json"},
        data={
            "client_id": settings.GITHUB_CLIENT_ID,
            "client_secret": settings.GITHUB_CLIENT_SECRET,
            "code": code,
            "redirect_uri": settings.GITHUB_CALLBACK_URL,
        },
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def fetch_github_user(access_token: str) -> dict:
    response = requests.get(
        "https://api.github.com/user",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        },
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def fetch_github_primary_email(access_token: str) -> str | None:
    response = requests.get(
        "https://api.github.com/user/emails",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        },
        timeout=10,
    )
    response.raise_for_status()
    emails = response.json()

    for email_data in emails:
        if email_data.get("primary") and email_data.get("verified"):
            return email_data["email"]

    for email_data in emails:
        if email_data.get("verified"):
            return email_data["email"]

    return None


def _unique_username(base_username: str) -> str:
    username = base_username[:150]
    if not User.objects.filter(username=username).exists():
        return username

    suffix = 1
    while User.objects.filter(username=f"{username}{suffix}").exists():
        suffix += 1
    return f"{username}{suffix}"


def get_valid_invite(token: str) -> MemberInvite | None:
    invite = MemberInvite.objects.filter(token=token).first()
    if invite is None or not invite.is_valid:
        return None
    return invite


def get_valid_invite_for_email(token: str, email: str) -> MemberInvite | None:
    invite = get_valid_invite(token)
    if invite is None or invite.email.lower() != email.lower():
        return None
    return invite


def get_pending_invite_for_email(email: str) -> MemberInvite | None:
    return MemberInvite.objects.filter(
        email__iexact=email,
        accepted_at__isnull=True,
        expires_at__gt=timezone.now(),
    ).first()


def create_member_invite(invited_by: UserType, email: str) -> MemberInvite:
    MemberInvite.objects.filter(
        email__iexact=email,
        accepted_at__isnull=True,
        expires_at__gt=timezone.now(),
    ).delete()

    return MemberInvite.objects.create(
        token=MemberInvite.generate_token(),
        email=email,
        invited_by=invited_by,
        expires_at=MemberInvite.default_expires_at(),
    )


def send_member_invite_email(invite: MemberInvite) -> None:
    signup_url = f"{settings.FRONTEND_URL}/register?invite={invite.token}"
    send_mail(
        subject="You have been invited to join the intranet",
        message=(
            f"You were invited to join the platform.\n\n"
            f"Use this link to create your account:\n{signup_url}\n\n"
            f"This invite expires on {invite.expires_at:%Y-%m-%d %H:%M UTC}."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[invite.email],
        fail_silently=False,
    )


def consume_invite(invite: MemberInvite, user: UserType) -> None:
    invite.accepted_at = timezone.now()
    invite.accepted_by = user
    invite.save(update_fields=["accepted_at", "accepted_by"])


def get_or_create_user_from_github(github_user: dict, email: str | None) -> UserType:
    provider_user_id = str(github_user["id"])

    social_account = SocialAccount.objects.filter(
        provider=SocialAccount.PROVIDER_GITHUB,
        provider_user_id=provider_user_id,
    ).select_related("user").first()
    if social_account:
        social_account.extra_data = github_user
        social_account.save(update_fields=["extra_data"])
        return cast(UserType, social_account.user)

    if email:
        existing_user = User.objects.filter(email__iexact=email).first()
        if existing_user is not None:
            resolved_user = cast(UserType, existing_user)
            SocialAccount.objects.create(
                user=resolved_user,
                provider=SocialAccount.PROVIDER_GITHUB,
                provider_user_id=provider_user_id,
                extra_data=github_user,
            )
            get_user_profile(resolved_user)
            return resolved_user

    pending_invite: MemberInvite | None = None
    if not registration_open_without_invite():
        if not email:
            raise InviteRequiredError("An invite is required to join this platform.")
        pending_invite = get_pending_invite_for_email(email)
        if pending_invite is None:
            raise InviteRequiredError("An invite is required to join this platform.")

    username = _unique_username(github_user.get("login") or f"github_{provider_user_id}")
    created_user = User(username=username, email=email or "")
    created_user.set_unusable_password()
    created_user.save()
    resolved_user = cast(UserType, created_user)
    get_user_profile(resolved_user)

    SocialAccount.objects.create(
        user=resolved_user,
        provider=SocialAccount.PROVIDER_GITHUB,
        provider_user_id=provider_user_id,
        extra_data=github_user,
    )
    if pending_invite is not None:
        consume_invite(pending_invite, resolved_user)
    return resolved_user
