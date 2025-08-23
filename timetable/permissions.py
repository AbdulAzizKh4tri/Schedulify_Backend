from rest_framework.permissions import BasePermission
from django.contrib.auth import get_user_model

SAFE_METHODS = ('GET', 'HEAD', 'OPTIONS')

class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.role == get_user_model().Admin
    
class IsOwnerOrReadOnly(BasePermission):
    def has_object_permission(self, request, view, obj):
        return bool(request.method in SAFE_METHODS or obj.teacher.user == request.user)

class IsSelfOrReadOnly(BasePermission):
    def has_object_permission(self, request, view, obj):
        return bool(request.method in SAFE_METHODS or obj.user == request.user )


