from datetime import date
from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from .models import Project, ProjectMembership, Task


class TaskFlowRBACPermissionTests(TestCase):
    def setUp(self):
        self.api_client = APIClient()
        self.admin_user = User.objects.create_user(
            username="admin_proj", email="admin@ejemplo.com", password="claveSegura123!"
        )
        self.member_user = User.objects.create_user(
            username="miembro_proj", email="miembro@ejemplo.com", password="claveSegura123!"
        )
        self.stranger_user = User.objects.create_user(
            username="extrano", email="extrano@ejemplo.com", password="claveSegura123!"
        )

        self.project = Project.objects.create(name="Proyecto RBAC", description="Test")
        ProjectMembership.objects.create(
            project=self.project, user=self.admin_user, role="admin"
        )
        ProjectMembership.objects.create(
            project=self.project, user=self.member_user, role="miembro"
        )

    def test_admin_can_create_task(self):
        self.api_client.force_authenticate(user=self.admin_user)
        response = self.api_client.post(
            "/api/tasks/",
            {
                "project": self.project.id,
                "title": "Tarea por admin",
                "due_date": str(date.today()),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_member_cannot_create_task(self):
        self.api_client.force_authenticate(user=self.member_user)
        response = self.api_client.post(
            "/api/tasks/",
            {
                "project": self.project.id,
                "title": "Tarea intento miembro",
                "due_date": str(date.today()),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_member_can_read_tasks(self):
        Task.objects.create(
            project=self.project,
            title="Tarea existente",
            status="pendiente",
            due_date=date.today(),
            owner=self.admin_user,
        )
        self.api_client.force_authenticate(user=self.member_user)
        response = self.api_client.get("/api/tasks/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.json()["results"]
        self.assertEqual(len(results), 1)

    def test_stranger_cannot_see_project(self):
        self.api_client.force_authenticate(user=self.stranger_user)
        response = self.api_client.get(f"/api/projects/{self.project.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_add_member_action_by_admin(self):
        self.api_client.force_authenticate(user=self.admin_user)
        response = self.api_client.post(
            f"/api/projects/{self.project.id}/add_member/",
            {"username": "extrano", "role": "miembro"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            ProjectMembership.objects.filter(
                project=self.project, user=self.stranger_user
            ).exists()
        )


class SecurityAndSanitizationTests(TestCase):
    def setUp(self):
        self.api_client = APIClient()
        self.user = User.objects.create_user(
            username="testsec", email="testsec@ejemplo.com", password="claveSegura123!"
        )
        self.project = Project.objects.create(name="Proyecto Seguridad")
        ProjectMembership.objects.create(
            project=self.project, user=self.user, role="admin"
        )

    def test_nh3_description_sanitization(self):
        self.api_client.force_authenticate(user=self.user)
        malicious_html = "<script>alert('xss')</script>Hola <b>mundo</b>"
        response = self.api_client.post(
            "/api/tasks/",
            {
                "project": self.project.id,
                "title": "Tarea Sanitizada",
                "description": malicious_html,
                "due_date": str(date.today()),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        task_id = response.json()["id"]
        task = Task.objects.get(id=task_id)
        self.assertEqual(task.description, "Hola mundo")

    def test_failed_login_creates_security_log(self):
        from .models import SecurityLog
        response = self.api_client.post(
            "/api/token/",
            {"username": "testsec", "password": "password_erroneo"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        log = SecurityLog.objects.filter(action="login_failed").first()
        self.assertIsNotNone(log)
        self.assertIn("usuario=testsec", log.detail)

    def test_permission_denied_creates_security_log(self):
        from .models import SecurityLog
        member_user = User.objects.create_user(
            username="miembro_log", email="m@ejemplo.com", password="claveSegura123!"
        )
        ProjectMembership.objects.create(
            project=self.project, user=member_user, role="miembro"
        )
        task = Task.objects.create(
            project=self.project,
            title="Tarea Admin",
            status="pendiente",
            due_date=date.today(),
            owner=self.user,
        )
        self.api_client.force_authenticate(user=member_user)
        response = self.api_client.delete(f"/api/tasks/{task.id}/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        log = SecurityLog.objects.filter(action="permission_denied").first()
        self.assertIsNotNone(log)
        self.assertEqual(log.user, member_user)

    def test_cors_headers_allowed_origin(self):
        response = self.api_client.get(
            "/api/health/", HTTP_ORIGIN="http://localhost:3000"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.headers.get("Access-Control-Allow-Origin"), "http://localhost:3000"
        )

    def test_cors_headers_disallowed_origin(self):
        response = self.api_client.get(
            "/api/health/", HTTP_ORIGIN="http://sitio-malicioso.com"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.headers.get("Access-Control-Allow-Origin"))


class WebSocketConsumerTests(TestCase):
    async def test_websocket_connection_and_echo(self):
        from channels.db import database_sync_to_async
        from channels.testing import WebsocketCommunicator
        from config.asgi import application

        project = await database_sync_to_async(Project.objects.create)(
            name="Proyecto WebSocket"
        )
        communicator = WebsocketCommunicator(
            application, f"/ws/projects/{project.id}/"
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        # Enviar mensaje y recibir echo
        await communicator.send_json_to({"mensaje": "hola desde test"})
        response = await communicator.receive_json_from()
        self.assertEqual(response, {"echo": {"mensaje": "hola desde test"}})

        await communicator.disconnect()

    async def test_websocket_rejects_nonexistent_project(self):
        from channels.testing import WebsocketCommunicator
        from config.asgi import application

        communicator = WebsocketCommunicator(application, "/ws/projects/99999/")
        connected, _ = await communicator.connect()
        self.assertFalse(connected)
        await communicator.disconnect()


