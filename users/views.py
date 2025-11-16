from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework.permissions import AllowAny
from django.contrib.auth import authenticate
from django.contrib.auth.hashers import make_password
from rest_framework.decorators import action
from django.db import transaction

import csv, io

from .models import User
from .serializers import UserSerializer, LoginSerializer
from timetable.serializers import TeacherSerializer, TimetableEntrySerializer, TimetableSerializer
from timetable.models import Teacher, TimetableEntry

class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer

    def perform_create(self, serializer):
        # Automatically hash password if provided
        pwd = serializer.validated_data.get("password")
        if pwd:
            serializer.save(password=make_password(pwd))
        else:
            serializer.save()

    def perform_update(self, serializer):
        pwd = serializer.validated_data.get("password")
        if pwd:
            serializer.save(password=make_password(pwd))
        else:
            # Exclude password from update if not provided
            serializer.save()

    @action(detail=False, methods=["post"])
    def csv_upload(self, request):
        """
        Expects JSON: { users: [ {full_name, email, phone_number, gender, role, password, is_staff, is_superuser}, ... ] }
        """
        users_list = request.data.get("users")
        if not isinstance(users_list, list):
            return Response({"detail": "Invalid format, 'users' must be a list"}, status=400)

        created = 0
        updated = 0

        with transaction.atomic():
            for u in users_list:
                email = u.get("email")
                if not email:
                    continue

                try:
                    user = User.objects.get(email=email)
                    # PATCH-like update
                    for field in ["full_name", "phone_number", "gender", "role", "is_staff", "is_superuser"]:
                        if field in u:
                            setattr(user, field, u[field])
                    if "password" in u and u["password"]:
                        user.password = make_password(u["password"])
                    user.save()
                    updated += 1
                except User.DoesNotExist:
                    # Create new user
                    pwd = u.get("password")
                    user = User(
                        email=email,
                        full_name=u.get("full_name", ""),
                        phone_number=u.get("phone_number", ""),
                        gender=u.get("gender", "Male"),
                        role=u.get("role", "Student"),
                        is_staff=u.get("is_staff", False),
                        is_superuser=u.get("is_superuser", False)
                    )
                    if pwd:
                        user.password = make_password(pwd)
                    else:
                        # If no password provided, generate a random one
                        import secrets
                        user.password = make_password(secrets.token_urlsafe(8))
                    user.save()
                    created += 1

        return Response({"detail": f"CSV processed. Created: {created}, Updated: {updated}"})

class LoginView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            password = serializer.validated_data['password']
            user = authenticate(email=email, password=password)
            if user:
                refresh = RefreshToken.for_user(user)
                return Response({
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                    'user': UserSerializer(user).data
                }, status=status.HTTP_200_OK)
            return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data.get('refresh')
            if not refresh_token:
                return Response({'error': 'Refresh token required'}, status=status.HTTP_400_BAD_REQUEST)
            token = RefreshToken(refresh_token)
            token.blacklist()  # Add to blacklist
            return Response({'message': 'Successfully logged out'}, status=status.HTTP_205_RESET_CONTENT)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class ProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        serializer = UserSerializer(user)
        if user.role == User.TEACHER:
            try:
                teacher = Teacher.objects.get(user=user)
                teacher_serializer = TeacherSerializer(teacher)
                timetable_entries = TimetableEntry.objects.filter(teacher=teacher)

                profile_data = {
                    'user': serializer.data,
                    'teacher': teacher_serializer.data,
                    'timetable': TimetableEntrySerializer(timetable_entries, many=True).data
                }
                return Response(profile_data, status=status.HTTP_200_OK)
            except Teacher.DoesNotExist:
                return Response({'error': 'Teacher profile not found'}, status=status.HTTP_404_NOT_FOUND)

        return Response({'user':serializer.data}, status=status.HTTP_200_OK)