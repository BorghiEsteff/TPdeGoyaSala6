from django.contrib import admin
from django.urls import path, include
from django.views.decorators.csrf import csrf_exempt
from rest_framework_simplejwt.views import TokenRefreshView
from core.graphql_views import JWTGraphQLView
from core.views import RegisterView, SocialLoginJWTView, ThrottledTokenObtainPairView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),
    path("api/", include("core.urls")),
    path("api/token/", ThrottledTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/register/", RegisterView.as_view(), name="register"),
    path("api/auth/social/jwt/", SocialLoginJWTView.as_view(), name="social_jwt"),
    path("api-auth/", include("rest_framework.urls")),
    path("graphql/", csrf_exempt(JWTGraphQLView.as_view(graphiql=True))),
]
