import secrets
from typing import cast

from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.models import User as UserType
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

from .docs import (
    csrf_token_view,
    current_user_view,
    github_authorization_view,
    github_callback_view,
    invite_create_view,
    invite_list_view,
    invite_validate_view,
    login_view,
    logout_view,
    mfa_disable_view,
    mfa_setup_confirm_view,
    mfa_setup_view,
    mfa_verify_view,
    password_change_view,
    password_forgot_view,
    password_reset_view,
    register_view,
)
from .serializers import (
    CreateInviteSerializer,
    GitHubCallbackSerializer,
    LoginSerializer,
    MemberInviteSerializer,
    MfaCodeSerializer,
    MfaDisableSerializer,
    PasswordChangeSerializer,
    PasswordForgotSerializer,
    PasswordResetSerializer,
    RegisterSerializer,
    UserSerializer,
    UserUpdateSerializer,
)
from .services import (
    InviteRequiredError,
    build_github_authorization_url,
    create_member_invite,
    exchange_github_code,
    fetch_github_primary_email,
    fetch_github_user,
    generate_mfa_secret,
    get_mfa_provisioning_uri,
    get_or_create_user_from_github,
    get_user_profile,
    get_valid_invite,
    github_oauth_configured,
    send_member_invite_email,
    send_password_reset_email,
    validate_password_reset_token,
    verify_mfa_code,
)

User = get_user_model()

PENDING_MFA_SESSION_KEY = "pending_mfa_user_id"
GITHUB_OAUTH_STATE_SESSION_KEY = "github_oauth_state"


def _login_response(request, user: UserType) -> Response:
    profile = get_user_profile(user)
    if profile.mfa_enabled:
        request.session[PENDING_MFA_SESSION_KEY] = user.pk
        return Response({"detail": "MFA required.", "mfa_required": True}, status=status.HTTP_200_OK)

    login(request, user)
    return Response(UserSerializer(user).data)


@csrf_token_view
class CsrfTokenView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request) -> Response:
        return Response({"csrfToken": get_token(request)})


@method_decorator(csrf_exempt, name="dispatch")
@register_view
class RegisterView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request) -> Response:
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        login(request, user)
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


@invite_create_view
class InviteCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request) -> Response:
        serializer = CreateInviteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        invite = create_member_invite(request.user, serializer.validated_data["email"])
        send_member_invite_email(invite)

        signup_url = f"{settings.FRONTEND_URL}/register?invite={invite.token}"
        return Response(
            {
                "id": invite.pk,
                "email": invite.email,
                "token": invite.token,
                "expires_at": invite.expires_at,
                "signup_url": signup_url,
            },
            status=status.HTTP_201_CREATED,
        )


@invite_list_view
class InviteListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request) -> Response:
        from .models import MemberInvite

        invites = MemberInvite.objects.filter(invited_by=request.user).order_by("-created_at")
        return Response(MemberInviteSerializer(invites, many=True).data)


@invite_validate_view
class InviteValidateView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request) -> Response:
        token = request.query_params.get("token", "").strip()
        if not token:
            return Response({"valid": False}, status=status.HTTP_400_BAD_REQUEST)

        invite = get_valid_invite(token)
        if invite is None:
            return Response({"valid": False})

        return Response(
            {
                "valid": True,
                "email": invite.email,
                "expires_at": invite.expires_at,
            }
        )


@method_decorator(csrf_exempt, name="dispatch")
@login_view
class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request) -> Response:
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = authenticate(
            request,
            username=serializer.validated_data["username"],
            password=serializer.validated_data["password"],
        )
        if user is None:
            return Response({"detail": "Invalid credentials."}, status=status.HTTP_400_BAD_REQUEST)

        return _login_response(request, cast(UserType, user))


@logout_view
class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request) -> Response:
        logout(request)
        return Response({"detail": "Logged out."})


@current_user_view
class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request) -> Response:
        return Response(UserSerializer(request.user).data)

    def patch(self, request) -> Response:
        serializer = UserUpdateSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(UserSerializer(request.user).data)


@password_change_view
class PasswordChangeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request) -> Response:
        serializer = PasswordChangeSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": "Password changed successfully."})


@method_decorator(csrf_exempt, name="dispatch")
@password_forgot_view
class PasswordForgotView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request) -> Response:
        serializer = PasswordForgotSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = User.objects.filter(email__iexact=serializer.validated_data["email"]).first()
        if user is not None and getattr(user, "email", ""):
            send_password_reset_email(cast(UserType, user))

        return Response({"detail": "If an account exists for this email, a reset link has been sent."})


@method_decorator(csrf_exempt, name="dispatch")
@password_reset_view
class PasswordResetView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request) -> Response:
        serializer = PasswordResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = validate_password_reset_token(
            serializer.validated_data["uid"],
            serializer.validated_data["token"],
        )
        if user is None:
            return Response({"detail": "Invalid or expired reset token."}, status=status.HTTP_400_BAD_REQUEST)

        from django.contrib.auth.password_validation import validate_password

        validate_password(serializer.validated_data["new_password"], user=user)
        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password"])
        return Response({"detail": "Password reset successfully."})


@mfa_setup_view
class MfaSetupView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request) -> Response:
        profile = get_user_profile(request.user)
        if profile.mfa_enabled:
            return Response({"detail": "MFA is already enabled."}, status=status.HTTP_400_BAD_REQUEST)

        secret = generate_mfa_secret()
        profile.mfa_secret = secret
        profile.save(update_fields=["mfa_secret"])

        return Response(
            {
                "secret": secret,
                "provisioning_uri": get_mfa_provisioning_uri(request.user, secret),
            }
        )


@mfa_setup_confirm_view
class MfaSetupConfirmView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request) -> Response:
        serializer = MfaCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        profile = get_user_profile(request.user)
        if not profile.mfa_secret:
            return Response({"detail": "Start MFA setup first."}, status=status.HTTP_400_BAD_REQUEST)

        if not verify_mfa_code(profile.mfa_secret, serializer.validated_data["code"]):
            return Response({"detail": "Invalid MFA code."}, status=status.HTTP_400_BAD_REQUEST)

        profile.mfa_enabled = True
        profile.save(update_fields=["mfa_enabled"])
        return Response({"detail": "MFA enabled successfully."})


@method_decorator(csrf_exempt, name="dispatch")
@mfa_verify_view
class MfaVerifyView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request) -> Response:
        serializer = MfaCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        pending_user_id = request.session.get(PENDING_MFA_SESSION_KEY)
        if not pending_user_id:
            return Response({"detail": "No pending MFA login."}, status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.filter(pk=pending_user_id).first()
        if user is None:
            return Response({"detail": "No pending MFA login."}, status=status.HTTP_400_BAD_REQUEST)

        profile = get_user_profile(cast(UserType, user))
        if not verify_mfa_code(profile.mfa_secret, serializer.validated_data["code"]):
            return Response({"detail": "Invalid MFA code."}, status=status.HTTP_400_BAD_REQUEST)

        del request.session[PENDING_MFA_SESSION_KEY]
        login(request, user)
        return Response(UserSerializer(user).data)


@mfa_disable_view
class MfaDisableView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request) -> Response:
        serializer = MfaDisableSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if not request.user.check_password(serializer.validated_data["password"]):
            return Response({"detail": "Invalid password."}, status=status.HTTP_400_BAD_REQUEST)

        profile = get_user_profile(request.user)
        if not verify_mfa_code(profile.mfa_secret, serializer.validated_data["code"]):
            return Response({"detail": "Invalid MFA code."}, status=status.HTTP_400_BAD_REQUEST)

        profile.mfa_enabled = False
        profile.mfa_secret = ""
        profile.save(update_fields=["mfa_enabled", "mfa_secret"])
        return Response({"detail": "MFA disabled successfully."})


@github_authorization_view
class GitHubAuthorizationView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request) -> Response:
        if not github_oauth_configured():
            return Response({"detail": "GitHub OAuth is not configured."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        state = secrets.token_urlsafe(32)
        request.session[GITHUB_OAUTH_STATE_SESSION_KEY] = state
        return Response(
            {
                "authorization_url": build_github_authorization_url(state),
                "state": state,
            }
        )


@method_decorator(csrf_exempt, name="dispatch")
@github_callback_view
class GitHubCallbackView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request) -> Response:
        if not github_oauth_configured():
            return Response({"detail": "GitHub OAuth is not configured."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        serializer = GitHubCallbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        expected_state = request.session.get(GITHUB_OAUTH_STATE_SESSION_KEY)
        received_state = serializer.validated_data.get("state")
        if expected_state and received_state and expected_state != received_state:
            return Response({"detail": "Invalid OAuth state."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            token_data = exchange_github_code(serializer.validated_data["code"])
            access_token = token_data.get("access_token")
            if not access_token:
                return Response({"detail": "GitHub authentication failed."}, status=status.HTTP_400_BAD_REQUEST)

            github_user = fetch_github_user(access_token)
            email = fetch_github_primary_email(access_token) or github_user.get("email")
            user = get_or_create_user_from_github(github_user, email)
        except InviteRequiredError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except Exception:
            return Response({"detail": "GitHub authentication failed."}, status=status.HTTP_400_BAD_REQUEST)
        finally:
            request.session.pop(GITHUB_OAUTH_STATE_SESSION_KEY, None)

        return _login_response(request, cast(UserType, user))
