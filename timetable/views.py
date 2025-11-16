from django.http import JsonResponse
from django.shortcuts import render
from rest_framework import viewsets, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import transaction
from django.db.models import Max, Prefetch, Min, Sum
from django.db.models import Count
from rest_framework.decorators import api_view
from django.utils import timezone


from users.models import User
from users.serializers import UserLiteSerializer


from .timetablegenerator import generate_timetable
from .permissions import IsAdmin, IsOwnerOrReadOnly, IsSelfOrReadOnly, ReadOnly
from .models import (
    ClassRoom, Department, Division, Preference,
    Subject, Teacher, Timetable, TimetableEntry
)
from .serializers import (
    ClassRoomSerializer, DepartmentSerializer, DivisionSerializer,
    PreferenceSerializer, SubjectSerializer, TeacherSerializer,
    TimetableSerializer
)

from .mixins import CSVUploadMixin


class ClassRoomViewSet(CSVUploadMixin, viewsets.ModelViewSet):
    queryset = ClassRoom.objects.all()
    serializer_class = ClassRoomSerializer

    csv_key = "classrooms"
    csv_serializer = ClassRoomSerializer

    def get_permissions(self):
        if self.action in ["update", "destroy", "create", "csv_upload"]:
            return [IsAdmin()]
        return [AllowAny()]


class DepartmentViewSet(CSVUploadMixin, viewsets.ModelViewSet):
    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer

    csv_key = "departments"
    csv_serializer = DepartmentSerializer

    def get_permissions(self):
        if self.action in ["update", "destroy", "create", "csv_upload"]:
            return [IsAdmin()]
        return [AllowAny()]


class DivisionViewSet(CSVUploadMixin, viewsets.ModelViewSet):
    queryset = Division.objects.all()
    serializer_class = DivisionSerializer

    csv_key = "divisions"
    csv_serializer = DivisionSerializer

    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['semester', 'department']

    def get_permissions(self):
        if self.action in ["update", "destroy", "create", "csv_upload"]:
            return [IsAdmin()]
        return [AllowAny()]


class SubjectViewSet(CSVUploadMixin, viewsets.ModelViewSet):
    queryset = Subject.objects.all()
    serializer_class = SubjectSerializer

    csv_key = "subjects"
    csv_serializer = SubjectSerializer

    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['department']

    def get_permissions(self):
        if self.action in ["update", "destroy", "create", "csv_upload"]:
            return [IsAdmin()]
        return [AllowAny()]


class TeacherViewSet(CSVUploadMixin, viewsets.ModelViewSet):
    queryset = Teacher.objects.all()
    serializer_class = TeacherSerializer

    csv_key = "teachers"
    csv_serializer = TeacherSerializer

    @action(detail=False, methods=['get'])
    def users(self, request):
        users = User.objects.filter(role=User.TEACHER, teacher_profile__isnull=True)
        return Response({"users": UserLiteSerializer(users, many=True).data})
    
    @action(detail=False, methods=['get'])
    def preferences(self, request):
        """
        Returns teachers along with all their preferences, sorted by last preference update.
        """
        # Annotate teachers with the latest preference update
        teachers = Teacher.objects.annotate(
            last_pref_update=Max("teacher_preferences__updated_at")
        ).prefetch_related(
            Prefetch(
                "teacher_preferences",
                queryset=Preference.objects.select_related("subject").order_by("-score"),
                to_attr="all_preferences"
            )
        ).order_by("-last_pref_update")

        data = []
        for t in teachers:
            serializer = PreferenceSerializer(t.all_preferences, many=True)
            data.append({
                "id": t.id,
                "staff_id": t.staff_id,
                "name": t.user.full_name if t.user else None,
                "department": t.department.name if t.department else None,
                "preferences": serializer.data,
                "last_pref_update": t.last_pref_update
            })

        return Response(data)

    def get_permissions(self):
        return [IsSelfOrReadOnly()]


class PreferenceViewSet(CSVUploadMixin, viewsets.ModelViewSet):
    queryset = Preference.objects.all()
    serializer_class = PreferenceSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['teacher', 'subject']

    csv_key = "preferences"
    csv_serializer = PreferenceSerializer

    def get_permissions(self):
        return [IsOwnerOrReadOnly()]

    @action(detail=False, methods=['post'])
    def bulk_update(self, request):
        teacher_id = request.data.get("teacher_id")
        prefs_dict = request.data.get("preferences")

        if not teacher_id or not isinstance(prefs_dict, dict):
            return Response(
                {"detail": "teacher_id and preferences{} required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            teacher = Teacher.objects.get(id=teacher_id)
        except Teacher.DoesNotExist:
            return Response({"detail": "Teacher not found"}, status=404)

        # Convert dict keys to ints
        try:
            prefs = {int(k): int(v) for k, v in prefs_dict.items()}
        except ValueError:
            return Response({"detail": "Invalid subject_id or score type"}, status=400)

        subject_ids = list(prefs.keys())

        subjects = set(
            Subject.objects.filter(id__in=subject_ids).values_list("id", flat=True)
        )

        missing = set(subject_ids) - subjects
        if missing:
            return Response(
                {"detail": f"Invalid subject ids: {list(missing)}"},
                status=400
            )

        existing_qs = Preference.objects.filter(
            teacher=teacher,
            subject_id__in=subject_ids
        )
        existing_map = {p.subject_id: p for p in existing_qs}

        to_update = []
        to_create = []

        for subject_id, score in prefs.items():
            if not (1 <= score <= 10):
                return Response(
                    {"detail": f"Invalid score {score} for subject {subject_id}. Must be 1-10."},
                    status=400
                )

            if subject_id in existing_map:
                pref_obj = existing_map[subject_id]
                pref_obj.score = score
                to_update.append(pref_obj)
            else:
                to_create.append(
                    Preference(
                        teacher=teacher,
                        subject_id=subject_id,
                        score=score
                    )
                )

        with transaction.atomic():
            if to_update:
                for pref_obj in to_update:
                    pref_obj.updated_at = timezone.now()
                Preference.objects.bulk_update(to_update, ["score", "updated_at"])
            if to_create:
                Preference.objects.bulk_create(to_create)


        return Response({"detail": "Preferences updated successfully"})


class TimetableViewSet(viewsets.ModelViewSet):
    queryset = Timetable.objects.all()
    serializer_class = TimetableSerializer

    @action(detail=False, methods=['get'])
    def list_timetables(self, request):
        timetables = Timetable.objects.all()
        return JsonResponse({"timetables": [tt.serialize() for tt in timetables]})

    def get_permissions(self):
        return [ReadOnly()]


# -------------------------
# Standalone endpoints
# -------------------------
@api_view(['GET'])
def generate(request):
    timeout = request.GET.get("timeout")  # in seconds
    timeout = int(timeout) if timeout else None

    try:
        LP_output = generate_timetable(timeout=timeout)
    except TimeoutError as e:
        return JsonResponse({"message": str(e)}, status=408)
    except Exception as e:
        return JsonResponse({"message": "Unable to generate timetable: " + str(e)}, status=500)

    return JsonResponse({"data": LP_output})

@api_view(['GET'])
def summary(request):
    """Return dashboard summary"""
    # Departments summary
    departments = Department.objects.annotate(
        num_teachers=Count("teachers", distinct=True),
        num_subjects=Count("subjects", distinct=True)
    ).values("id", "name", "num_teachers", "num_subjects")

    # Subjects summary
    subjects = Subject.objects.annotate(
        num_teachers=Count("subject_preferences__teacher", distinct=True),
        num_divisions=Count("division", distinct=True)
    ).values("id", "name", "num_teachers", "num_divisions")

    # Total counts
    total = {
        "departments": Department.objects.count(),
        "teachers": Teacher.objects.count(),
        "subjects": Subject.objects.count(),
        "classrooms": ClassRoom.objects.count(),
        "divisions": Division.objects.count(),
    }

    return JsonResponse({
        "departments": list(departments),
        "subjects": list(subjects),
        "total": total
    })

@api_view(["GET"])
def teacher_mappings(request):
    timetable_id = request.GET.get("timetable_id")
    if not timetable_id:
        return Response({"detail": "timetable_id parameter required"}, status=400)

    try:
        timetable = Timetable.objects.get(id=timetable_id)
    except Timetable.DoesNotExist:
        return Response({"detail": "Timetable not found"}, status=404)

    # 1️⃣ Get unique entries per (teacher, subject, division)
    subquery = (
        TimetableEntry.objects.filter(timetable=timetable)
        .values("teacher_id", "subject_id", "division_id")
        .annotate(entry_id=Min("id"))
    )
    entries = TimetableEntry.objects.filter(
        id__in=[e["entry_id"] for e in subquery]
    ).select_related("teacher", "subject", "division")

    # 2️⃣ Build teacher map
    teachers_map = {}
    for e in entries:
        t_id = e.teacher.id
        s_id = e.subject.id

        if t_id not in teachers_map:
            teachers_map[t_id] = {
                "teacher_id": t_id,
                "teacher_name": e.teacher.user.full_name,
                "staff_id": getattr(e.teacher, "staff_id", "-"),
                "department": getattr(e.teacher.department, "name", "-") if e.teacher.department else "-",
                "subjects": {},
                "used_workload": 0,
                "max_workload": getattr(e.teacher, "max_workload", 0),
                "satisfaction": 0
            }

        teacher = teachers_map[t_id]

        # Workload
        lectures = getattr(e.subject, "lectures_per_week", 0)
        labs = getattr(e.subject, "labs_per_week", 0)
        teacher["used_workload"] += lectures + 2 * labs

        # Preference score per division
        pref = Preference.objects.filter(teacher=e.teacher, subject=e.subject).first()
        score = pref.score if pref else 0

        if s_id not in teacher["subjects"]:
            teacher["subjects"][s_id] = {
                "subject": e.subject.name,
                "divisions": [],
                "score_per_division": score
            }

        teacher["subjects"][s_id]["divisions"].append(e.division.name if e.division else "-")

    # 3️⃣ Calculate satisfaction per teacher
    for t in teachers_map.values():
        total_score = 0
        max_score = 0

        for sub in t["subjects"].values():
            num_divs = len(sub["divisions"])
            total_score += sub["score_per_division"] * num_divs
            max_score += 10 * num_divs

        t["satisfaction"] = (total_score / max_score) if max_score > 0 else 0

    # 4️⃣ Overall satisfaction = mean across all teachers
    overall_satisfaction = (
        sum(t["satisfaction"] for t in teachers_map.values()) / len(teachers_map)
        if teachers_map else 0
    )

    # 5️⃣ Format subjects as list for frontend
    teachers_list = [
        {**t, "subjects": list(t["subjects"].values())} for t in teachers_map.values()
    ]

    return Response({
        "overall_satisfaction": overall_satisfaction,
        "teachers": teachers_list
    })
