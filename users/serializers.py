from rest_framework import serializers
from .models import User
from timetable.serializers import TeacherSerializer

class UserSerializer(serializers.ModelSerializer):
    teacher_profile = TeacherSerializer(read_only = True)
    class Meta:
        model = User
        fields = ['id', 'email', 'full_name', 'gender', 'phone_number', 'role', 'date_joined', 'last_login', 'teacher_profile']

    

class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)