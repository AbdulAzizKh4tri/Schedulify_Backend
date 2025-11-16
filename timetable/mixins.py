# timetable/mixins.py

from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction

class CSVUploadMixin:
    """
    Generic reusable CSV uploader.
    Each ViewSet must define:
        csv_key = "<key-name>"
        csv_serializer = <SerializerClass>
    """

    csv_key = None          # required
    csv_serializer = None   # required

    @action(detail=False, methods=["post"], url_path="csv_upload")
    def csv_upload(self, request):
        if not self.csv_key or not self.csv_serializer:
            return Response({"error": "CSVUploadMixin misconfigured"}, status=500)

        data = request.data.get(self.csv_key)
        if not isinstance(data, list):
            return Response(
                {"error": f"'{self.csv_key}' must be a list of objects"},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = self.csv_serializer(data=data, many=True)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            instances = serializer.save()

        return Response(
            {
                "created": self.csv_serializer(instances, many=True).data,
                "total_created": len(instances)
            },
            status=status.HTTP_201_CREATED
        )
