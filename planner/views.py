from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import RouteRequestSerializer
from .services.locations import LocationError
from .services.planner import NoFeasiblePlan, plan_trip
from .services.routing import RoutingError


class RouteView(APIView):
    def post(self, request):
        ser = RouteRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)          # missing/blank input -> 400
        try:
            result = plan_trip(ser.validated_data["start"],
                               ser.validated_data["finish"])
        except LocationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except NoFeasiblePlan as e:
            return Response({"error": str(e)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        except RoutingError as e:
            return Response({"error": str(e)}, status=status.HTTP_502_BAD_GATEWAY)
        return Response(result)