from django import forms
from django.contrib.auth import get_user_model

from .models import UserProfile


class UserProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ("timezone",  'maximum_daily_notifications')


class UserForm(forms.ModelForm):
    class Meta:
        model = get_user_model()
        fields = ('first_name', 'last_name', 'email')
