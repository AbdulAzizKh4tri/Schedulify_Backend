from rest_framework import serializers

from users.models import User
from users.serializers import UserSerializer
from .models import (
    ClassRoom, Department, Division, Preference,
    Subject, Teacher, Timetable, TimetableEntry
)


# -------------------------
# BASIC SERIALIZERS
# -------------------------

class ClassRoomSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClassRoom
        fields = "__all__"


class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = "__all__"


class SubjectSerializer(serializers.ModelSerializer):

    department = DepartmentSerializer(read_only=True)
    department_id = serializers.PrimaryKeyRelatedField(
        source='department',
        queryset=Department.objects.all(),
        write_only=True
    )    

    class Meta:
        model = Subject
        fields = "__all__"


class DivisionSerializer(serializers.ModelSerializer):

    department = DepartmentSerializer(read_only=True)
    department_id = serializers.PrimaryKeyRelatedField(
        source='department',
        queryset=Department.objects.all(),
        write_only=True
    )    

    class Meta:
        model = Division
        fields = "__all__"


class PreferenceSerializer(serializers.ModelSerializer):
    
    subject = SubjectSerializer(read_only=True)
    subject_id = serializers.PrimaryKeyRelatedField(
        source='subject',
        queryset=Subject.objects.all(),
        write_only=True
    )

    class Meta:
        model = Preference
        fields = "__all__"

class TeacherSerializer(serializers.ModelSerializer):
    # Full nested user on read
    user = UserSerializer(read_only=True)

    # Writable field that maps to the real FK
    user_id = serializers.PrimaryKeyRelatedField(
        source='user',          # <-- THIS is the correct fix
        queryset=User.objects.all(),
        write_only=True,
        allow_null=True,
        allow_empty=True
    )

    department = DepartmentSerializer(read_only=True)
    department_id = serializers.PrimaryKeyRelatedField(
        source='department',
        queryset=Department.objects.all(),
        write_only=True
    )

    class Meta:
        model = Teacher
        fields = "__all__"

class TeacherPreferenceSerializer(serializers.ModelSerializer):

    teacher_preferences = PreferenceSerializer(many=True, read_only=True)
    user = UserSerializer(read_only=True)
    department = DepartmentSerializer(read_only=True)

    class Meta:
        model = Teacher
        fields = "__all__"

class TimetableEntrySerializer(serializers.ModelSerializer):
    # Nested read-only relationships
    subject = SubjectSerializer(read_only=True)
    division = DivisionSerializer(read_only=True)
    classroom = ClassRoomSerializer(read_only=True)
    teacher = TeacherSerializer(read_only=True)

    # Writable FK fields
    subject_id = serializers.PrimaryKeyRelatedField(
        source='subject',
        queryset=Subject.objects.all(),
        write_only=True
    )
    division_id = serializers.PrimaryKeyRelatedField(
        source='division',
        queryset=Division.objects.all(),
        write_only=True
    )
    classroom_id = serializers.PrimaryKeyRelatedField(
        source='classroom',
        queryset=ClassRoom.objects.all(),
        write_only=True
    )
    teacher_id = serializers.PrimaryKeyRelatedField(
        source='teacher',
        queryset=Teacher.objects.all(),
        write_only=True
    )

    class Meta:
        model = TimetableEntry
        fields = "__all__"


# -------------------------
# TIMETABLE SERIALIZER
# -------------------------

class TimetableSerializer(serializers.ModelSerializer):
    entries = TimetableEntrySerializer(many=True, read_only=True)

    class Meta:
        model = Timetable
        fields = "__all__"
