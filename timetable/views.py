from django.http import JsonResponse
from django.shortcuts import render
from .timetablegenerator import generate_timetable
from .models import Timetable, TimetableEntry

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


