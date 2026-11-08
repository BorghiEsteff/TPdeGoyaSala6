from graphene_django.views import GraphQLView
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication


class JWTGraphQLView(GraphQLView):
    """
    GraphQLView es una vista de Django común, no de DRF: no lee el header
    Authorization por su cuenta. Acá lo hacemos a mano con la misma clase
    JWTAuthentication que usa DRF (Clase 6).
    """

    def dispatch(self, request, *args, **kwargs):
        try:
            result = JWTAuthentication().authenticate(request)
        except AuthenticationFailed:
            result = None
        if result is not None:
            request.user, _ = result
        return super().dispatch(request, *args, **kwargs)
