from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .domain.geometry import Coordinate
from .serializers import GeocodeQuerySerializer, RoutePlanRequestSerializer


@api_view(["GET"])
def health(request: Request) -> Response:
    """Liveness probe. Does not call external providers."""
    return Response({"status": "ok", "service": "weather-aware-truck-routing"})


class GeocodeView(APIView):
    """GET /api/geocode/?q=... -> location suggestions for autocomplete."""

    throttle_scope = "geocode"

    def get(self, request: Request) -> Response:
        serializer = GeocodeQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        return Response({"results": services.search_places(serializer.validated_data["q"])})


class TripPlanView(APIView):
    """POST /api/trips/plan/ -> routes, checkpoint weather risk, recommendation and heatmap."""

    throttle_scope = "trip_plan"

    def post(self, request: Request) -> Response:
        serializer = RoutePlanRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        inputs = {
            "origin": data["origin"],
            "destination": data["destination"],
            "departure_time": data["departure_time"].isoformat(),
            "load_weight_lb": data["load_weight_lb"],
            "checkpoint_interval_miles": data["checkpoint_interval_miles"],
        }
        return Response(
            services.plan_trip(
                origin=Coordinate(data["origin"]["lat"], data["origin"]["lon"]),
                destination=Coordinate(data["destination"]["lat"], data["destination"]["lon"]),
                departure_time=data["departure_time"],
                load_weight_lb=data["load_weight_lb"],
                interval_miles=data["checkpoint_interval_miles"],
                inputs=inputs,
            )
        )
