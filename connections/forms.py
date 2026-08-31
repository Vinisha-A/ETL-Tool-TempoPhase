from django import forms
from .models import DataConnection


class DataConnectionForm(forms.ModelForm):
    """Form for creating/editing data connections."""
    password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Database password',
        })
    )

    class Meta:
        model = DataConnection
        fields = ['name', 'connection_type', 'description', 'host', 'port',
                  'database_name', 'username', 'driver', 'file']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Production PostgreSQL'}),
            'connection_type': forms.Select(attrs={'class': 'form-control', 'id': 'conn-type-select'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Optional description', 'maxlength': '1000'}),
            'host': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., db-server.hdfcbank.com'}),
            'port': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '5432'}),
            'database_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Database name'}),
            'username': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Database username'}),
            'driver': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., cx_Oracle, oracledb, pyodbc'}),
            'file': forms.FileInput(attrs={'class': 'form-control', 'accept': '.csv,.parquet,.parq,.xlsx,.xls,.txt'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        connection_type = cleaned_data.get('connection_type')

        if connection_type in ('postgresql', 'mysql', 'db2', 'sqlserver'):
            if not cleaned_data.get('host'):
                self.add_error('host', f'Host is required for {connection_type.upper()}.')
            if not cleaned_data.get('database_name'):
                self.add_error('database_name', f'Database name is required for {connection_type.upper()}.')
            if not cleaned_data.get('username'):
                self.add_error('username', f'Username is required for {connection_type.upper()}.')
            if not cleaned_data.get('password') and not self.instance.encrypted_password:
                self.add_error('password', f'Password is required for {connection_type.upper()}.')
        elif connection_type in ('oracle', 'lakehouse'):
            if not cleaned_data.get('host'):
                self.add_error('host', f'Host is required for {connection_type.title()}.')
            if not cleaned_data.get('database_name'):
                self.add_error('database_name', f'Database name is required for {connection_type.title()}.')
            if not cleaned_data.get('username'):
                self.add_error('username', f'Username is required for {connection_type.title()}.')
            if not cleaned_data.get('password') and not self.instance.encrypted_password:
                self.add_error('password', f'Password is required for {connection_type.title()}.')
        elif connection_type == 'databricks':
            if not cleaned_data.get('host'):
                self.add_error('host', 'Server Hostname is required for Databricks.')
            if not cleaned_data.get('database_name'):
                self.add_error('database_name', 'HTTP Path is required for Databricks.')
            if not cleaned_data.get('password') and not self.instance.encrypted_password:
                self.add_error('password', 'Access Token is required for Databricks.')
        elif connection_type in ('csv', 'parquet', 'excel', 'text'):
            if not cleaned_data.get('file') and not self.instance.file:
                self.add_error('file', 'File upload is required.')
        elif connection_type == 'azure_blob':
            if not cleaned_data.get('host'):
                self.add_error('host', 'Folder Path / Prefix is required for Azure Blob.')
            if not cleaned_data.get('database_name'):
                self.add_error('database_name', 'Container Name is required for Azure Blob.')

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        password = self.cleaned_data.get('password')
        if password:
            instance.set_password(password)
        if commit:
            instance.save()
        return instance
