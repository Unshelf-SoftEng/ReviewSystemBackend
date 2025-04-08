from django import forms


class PasswordUpdateForm(forms.Form):
    new_password = forms.CharField(label='New Password', widget=forms.PasswordInput, min_length=8)
    confirm_password = forms.CharField(label='Confirm Password', widget=forms.PasswordInput)
