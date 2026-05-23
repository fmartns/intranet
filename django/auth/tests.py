import pyotp
import pytest
from django.contrib.auth.models import User as UserType
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APIClient

from auth.services import create_member_invite, get_user_profile


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def user(db) -> UserType:
    created = UserType.objects.create_user(
        username="testuser",
        email="test@example.com",
        password="testpass123",
    )
    get_user_profile(created)
    return created


@pytest.fixture
def invite(db, user: UserType):
    return create_member_invite(user, "invited@example.com")


@pytest.mark.django_db
class TestRegisterView:
    def test_bootstrap_register_without_invite(self, api_client: APIClient) -> None:
        response = api_client.post(
            "/auth/register/",
            {
                "username": "firstuser",
                "email": "first@example.com",
                "password": "securepass123",
                "password_confirm": "securepass123",
            },
            format="json",
        )

        assert response.status_code == 201
        assert response.data["username"] == "firstuser"

    def test_register_requires_invite_after_bootstrap(self, api_client: APIClient, user: UserType) -> None:
        response = api_client.post(
            "/auth/register/",
            {
                "username": "newuser",
                "email": "new@example.com",
                "password": "securepass123",
                "password_confirm": "securepass123",
            },
            format="json",
        )

        assert response.status_code == 400
        assert "invite_token" in response.data

    def test_register_with_valid_invite(self, api_client: APIClient, user: UserType, invite) -> None:
        response = api_client.post(
            "/auth/register/",
            {
                "invite_token": invite.token,
                "username": "newuser",
                "email": invite.email,
                "password": "securepass123",
                "password_confirm": "securepass123",
            },
            format="json",
        )

        assert response.status_code == 201
        assert response.data["username"] == "newuser"
        invite.refresh_from_db()
        assert invite.accepted_at is not None


@pytest.mark.django_db
class TestInviteViews:
    def test_create_invite_requires_authentication(self, api_client: APIClient) -> None:
        response = api_client.post(
            "/auth/invites/create/",
            {"email": "someone@example.com"},
            format="json",
        )

        assert response.status_code == 403

    def test_member_can_create_invite(self, api_client: APIClient, user: UserType) -> None:
        api_client.force_authenticate(user=user)

        response = api_client.post(
            "/auth/invites/create/",
            {"email": "invited@example.com"},
            format="json",
        )

        assert response.status_code == 201
        assert response.data["email"] == "invited@example.com"
        assert "token" in response.data
        assert len(mail.outbox) == 1

    def test_validate_invite(self, api_client: APIClient, user: UserType, invite) -> None:
        response = api_client.get(f"/auth/invites/validate/?token={invite.token}")

        assert response.status_code == 200
        assert response.data["valid"] is True
        assert response.data["email"] == invite.email

    def test_list_sent_invites(self, api_client: APIClient, user: UserType, invite) -> None:
        api_client.force_authenticate(user=user)

        response = api_client.get("/auth/invites/")

        assert response.status_code == 200
        assert len(response.data) == 1
        assert response.data[0]["email"] == invite.email


@pytest.mark.django_db
class TestLoginView:
    def test_login_success(self, api_client: APIClient, user: UserType) -> None:
        response = api_client.post(
            "/auth/login/",
            {"username": "testuser", "password": "testpass123"},
            format="json",
        )

        assert response.status_code == 200
        assert response.data["username"] == "testuser"
        assert "_auth_user_id" in api_client.session

    def test_login_requires_mfa(self, api_client: APIClient, user: UserType) -> None:
        profile = get_user_profile(user)
        profile.mfa_secret = pyotp.random_base32()
        profile.mfa_enabled = True
        profile.save()

        response = api_client.post(
            "/auth/login/",
            {"username": "testuser", "password": "testpass123"},
            format="json",
        )

        assert response.status_code == 200
        assert response.data["mfa_required"] is True
        assert "_auth_user_id" not in api_client.session


@pytest.mark.django_db
class TestPasswordForgotAndReset:
    def test_forgot_password_sends_email(self, api_client: APIClient, user: UserType) -> None:
        response = api_client.post(
            "/auth/password/forgot/",
            {"email": "test@example.com"},
            format="json",
        )

        assert response.status_code == 200
        assert len(mail.outbox) == 1
        assert user.email in mail.outbox[0].to

    def test_reset_password_with_valid_token(self, api_client: APIClient, user: UserType) -> None:
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)

        response = api_client.post(
            "/auth/password/reset/",
            {
                "uid": uid,
                "token": token,
                "new_password": "newsecurepass123",
                "new_password_confirm": "newsecurepass123",
            },
            format="json",
        )

        assert response.status_code == 200
        user.refresh_from_db()
        assert user.check_password("newsecurepass123")


@pytest.mark.django_db
class TestMfaViews:
    def test_mfa_setup_and_confirm(self, api_client: APIClient, user: UserType) -> None:
        api_client.force_authenticate(user=user)

        setup_response = api_client.post("/auth/mfa/setup/")
        assert setup_response.status_code == 200

        secret = setup_response.data["secret"]
        code = pyotp.TOTP(secret).now()

        confirm_response = api_client.post("/auth/mfa/setup/confirm/", {"code": code}, format="json")
        assert confirm_response.status_code == 200

        profile = get_user_profile(user)
        assert profile.mfa_enabled is True


@pytest.mark.django_db
class TestGitHubOAuth:
    @pytest.fixture(autouse=True)
    def github_settings(self, settings):
        settings.GITHUB_CLIENT_ID = "test-client-id"
        settings.GITHUB_CLIENT_SECRET = "test-client-secret"
        settings.GITHUB_CALLBACK_URL = "http://testserver/auth/social/github/callback/"

    def test_github_callback_requires_invite_for_new_user(
        self, api_client: APIClient, user: UserType, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        auth_response = api_client.get("/auth/social/github/")
        state = auth_response.data["state"]

        monkeypatch.setattr(
            "auth.views.exchange_github_code",
            lambda code: {"access_token": "github-token"},
        )
        monkeypatch.setattr(
            "auth.views.fetch_github_user",
            lambda access_token: {"id": 99999, "login": "new-github-user", "email": "new@example.com"},
        )
        monkeypatch.setattr(
            "auth.views.fetch_github_primary_email",
            lambda access_token: "new@example.com",
        )

        response = api_client.post(
            "/auth/social/github/callback/",
            {"code": "oauth-code", "state": state},
            format="json",
        )

        assert response.status_code == 403
        assert "invite" in response.data["detail"].lower()

    def test_github_callback_with_invite(
        self, api_client: APIClient, user: UserType, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        invite = create_member_invite(user, "gh@example.com")
        auth_response = api_client.get("/auth/social/github/")
        state = auth_response.data["state"]

        monkeypatch.setattr(
            "auth.views.exchange_github_code",
            lambda code: {"access_token": "github-token"},
        )
        monkeypatch.setattr(
            "auth.views.fetch_github_user",
            lambda access_token: {"id": 12345, "login": "github-user", "email": "gh@example.com"},
        )
        monkeypatch.setattr(
            "auth.views.fetch_github_primary_email",
            lambda access_token: "gh@example.com",
        )

        response = api_client.post(
            "/auth/social/github/callback/",
            {"code": "oauth-code", "state": state},
            format="json",
        )

        assert response.status_code == 200
        assert response.data["username"] == "github-user"
        invite.refresh_from_db()
        assert invite.accepted_at is not None
