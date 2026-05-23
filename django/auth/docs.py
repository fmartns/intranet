from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
    inline_serializer,
)
from rest_framework import serializers

from .serializers import (
    CreateInviteResponseSerializer,
    CreateInviteSerializer,
    GitHubAuthorizationUrlSerializer,
    GitHubCallbackSerializer,
    InviteValidateSerializer,
    LoginSerializer,
    MemberInviteSerializer,
    MfaCodeSerializer,
    MfaDisableSerializer,
    MfaSetupResponseSerializer,
    PasswordChangeSerializer,
    PasswordForgotSerializer,
    PasswordResetSerializer,
    RegisterSerializer,
    UserSerializer,
    UserUpdateSerializer,
)

_detail_serializer = inline_serializer(
    name="AuthDetailResponse",
    fields={"detail": serializers.CharField()},
)

_error_serializer = inline_serializer(
    name="AuthErrorResponse",
    fields={"detail": serializers.CharField()},
)

_csrf_serializer = inline_serializer(
    name="CsrfTokenResponse",
    fields={"csrfToken": serializers.CharField()},
)

csrf_token_view = extend_schema_view(
    get=extend_schema(
        summary="Get CSRF token",
        description="Returns a CSRF token for session-authenticated requests.",
        responses={
            200: OpenApiResponse(
                response=_csrf_serializer,
                description="CSRF token",
                examples=[
                    OpenApiExample(
                        name="CSRF token",
                        value={"csrfToken": "abc123"},
                    ),
                ],
            ),
        },
    ),
)

register_view = extend_schema_view(
    post=extend_schema(
        summary="Register",
        description=(
            "Create a new account with a valid member invite. "
            "The first account can be created without an invite to bootstrap the platform."
        ),
        request=RegisterSerializer,
        responses={
            201: OpenApiResponse(
                response=UserSerializer,
                description="User created",
            ),
            400: OpenApiResponse(
                response=RegisterSerializer,
                description="Validation error",
            ),
        },
    ),
)

login_view = extend_schema_view(
    post=extend_schema(
        summary="Login",
        description="Authenticate with username and password. If MFA is enabled, complete login at /auth/mfa/verify/.",
        request=LoginSerializer,
        responses={
            200: OpenApiResponse(
                response=UserSerializer,
                description="Authenticated",
            ),
            400: OpenApiResponse(
                response=_error_serializer,
                description="Invalid credentials",
                examples=[
                    OpenApiExample(
                        name="Invalid credentials",
                        value={"detail": "Invalid credentials."},
                    ),
                ],
            ),
        },
    ),
)

_mfa_required_serializer = inline_serializer(
    name="MfaRequiredResponse",
    fields={
        "detail": serializers.CharField(),
        "mfa_required": serializers.BooleanField(),
    },
)

logout_view = extend_schema_view(
    post=extend_schema(
        summary="Logout",
        description="End the current session.",
        request=None,
        responses={
            200: OpenApiResponse(
                response=_detail_serializer,
                description="Logged out",
                examples=[
                    OpenApiExample(
                        name="Logged out",
                        value={"detail": "Logged out."},
                    ),
                ],
            ),
        },
    ),
)

current_user_view = extend_schema_view(
    get=extend_schema(
        summary="Current user",
        description="Return the authenticated user profile.",
        responses={
            200: OpenApiResponse(
                response=UserSerializer,
                description="Current user",
            ),
            401: OpenApiResponse(
                response=_detail_serializer,
                description="Not authenticated",
            ),
        },
    ),
    patch=extend_schema(
        summary="Update current user",
        description="Update profile fields for the authenticated user.",
        request=UserUpdateSerializer,
        responses={
            200: OpenApiResponse(
                response=UserSerializer,
                description="Updated user",
            ),
            400: OpenApiResponse(
                response=UserUpdateSerializer,
                description="Validation error",
            ),
            401: OpenApiResponse(
                response=_detail_serializer,
                description="Not authenticated",
            ),
        },
    ),
)

password_change_view = extend_schema_view(
    post=extend_schema(
        summary="Change password",
        description="Change the password for the authenticated user.",
        request=PasswordChangeSerializer,
        responses={
            200: OpenApiResponse(
                response=_detail_serializer,
                description="Password changed",
                examples=[
                    OpenApiExample(
                        name="Password changed",
                        value={"detail": "Password changed successfully."},
                    ),
                ],
            ),
            400: OpenApiResponse(
                response=PasswordChangeSerializer,
                description="Validation error",
            ),
            401: OpenApiResponse(
                response=_detail_serializer,
                description="Not authenticated",
            ),
        },
    ),
)

password_forgot_view = extend_schema_view(
    post=extend_schema(
        summary="Forgot password",
        description="Send a password reset email if the account exists.",
        request=PasswordForgotSerializer,
        responses={
            200: OpenApiResponse(response=_detail_serializer, description="Reset email queued"),
        },
    ),
)

password_reset_view = extend_schema_view(
    post=extend_schema(
        summary="Reset password",
        description="Reset password using uid and token from the reset email.",
        request=PasswordResetSerializer,
        responses={
            200: OpenApiResponse(response=_detail_serializer, description="Password reset"),
            400: OpenApiResponse(response=_error_serializer, description="Invalid token"),
        },
    ),
)

mfa_setup_view = extend_schema_view(
    post=extend_schema(
        summary="Setup MFA",
        description="Generate a TOTP secret and provisioning URI for an authenticator app.",
        request=None,
        responses={
            200: OpenApiResponse(response=MfaSetupResponseSerializer, description="MFA setup data"),
            400: OpenApiResponse(response=_detail_serializer, description="MFA already enabled"),
        },
    ),
)

mfa_setup_confirm_view = extend_schema_view(
    post=extend_schema(
        summary="Confirm MFA setup",
        description="Verify TOTP code and enable MFA.",
        request=MfaCodeSerializer,
        responses={
            200: OpenApiResponse(response=_detail_serializer, description="MFA enabled"),
            400: OpenApiResponse(response=_error_serializer, description="Invalid code"),
        },
    ),
)

mfa_verify_view = extend_schema_view(
    post=extend_schema(
        summary="Verify MFA login",
        description="Complete login after credentials were accepted and MFA is required.",
        request=MfaCodeSerializer,
        responses={
            200: OpenApiResponse(response=UserSerializer, description="Authenticated"),
            400: OpenApiResponse(response=_error_serializer, description="Invalid code or no pending login"),
        },
    ),
)

mfa_disable_view = extend_schema_view(
    post=extend_schema(
        summary="Disable MFA",
        description="Disable MFA using account password and a valid TOTP code.",
        request=MfaDisableSerializer,
        responses={
            200: OpenApiResponse(response=_detail_serializer, description="MFA disabled"),
            400: OpenApiResponse(response=_error_serializer, description="Invalid credentials"),
        },
    ),
)

github_authorization_view = extend_schema_view(
    get=extend_schema(
        summary="GitHub OAuth URL",
        description="Return the GitHub authorization URL to start social login.",
        responses={
            200: OpenApiResponse(response=GitHubAuthorizationUrlSerializer, description="Authorization URL"),
            503: OpenApiResponse(response=_detail_serializer, description="GitHub OAuth not configured"),
        },
    ),
)

github_callback_view = extend_schema_view(
    post=extend_schema(
        summary="GitHub OAuth callback",
        description=(
            "Exchange the GitHub authorization code for a session. "
            "New accounts require a pending invite for the GitHub email."
        ),
        request=GitHubCallbackSerializer,
        responses={
            200: OpenApiResponse(response=UserSerializer, description="Authenticated"),
            400: OpenApiResponse(response=_error_serializer, description="OAuth failed"),
            403: OpenApiResponse(response=_detail_serializer, description="Invite required"),
            503: OpenApiResponse(response=_detail_serializer, description="GitHub OAuth not configured"),
        },
    ),
)

invite_create_view = extend_schema_view(
    post=extend_schema(
        summary="Create member invite",
        description="Invite someone by email. Only authenticated members can create invites.",
        request=CreateInviteSerializer,
        responses={
            201: OpenApiResponse(response=CreateInviteResponseSerializer, description="Invite created"),
            400: OpenApiResponse(response=CreateInviteSerializer, description="Validation error"),
        },
    ),
)

invite_list_view = extend_schema_view(
    get=extend_schema(
        summary="List sent invites",
        description="Return invites created by the authenticated member.",
        responses={
            200: MemberInviteSerializer(many=True),
        },
    ),
)

invite_validate_view = extend_schema_view(
    get=extend_schema(
        summary="Validate invite token",
        description="Check whether an invite token is valid before showing the registration form.",
        parameters=[
            OpenApiParameter(
                name="token",
                type=str,
                location=OpenApiParameter.QUERY,
                required=True,
            ),
        ],
        responses={
            200: OpenApiResponse(response=InviteValidateSerializer, description="Validation result"),
            400: OpenApiResponse(response=InviteValidateSerializer, description="Missing token"),
        },
    ),
)
