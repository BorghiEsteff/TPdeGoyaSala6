import logging
from django.contrib.auth.models import User
from django.db import transaction
from django.http import JsonResponse
from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from .models import Project, ProjectMembership, SecurityLog
from .permissions import IsProjectAdminOrReadOnly
from .repositories import TaskRepository
from .serializers import ProjectSerializer, TaskSerializer
from .serializers_auth import RegisterSerializer
from .services import MembershipService, NotificationService, ProjectService, TaskService
from .throttles import LoginRateThrottle

security_logger = logging.getLogger("security")


def health_check(request):
    return JsonResponse({"status": "ok", "service": "TaskFlow API"})


class ThrottledTokenObtainPairView(TokenObtainPairView):
    throttle_classes = [LoginRateThrottle]

    def post(self, request, *args, **kwargs):
        try:
            return super().post(request, *args, **kwargs)
        except AuthenticationFailed:
            ip = request.META.get("REMOTE_ADDR")
            username = request.data.get("username", "")
            SecurityLog.objects.create(
                action="login_failed", detail=f"usuario={username}", ip_address=ip
            )
            security_logger.warning(
                f"Login fallido para usuario {username} desde {ip}"
            )
            raise


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]


class SocialLoginJWTView(APIView):
    """
    Entrega un par de tokens JWT propios tras el flujo OAuth de Google / allauth.
    """

    def get(self, request):
        refresh = RefreshToken.for_user(request.user)
        return Response({"refresh": str(refresh), "access": str(refresh.access_token)})


class ProjectViewSet(viewsets.ModelViewSet):
    queryset = Project.objects.all().order_by("id")
    serializer_class = ProjectSerializer
    permission_classes = [IsAuthenticated, IsProjectAdminOrReadOnly]

    def get_queryset(self):
        return MembershipService.projects_for(self.request.user)

    def perform_create(self, serializer):
        with transaction.atomic():
            project = serializer.save()
            ProjectMembership.objects.create(
                project=project, user=self.request.user, role="admin"
            )

    @action(detail=True, methods=["get"])
    def summary(self, request, pk=None):
        project = self.get_object()
        data = ProjectService.project_summary(project)
        return Response(data)

    @action(detail=True, methods=["post"])
    def add_member(self, request, pk=None):
        project = self.get_object()
        username = request.data.get("username")
        role = request.data.get("role", "miembro")

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            return Response(
                {"error": True, "detail": "Usuario no encontrado."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if ProjectMembership.objects.filter(project=project, user=user).exists():
            return Response(
                {"error": True, "detail": "El usuario ya es miembro de este proyecto."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        membership = ProjectMembership.objects.create(
            project=project, user=user, role=role
        )
        return Response(
            {
                "status": "ok",
                "user": membership.user.username,
                "project": membership.project.id,
                "role": membership.role,
            },
            status=status.HTTP_201_CREATED,
        )


class TaskViewSet(viewsets.ModelViewSet):
    queryset = TaskRepository.get_queryset()
    serializer_class = TaskSerializer
    filterset_fields = ["status", "priority", "project"]
    ordering_fields = ["due_date", "created_at", "priority"]
    search_fields = ["title", "description"]
    permission_classes = [IsAuthenticated, IsProjectAdminOrReadOnly]

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .filter(project__memberships__user=self.request.user)
            .distinct()
        )

    def check_project_admin(self, project):
        if not MembershipService.is_admin(self.request.user, project):
            ip = self.request.META.get("REMOTE_ADDR") if hasattr(self.request, "META") else None
            SecurityLog.objects.create(
                user=self.request.user if self.request.user.is_authenticated else None,
                action="permission_denied",
                detail=f"accion=create/move_task proyecto={getattr(project, 'id', None)}",
                ip_address=ip,
            )
            security_logger.warning(
                f"Permiso denegado para usuario {self.request.user} al crear/mover tarea en proyecto {getattr(project, 'id', None)} desde {ip}"
            )
            raise PermissionDenied(
                "Solo un admin del proyecto puede crear o mover tareas en él."
            )

    def perform_create(self, serializer):
        self.check_project_admin(serializer.validated_data["project"])
        task = serializer.save(owner=self.request.user)
        NotificationService.notify_task_created(task)

    def perform_update(self, serializer):
        if "project" in serializer.validated_data:
            self.check_project_admin(serializer.validated_data["project"])
        task = serializer.save()
        NotificationService.notify_task_updated(task)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        task = self.get_object()
        TaskService.mark_completed(task)
        NotificationService.notify_task_completed(task)
        return Response(self.get_serializer(task).data)

    @action(detail=False, methods=["get"])
    def overdue(self, request):
        tasks = TaskService.tasks_overdue(self.get_queryset())
        page = self.paginate_queryset(tasks)
        if page is not None:
            return self.get_paginated_response(self.get_serializer(page, many=True).data)
        return Response(self.get_serializer(tasks, many=True).data)
