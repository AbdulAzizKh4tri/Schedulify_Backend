from rest_framework.permissions import BasePermission
from django.contrib.auth import get_user_model

SAFE_METHODS = ('GET', 'HEAD', 'OPTIONS')

class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.role == get_user_model().ADMIN
    
class IsOwnerOrReadOnly(BasePermission):
    def has_object_permission(self, request, view, obj):
        return request.user.is_authenticated and bool(request.method in SAFE_METHODS or obj.teacher.user == request.user)

class IsSelfOrReadOnly(BasePermission):
    def has_object_permission(self, request, view, obj):
        return request.user.is_authenticated and bool(request.method in SAFE_METHODS or obj.user == request.user)
    
class ReadOnly(BasePermission):
    def has_object_permission(self, request, view, obj):
        return request.method in SAFE_METHODS


