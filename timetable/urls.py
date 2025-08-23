from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'classrooms', views.ClassRoomViewSet)
router.register(r'divisions', views.DivisionViewSet)
router.register(r'departments', views.DepartmentViewSet)
router.register(r'preferences', views.PreferenceViewSet)
router.register(r'subjects', views.SubjectViewSet)
router.register(r'teachers', views.TeacherViewSet)
router.register(r'timetables', views.TimetableViewSet)


urlpatterns = [
    path("generate/", views.generate),
    path("show/<int:ttid>/<str:division>", views.show),
    path('', include(router.urls)),

]