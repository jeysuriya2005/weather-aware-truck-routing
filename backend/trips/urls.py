from django.urls import path

from . import views

urlpatterns = [
    path("health/", views.health, name="health"),
    path("geocode/", views.GeocodeView.as_view(), name="geocode"),
    path("trips/plan/", views.TripPlanView.as_view(), name="trip-plan"),
]
