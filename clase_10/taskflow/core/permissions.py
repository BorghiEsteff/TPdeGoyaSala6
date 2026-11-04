import logging
from rest_framework import permissions
from .models import SecurityLog
from .services import MembershipService

security_logger = logging.getLogger("security")


class IsProjectAdminOrReadOnly(permissions.BasePermission):
    """
    Cualquier miembro del proyecto puede leer (SAFE_METHODS).
    Solo un admin del proyecto puede modificar (editar/borrar/completar).
    Sirve tanto para Task (obj.project) como para Project (obj).
    """

    def has_object_permission(self, request, view, obj):
        project = obj.project if hasattr(obj, "project") else obj

        if request.method in permissions.SAFE_METHODS:
            return MembershipService.is_member(request.user, project)

        is_admin = MembershipService.is_admin(request.user, project)
        if not is_admin:
            ip = request.META.get("REMOTE_ADDR") if hasattr(request, "META") else None
            SecurityLog.objects.create(
                user=request.user if request.user and request.user.is_authenticated else None,
                action="permission_denied",
                detail=f"accion={request.method} proyecto={getattr(project, 'id', None)}",
                ip_address=ip,
            )
            security_logger.warning(
                f"Permiso denegado para usuario {request.user} ({request.method} en proyecto {getattr(project, 'id', None)}) desde {ip}"
            )
        return is_admin

