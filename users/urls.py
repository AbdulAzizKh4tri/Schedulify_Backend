from django.urls import path, include
from .views import LoginView, LogoutView, ProfileView, UserViewSet
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register(r'users', UserViewSet)

urlpatterns = [
    path('login/', LoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('me/', ProfileView.as_view(), name='profile'),
    path('refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('', include(router.urls)),
]