from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from accounts.models import User, phone_validator


def _clean_email(value, exclude_pk=None):
    email = value.strip().lower()
    qs = User.objects.filter(email__iexact=email)
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    if qs.exists():
        raise serializers.ValidationError("A user with this email already exists.")
    return email


class UserSerializer(serializers.ModelSerializer):
    """Compact, read-oriented representation of a user (never includes the password)."""

    class Meta:
        model = User
        fields = [
            "id", "username", "first_name", "last_name", "email", "phone",
            "role", "is_active", "date_joined",
        ]
        read_only_fields = fields


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, style={"input_type": "password"})
    password2 = serializers.CharField(write_only=True, style={"input_type": "password"})

    class Meta:
        model = User
        fields = [
            "id", "username", "first_name", "last_name", "email", "phone",
            "password", "password2",
        ]
        extra_kwargs = {
            "email": {"required": True},
            "first_name": {"required": True},
            "phone": {"validators": [phone_validator]},
        }

    def validate_email(self, value):
        return _clean_email(value)

    def validate(self, attrs):
        if attrs["password"] != attrs.pop("password2"):
            raise serializers.ValidationError({"password2": "Passwords do not match."})
        candidate = User(
            username=attrs.get("username", ""),
            email=attrs.get("email", ""),
            first_name=attrs.get("first_name", ""),
        )
        validate_password(attrs["password"], candidate)
        return attrs

    def create(self, validated_data):
        # Public registration can only ever create the lowest-privilege role.
        return User.objects.create_user(role=User.Role.STAFF, **validated_data)


class LoginSerializer(TokenObtainPairSerializer):
    """Accepts a username (or email in the ``username`` field) and returns tokens + user."""

    def validate(self, attrs):
        identifier = attrs.get(self.username_field, "")
        if "@" in identifier:
            match = User.objects.filter(email__iexact=identifier).first()
            if match:
                attrs[self.username_field] = match.get_username()
        data = super().validate(attrs)
        return {
            "message": "Login successful",
            "access": data["access"],
            "refresh": data["refresh"],
            "user": {
                "id": self.user.id,
                "username": self.user.username,
                "email": self.user.email,
                "role": self.user.role,
            },
        }


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id", "username", "first_name", "last_name", "email", "phone",
            "role", "date_joined", "updated_at",
        ]
        read_only_fields = ["id", "username", "role", "date_joined", "updated_at"]

    def validate_email(self, value):
        return _clean_email(value, exclude_pk=self.instance.pk if self.instance else None)


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)

    def validate_old_password(self, value):
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("Old password is incorrect.")
        return value

    def validate(self, attrs):
        if attrs["new_password"] != attrs["confirm_password"]:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        validate_password(attrs["new_password"], self.context["request"].user)
        return attrs


class UserManagementSerializer(serializers.ModelSerializer):
    """Used by administrators to create / update / list users."""

    password = serializers.CharField(
        write_only=True, required=False, style={"input_type": "password"}
    )

    class Meta:
        model = User
        fields = [
            "id", "username", "first_name", "last_name", "email", "phone", "role",
            "is_active", "is_staff", "is_superuser", "password", "date_joined", "updated_at",
        ]
        read_only_fields = ["id", "is_staff", "is_superuser", "date_joined", "updated_at"]

    def validate_email(self, value):
        return _clean_email(value, exclude_pk=self.instance.pk if self.instance else None)

    def validate_password(self, value):
        validate_password(value, self.instance)
        return value

    def validate(self, attrs):
        if self.instance is None and not attrs.get("password"):
            raise serializers.ValidationError({"password": "This field is required."})
        if self.instance and self.instance.is_superuser and attrs.get("is_active") is False:
            others = User.objects.filter(is_superuser=True, is_active=True).exclude(
                pk=self.instance.pk
            )
            if not others.exists():
                raise serializers.ValidationError(
                    {"is_active": "The last active superuser cannot be deactivated."}
                )
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        return User.objects.create_user(password=password, **validated_data)

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance
