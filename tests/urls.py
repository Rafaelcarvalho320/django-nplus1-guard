"""URLs used by the middleware tests."""

from django.urls import path
from tests import views

urlpatterns = [
    path("naive/", views.naive, name="naive"),
    path("optimized/", views.optimized, name="optimized"),
    path("health/", views.health, name="health"),
]
