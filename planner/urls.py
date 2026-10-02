from django.urls import path

from .views import MapView, RouteView

urlpatterns = [
    path("", MapView.as_view(), name="map-home"),
    path("api/route/", RouteView.as_view(), name="api-route"),
]