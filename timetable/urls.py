from django.urls import path

from . import views

urlpatterns = [
    path("generate/", views.generate),
    path("show/<int:ttid>/<str:division>", views.show),
]