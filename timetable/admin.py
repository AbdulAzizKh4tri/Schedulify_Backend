from django.contrib import admin
from .models import Division, Subject, Teacher, ClassRoom, Preference, Timetable, Department, TimetableEntry

# Register your models here.
admin.site.register(Department)
admin.site.register(Division)
admin.site.register(Subject)
admin.site.register(Teacher)
admin.site.register(ClassRoom)
admin.site.register(Preference)
admin.site.register(Timetable)
admin.site.register(TimetableEntry)
