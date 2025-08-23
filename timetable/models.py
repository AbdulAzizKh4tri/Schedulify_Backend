from django.db import models
from users.models import User

# Create your models here.
TIME_SLOTS = 48
MAXIMUM_WORK_LOAD = 18

SHIFT_1 = "111111111111111111111111111111111111000000000000"
SHIFT_2 = "000000000000111111111111111111111111111111111111"
BOTH_SHIFTS = "1" * TIME_SLOTS

class Department(models.Model):
    name = models.CharField(max_length=255)

    def __str__(self):
        return self.name

class Subject(models.Model):
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=20)
    lectures_per_week = models.PositiveSmallIntegerField()
    labs_per_week = models.PositiveSmallIntegerField()
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name="subjects")

    def __str__(self):
        return self.name

class Teacher(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="teacher_profile")
    name = models.CharField(max_length=255)
    availability = models.CharField(max_length=TIME_SLOTS, default=SHIFT_2)
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name="teachers")
    max_workload = models.PositiveSmallIntegerField()

    def __str__(self):
        return self.name

class ClassRoom(models.Model):
    number = models.CharField(max_length=10, unique=True)
    availability = models.CharField(max_length=TIME_SLOTS, default=BOTH_SHIFTS)

    def __str__(self):
        return self.number

class Division(models.Model):
    name = models.CharField(max_length=255)
    semester = models.PositiveSmallIntegerField()
    subjects = models.ManyToManyField(Subject)
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name="divisions")
    availability = models.CharField(max_length=TIME_SLOTS, default=SHIFT_2)

    def __str__(self):
        return self.name

class Preference(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="subject_preferences")
    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE,related_name="teacher_preferences")
    score = models.PositiveSmallIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return str(self.subject) + " " + str(self.teacher) + " " + str(self.score)
    
    class Meta:
        ordering = ('score',)

class Timetable(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)

class TimetableEntry(models.Model):
    division = models.ForeignKey(Division, on_delete=models.CASCADE, related_name="timetables")
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE)
    classroom = models.ForeignKey(ClassRoom, on_delete=models.CASCADE)
    time_slot = models.PositiveSmallIntegerField()
    session_type = models.CharField(max_length=20)
    generated = models.BooleanField(default=True)
    timetable = models.ForeignKey(Timetable, on_delete=models.CASCADE, related_name="entries")

    def __str__(self):
        return f"division {self.division} to be taught {self.subject} by {self.teacher} at {self.time_slot} in classroom {self.classroom}"

    class Meta:
        unique_together = [
            ('division', 'time_slot'),
            ('teacher', 'time_slot'),
            ('classroom', 'time_slot'),
        ]