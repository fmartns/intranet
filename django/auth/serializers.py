from typing import cast

from rest_framework import serializers

from django.contrib.auth import get_user_model
from django.contrib.auth.models import User as UserType
from django.contrib.auth.password_validation import validate_password

from .models import MemberInvite
from .services import consume_invite, get_user_profile, get_valid_invite_for_email, registration_open_without_invite

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    mfa_enabled = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "is_staff",
            "date_joined",
            "mfa_enabled",
        ]
        read_only_fields = fields

    def get_mfa_enabled(self, obj: UserType) -> bool:
        return get_user_profile(obj).mfa_enabled


class UserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["email", "first_name", "last_name"]


class RegisterSerializer(serializers.Serializer):
    invite_token = serializers.CharField(required=False, allow_blank=True)
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True, min_length=8)

    def validate_username(self, value: str) -> str:
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("A user with this username already exists.")
        return value

    def validate_email(self, value: str) -> str:
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate(self, attrs: dict) -> dict:
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError({"password_confirm": "Passwords do not match."})
        validate_password(attrs["password"])

        if registration_open_without_invite():
            return attrs

        invite_token = attrs.get("invite_token", "").strip()
        if not invite_token:
            raise serializers.ValidationError({"invite_token": "A valid invite is required to register."})

        invite = get_valid_invite_for_email(invite_token, attrs["email"])
        if invite is None:
            raise serializers.ValidationError({"invite_token": "Invalid, expired, or email-mismatched invite."})

        attrs["invite"] = invite
        return attrs

    def create(self, validated_data: dict) -> UserType:
        invite = validated_data.pop("invite", None)
        validated_data.pop("invite_token", None)
        validated_data.pop("password_confirm", None)

        user = UserType.objects.create_user(
            username=validated_data["username"],
            email=validated_data["email"],
            password=validated_data["password"],
        )
        get_user_profile(user)

        if invite is not None:
            consume_invite(invite, user)

        return user


class CreateInviteSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value: str) -> str:
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value


class MemberInviteSerializer(serializers.ModelSerializer):
    valid = serializers.BooleanField(source="is_valid", read_only=True)

    class Meta:
        model = MemberInvite
        fields = ["id", "email", "created_at", "expires_at", "accepted_at", "valid"]
        read_only_fields = fields


class CreateInviteResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    email = serializers.EmailField()
    token = serializers.CharField()
    expires_at = serializers.DateTimeField()
    signup_url = serializers.CharField()


class InviteValidateSerializer(serializers.Serializer):
    valid = serializers.BooleanField()
    email = serializers.EmailField(required=False)
    expires_at = serializers.DateTimeField(required=False)


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)


class LoginMfaRequiredSerializer(serializers.Serializer):
    detail = serializers.CharField()
    mfa_required = serializers.BooleanField()


class PasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)
    new_password_confirm = serializers.CharField(write_only=True, min_length=8)

    def validate_current_password(self, value: str) -> str:
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value

    def validate(self, attrs: dict) -> dict:
        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError({"new_password_confirm": "Passwords do not match."})
        validate_password(attrs["new_password"], user=self.context["request"].user)
        return attrs

    def save(self, **kwargs) -> UserType:
        user = cast(UserType, self.context["request"].user)
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password"])
        return user


class PasswordForgotSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, min_length=8)
    new_password_confirm = serializers.CharField(write_only=True, min_length=8)

    def validate(self, attrs: dict) -> dict:
        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError({"new_password_confirm": "Passwords do not match."})
        return attrs


class MfaCodeSerializer(serializers.Serializer):
    code = serializers.CharField(min_length=6, max_length=6)


class MfaSetupResponseSerializer(serializers.Serializer):
    secret = serializers.CharField()
    provisioning_uri = serializers.CharField()


class MfaDisableSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True)
    code = serializers.CharField(min_length=6, max_length=6)


class GitHubAuthorizationUrlSerializer(serializers.Serializer):
    authorization_url = serializers.CharField()
    state = serializers.CharField()


class GitHubCallbackSerializer(serializers.Serializer):
    code = serializers.CharField()
    state = serializers.CharField(required=False, allow_blank=True)
