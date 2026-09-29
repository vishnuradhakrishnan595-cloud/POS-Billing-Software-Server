from rest_framework.permissions import SAFE_METHODS, BasePermission

from accounts.models import User

Role = User.Role


def has_role(user, *roles):
    """True if the user is an active, authenticated user holding one of ``roles``.

    Superusers are treated as administrators and pass every role check.
    """
    if not (user and user.is_authenticated and user.is_active):
        return False
    if user.is_superuser:
        return True
    return user.role in roles


class RolePermission(BasePermission):
    allowed_roles = ()

    def has_permission(self, request, view):
        return has_role(request.user, *self.allowed_roles)


class IsAdmin(RolePermission):
    allowed_roles = (Role.ADMIN,)


class IsManager(RolePermission):
    allowed_roles = (Role.MANAGER,)


class IsCashier(RolePermission):
    allowed_roles = (Role.CASHIER,)


class IsStaff(RolePermission):
    allowed_roles = (Role.STAFF,)


class IsAdminOrManager(RolePermission):
    allowed_roles = (Role.ADMIN, Role.MANAGER)


class IsAdminManagerOrCashier(RolePermission):
    allowed_roles = (Role.ADMIN, Role.MANAGER, Role.CASHIER)


class IsAuthenticatedUser(RolePermission):
    """Any active authenticated user, whatever their role."""

    allowed_roles = (Role.ADMIN, Role.MANAGER, Role.CASHIER, Role.STAFF)


class ReadOnlyOrAdminManager(BasePermission):
    """Any authenticated user may read; only ADMIN/MANAGER may write."""

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return has_role(request.user, *IsAuthenticatedUser.allowed_roles)
        return has_role(request.user, Role.ADMIN, Role.MANAGER)
