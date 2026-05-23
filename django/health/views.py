from rest_framework.response import Response
from rest_framework.views import APIView

from .docs import health_check_view


@health_check_view
class HealthCheckView(APIView):
    """
    Health check endpoint.
    """

    def get(self, request) -> Response:
        """Return a 200 OK response.

        Returns:
            Response: A 200 OK response.
        """
        try:
            return Response({"status": "ok"})
        except Exception:
            return Response({"status": "internal server error"}, status=500)
