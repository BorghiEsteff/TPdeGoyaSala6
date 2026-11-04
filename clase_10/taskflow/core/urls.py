from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r"projects", views.ProjectViewSet, basename="project")
router.register(r"tasks", views.TaskViewSet, basename="task")

urlpatterns = [
    path("health/", views.health_check, name="health_check"),
    path("", include(router.urls)),
]
