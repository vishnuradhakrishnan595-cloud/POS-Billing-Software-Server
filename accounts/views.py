from rest_framework import generics, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from accounts.models import User
from accounts.permissions import IsAdmin
from accounts.serializers import (
    ChangePasswordSerializer,
    LoginSerializer,
    LogoutSerializer,
    ProfileSerializer,
    RegisterSerializer,
    UserManagementSerializer,
    UserSerializer,
)
from config.exceptions import success_response


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    authentication_classes = []

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return success_response("Registration successful", UserSerializer(user).data, 201)


class LoginView(TokenObtainPairView):
    serializer_class = LoginSerializer
    permission_classes = [AllowAny]
    authentication_classes = []
    


class RefreshView(TokenRefreshView):
    permission_classes = [AllowAny]
    authentication_classes = []


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            RefreshToken(serializer.validated_data["refresh"]).blacklist()
        except TokenError:
            raise ValidationError({"refresh": ["Token is invalid or expired."]})
        return success_response("Logged out successfully")


class ProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = ProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save()
        return success_response("Password changed successfully")


class UserViewSet(viewsets.ModelViewSet):
    """Admin-only user management."""

    queryset = User.objects.all().order_by("id")
    serializer_class = UserManagementSerializer
    permission_classes = [IsAdmin]
    filterset_fields = ["role", "is_active"]
    search_fields = ["username", "email", "first_name", "last_name", "phone"]
    ordering_fields = ["id", "username", "date_joined", "role"]

    def destroy(self, request, *args, **kwargs):
        user = self.get_object()
        if user.pk == request.user.pk:
            raise ValidationError("You cannot delete your own account.")
        if user.is_superuser:
            others = User.objects.filter(is_superuser=True, is_active=True).exclude(pk=user.pk)
            if not others.exists():
                raise ValidationError("The last active superuser cannot be deleted.")
        user.delete()  # ProtectedError (users with sales history) -> 409 via exception handler
        return Response(status=204)
