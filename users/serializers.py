from rest_framework import serializers
from .models import User

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = "__all__"
        extra_kwargs = {"password": {"write_only": True, "required": False}}

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        user = super().create(validated_data)
        if password:
            user.set_password(password)
            user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        user = super().update(instance, validated_data)
        if password:
            user.set_password(password)
            user.save()
        return user

class UserLiteSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserSerializer.Meta.model
        fields = ["id", "full_name", "email"]


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)