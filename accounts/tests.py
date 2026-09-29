from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User


def make_user(role="STAFF", username=None, password="StrongPass#123", **extra):
    username = username or f"{role.lower()}_user"
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password=password,
        role=role,
        **extra,
    )


def auth_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


class AuthTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def _register(self, **overrides):
        payload = {
            "username": "newuser", "email": "new@example.com", "first_name": "New",
            "password": "StrongPass#123", "password2": "StrongPass#123",
        }
        payload.update(overrides)
        return self.client.post("/api/accounts/register/", payload, format="json")

    def test_register_creates_staff_and_hides_password(self):
        res = self._register(role="ADMIN")  # role must be ignored
        self.assertEqual(res.status_code, 201)
        self.assertNotIn("password", res.data["data"])
        self.assertEqual(User.objects.get(username="newuser").role, "STAFF")

    def test_register_duplicate_email_rejected(self):
        self._register()
        res = self._register(username="other", email="NEW@example.com")
        self.assertEqual(res.status_code, 400)
        self.assertFalse(res.data["success"])

    def test_register_password_mismatch(self):
        res = self._register(password2="different")
        self.assertEqual(res.status_code, 400)

    def test_login_returns_jwt(self):
        make_user("ADMIN", "admin")
        res = self.client.post(
            "/api/accounts/login/",
            {"username": "admin", "password": "StrongPass#123"},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["message"], "Login successful")
        self.assertIn("access", res.data)
        self.assertIn("refresh", res.data)
        self.assertEqual(res.data["user"]["role"], "ADMIN")

    def test_login_with_email(self):
        make_user("CASHIER", "cash")
        res = self.client.post(
            "/api/accounts/login/",
            {"username": "cash@example.com", "password": "StrongPass#123"},
            format="json",
        )
        self.assertEqual(res.status_code, 200)

    def test_login_wrong_password(self):
        make_user("ADMIN", "admin")
        res = self.client.post(
            "/api/accounts/login/", {"username": "admin", "password": "nope"}, format="json"
        )
        self.assertEqual(res.status_code, 401)
        self.assertFalse(res.data["success"])

    def test_jwt_authenticates_and_unauthenticated_gets_401(self):
        make_user("ADMIN", "admin")
        self.assertEqual(self.client.get("/api/accounts/profile/").status_code, 401)
        tokens = self.client.post(
            "/api/accounts/login/",
            {"username": "admin", "password": "StrongPass#123"},
            format="json",
        ).data
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        self.assertEqual(self.client.get("/api/accounts/profile/").status_code, 200)

    def test_refresh_and_logout_blacklist(self):
        make_user("ADMIN", "admin")
        tokens = self.client.post(
            "/api/accounts/login/",
            {"username": "admin", "password": "StrongPass#123"},
            format="json",
        ).data
        refreshed = self.client.post(
            "/api/accounts/token/refresh/", {"refresh": tokens["refresh"]}, format="json"
        )
        self.assertEqual(refreshed.status_code, 200)
        new_refresh = refreshed.data["refresh"]  # rotated

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refreshed.data['access']}")
        out = self.client.post("/api/accounts/logout/", {"refresh": new_refresh}, format="json")
        self.assertEqual(out.status_code, 200)

        again = self.client.post(
            "/api/accounts/token/refresh/", {"refresh": new_refresh}, format="json"
        )
        self.assertEqual(again.status_code, 401)

    def test_old_refresh_token_blacklisted_after_rotation(self):
        make_user("ADMIN", "admin")
        tokens = self.client.post(
            "/api/accounts/login/",
            {"username": "admin", "password": "StrongPass#123"},
            format="json",
        ).data
        self.client.post("/api/accounts/token/refresh/", {"refresh": tokens["refresh"]}, format="json")
        replay = self.client.post(
            "/api/accounts/token/refresh/", {"refresh": tokens["refresh"]}, format="json"
        )
        self.assertEqual(replay.status_code, 401)


class ProfileAndPasswordTests(TestCase):
    def setUp(self):
        self.user = make_user("CASHIER", "cash")
        self.client = auth_client(self.user)

    def test_get_and_patch_profile(self):
        self.assertEqual(self.client.get("/api/accounts/profile/").data["username"], "cash")
        res = self.client.patch(
            "/api/accounts/profile/", {"first_name": "Cass", "role": "ADMIN"}, format="json"
        )
        self.assertEqual(res.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Cass")
        self.assertEqual(self.user.role, "CASHIER")  # role is read-only

    def test_change_password(self):
        res = self.client.post(
            "/api/accounts/change-password/",
            {
                "old_password": "StrongPass#123",
                "new_password": "Another#Pass987",
                "confirm_password": "Another#Pass987",
            },
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Another#Pass987"))

    def test_change_password_wrong_old(self):
        res = self.client.post(
            "/api/accounts/change-password/",
            {"old_password": "bad", "new_password": "Another#Pass987",
             "confirm_password": "Another#Pass987"},
            format="json",
        )
        self.assertEqual(res.status_code, 400)


class UserManagementTests(TestCase):
    def setUp(self):
        self.admin = make_user("ADMIN", "admin")
        self.client = auth_client(self.admin)

    def test_non_admin_forbidden(self):
        for role in ("MANAGER", "CASHIER", "STAFF"):
            res = auth_client(make_user(role, f"u_{role}")).get("/api/accounts/users/")
            self.assertEqual(res.status_code, 403, role)

    def test_admin_creates_updates_and_deactivates(self):
        res = self.client.post(
            "/api/accounts/users/",
            {"username": "clerk", "email": "clerk@example.com", "role": "CASHIER",
             "password": "StrongPass#123"},
            format="json",
        )
        self.assertEqual(res.status_code, 201)
        self.assertNotIn("password", res.data)
        uid = res.data["id"]
        res = self.client.patch(
            f"/api/accounts/users/{uid}/", {"role": "MANAGER", "is_active": False}, format="json"
        )
        self.assertEqual(res.status_code, 200)
        user = User.objects.get(pk=uid)
        self.assertEqual(user.role, "MANAGER")
        self.assertFalse(user.is_active)

    def test_last_superuser_protected(self):
        root = User.objects.create_superuser("root", "root@example.com", "StrongPass#123")
        client = auth_client(root)
        # `admin` (role only) is not a superuser, so root is the only superuser
        res = client.patch(f"/api/accounts/users/{root.pk}/", {"is_active": False}, format="json")
        self.assertEqual(res.status_code, 400)
        other = User.objects.create_superuser("root2", "root2@example.com", "StrongPass#123")
        res = client.delete(f"/api/accounts/users/{root.pk}/")  # cannot delete self
        self.assertEqual(res.status_code, 400)
        User.objects.filter(pk=other.pk).update(is_active=False)
        res = auth_client(self.admin).delete(f"/api/accounts/users/{root.pk}/")
        self.assertEqual(res.status_code, 400)  # root is now the last active superuser
