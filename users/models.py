from django.db import models
from django.contrib.auth.models import AbstractBaseUser,PermissionsMixin
from phonenumber_field.modelfields import PhoneNumberField
from .managers import UserManager


# Create your models here.
class User(AbstractBaseUser, PermissionsMixin):
    ADMIN = "Admin"
    TEACHER = "Teacher"
    STUDENT = "Student"

    MALE = "Male"
    FEMALE = "Female"
    OTHER = "Other"

    ROLE_CHOICES = [(ADMIN, ADMIN), (TEACHER, TEACHER), (STUDENT, STUDENT)]
    GENDER_CHOICES = [(MALE, MALE), (FEMALE, FEMALE), (OTHER, OTHER)]

    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=200)
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES)
    phone_number = PhoneNumberField()

    is_verified = models.BooleanField(default=False)

    role = models.CharField(max_length=15, choices=ROLE_CHOICES, default=STUDENT)

    # needed for django admin
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)

    date_joined = models.DateTimeField(verbose_name="date joined", auto_now_add=True)
    last_login = models.DateTimeField(verbose_name="last login", auto_now=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name", "phone_number", "gender", "date_of_birth"]

    objects = UserManager()

    def __str__(self):
        return f"{self.id} - {self.full_name}"
