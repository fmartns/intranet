from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema, extend_schema_view, inline_serializer
from rest_framework import serializers

health_check_view = extend_schema_view(
    get=extend_schema(
        summary="Health check",
        description="Check if the server is running",
        responses={
            200: OpenApiResponse(
                response=inline_serializer(
                    name="HealthCheckResponse",
                    fields={"status": serializers.CharField()},
                ),
                description="OK",
                examples=[
                    OpenApiExample(
                        name="OK",
                        value={"status": "ok"},
                    ),
                ],
            ),
            500: OpenApiResponse(
                response=inline_serializer(
                    name="HealthCheckResponse",
                    fields={"status": serializers.CharField()},
                ),
                description="Internal server error",
                examples=[
                    OpenApiExample(
                        name="Internal server error",
                        value={"status": "internal server error"},
                    ),
                ],
            ),
        },
    ),
)
