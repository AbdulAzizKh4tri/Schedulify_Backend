from django.http import JsonResponse
from django.shortcuts import render
from rest_framework import viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated


from .timetablegenerator import generate_timetable
from .permissions import IsAdmin, IsOwnerOrReadOnly, IsSelfOrReadOnly
from .models import ClassRoom, Department, Division, Preference, Subject, Teacher, Timetable, TimetableEntry
from .serializers import (ClassRoomSerializer, DepartmentSerializer, DivisionSerializer, PreferenceSerializer,
                          SubjectSerializer, TeacherSerializer, TimetableSerializer)

# Create your views here.

def generate(request):
    try:
        generate_timetable()
    except Exception as e:
        return JsonResponse({"message": "Unable to generate timetable " + str(e)},status=500)
    return JsonResponse({"message": "okay"})

def show(request, ttid, division):
    division_tt = TimetableEntry.objects.filter(timetable__id=ttid, division__name=division).order_by('time_slot')
    timetable_data = [
        {
            'division': entry.division.name,
            'subject': entry.subject.name,
            'teacher': entry.teacher.name,
            'classroom': entry.classroom.number,
            'time_slot': entry.time_slot,
            'session_type': entry.session_type
        }
        for entry in division_tt
    ]
    return JsonResponse({'data': timetable_data})


class ClassRoomViewSet(viewsets.ModelViewSet):
    queryset = ClassRoom.objects.all()
    serializer_class = ClassRoomSerializer

    def get_permissions(self):
        if self.action in ["update", "destroy", "create"]:
            return [IsAdmin()]
        return [AllowAny()]


class DepartmentViewSet(viewsets.ModelViewSet):
    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer
    def get_permissions(self):
        if self.action in ["update", "destroy", "create"]:
            return [IsAdmin()]
        return [AllowAny()]

class DivisionViewSet(viewsets.ModelViewSet):
    queryset = Division.objects.all()
    serializer_class = DivisionSerializer
    def get_permissions(self):
        if self.action in ["update", "destroy", "create"]:
            return [IsAdmin()]
        return [AllowAny()]

class PreferenceViewSet(viewsets.ModelViewSet):
    queryset = Preference.objects.all()
    serializer_class = PreferenceSerializer
    def get_permissions(self):
        return [IsOwnerOrReadOnly()]

class SubjectViewSet(viewsets.ModelViewSet):
    queryset = Subject.objects.all()
    serializer_class = SubjectSerializer
    def get_permissions(self):
        if self.action in ["update", "destroy", "create"]:
            return [IsAdmin()]
        return [AllowAny()]

class TeacherViewSet(viewsets.ModelViewSet):
    queryset = Teacher.objects.all()
    serializer_class = TeacherSerializer
    def get_permissions(self):
        return [IsSelfOrReadOnly()]

class TimetableViewSet(viewsets.ModelViewSet):
    queryset = Timetable.objects.all()
    serializer_class = TimetableSerializer
    def get_permissions(self):
        if self.action in ["update", "destroy", "create"]:
            return [IsAdmin()]
        return [AllowAny()]


