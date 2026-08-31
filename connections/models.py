from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MaxLengthValidator
from cryptography.fernet import Fernet
from django.conf import settings
import base64
import certifi
import ssl
import os
import logging
os.environ['SSL_CERT_FILE'] = certifi.where()


def get_fernet():
    """Get Fernet instance for encrypting/decrypting passwords."""
    key = settings.FERNET_KEY
    if not key:
        # Generate a key for development if not set
        key = base64.urlsafe_b64encode(b'hdfc-data-quality-tool-dev-key!!')
    if isinstance(key, str):
        key = key.encode()
    return Fernet(key)


class DataConnection(models.Model):
    """Represents a connection to a database or file source/target."""

    CONNECTION_TYPES = [
        ('postgresql', 'PostgreSQL'),
        ('mysql', 'MySQL'),
        ('databricks', 'Databricks'),
        ('db2', 'DB2'),
        ('oracle', 'Oracle'),
        ('lakehouse', 'Lakehouse'),
        ('sqlserver', 'SQL Server'),
        ('csv', 'Flat File (CSV)'),
        ('parquet', 'Flat File (Parquet)'),
        ('excel', 'Flat File (Excel)'),
        ('text', 'Flat File (Text)'),
        ('azure_blob', 'Azure Blob Storage'),
    ]

    name = models.CharField(max_length=200, help_text='Friendly name for this connection')
    connection_type = models.CharField(max_length=20, choices=CONNECTION_TYPES)
    description = models.TextField(blank=True, validators=[MaxLengthValidator(1000)])

    # Database connection fields
    host = models.CharField(max_length=500, blank=True)
    port = models.IntegerField(null=True, blank=True)
    database_name = models.CharField(max_length=200, blank=True)
    username = models.CharField(max_length=200, blank=True)
    encrypted_password = models.BinaryField(blank=True, default=b'')
    driver = models.CharField(max_length=100, blank=True, help_text='Optional DBAPI driver override (e.g. cx_Oracle, oracledb, pyodbc)')

    # File connection fields
    file = models.FileField(upload_to='uploads/connections/', blank=True)

    # Metadata
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='connections')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    last_tested = models.DateTimeField(null=True, blank=True)
    last_test_success = models.BooleanField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Data Connection'

    def __str__(self):
        return f"{self.name} ({self.get_connection_type_display()})"

    @property
    def is_database(self):
        return self.connection_type in ('postgresql', 'mysql', 'databricks', 'db2', 'oracle', 'lakehouse', 'sqlserver')

    @property
    def is_file(self):
        return self.connection_type in ('csv', 'parquet', 'excel', 'text', 'flat_file', 'azure_blob')

    def set_password(self, raw_password):
        """Encrypt and store the database password."""
        if raw_password:
            f = get_fernet()
            self.encrypted_password = f.encrypt(raw_password.encode())

    def get_password(self):
        """Decrypt and return the database password."""
        if self.encrypted_password:
            try:
                f = get_fernet()
                return f.decrypt(bytes(self.encrypted_password)).decode()
            except Exception:
                return ''
        return ''

    def get_connection_string(self):
        """Build SQLAlchemy connection string with URL-encoded credentials."""
        import urllib.parse
        encoded_username = urllib.parse.quote_plus(self.username)
        encoded_password = urllib.parse.quote_plus(self.get_password())
        
        if self.connection_type == 'postgresql':
            return f"postgresql+psycopg2://{encoded_username}:{encoded_password}@{self.host}:{self.port or 5432}/{self.database_name}"
        elif self.connection_type == 'mysql':
            return f"mysql+pymysql://{encoded_username}:{encoded_password}@{self.host}:{self.port or 3306}/{self.database_name}"
        elif self.connection_type == 'databricks':
            return (
                f"databricks://token:{encoded_password}"
                f"@{self.host}"
                f"?http_path={self.database_name}"
            )
        elif self.connection_type == 'db2':
            driver = self.driver.strip() if self.driver else 'ibm_db'
            if 'pyodbc' in driver.lower():
                driver_name = "IBM DB2"
                # If odbc attributes are added in the driver input, parse them (e.g. pyodbc;DRIVER={IBM DB2})
                parts = driver.split(';')
                for part in parts:
                    if part.upper().startswith('DRIVER='):
                        driver_name = part.split('=', 1)[1].strip()
                        if driver_name.startswith('{') and driver_name.endswith('}'):
                            driver_name = driver_name[1:-1]
                
                # Wrap custom driver name in curly braces unless it's a direct library path (.so or .dll)
                if '/' in driver_name or '.so' in driver_name or '.dll' in driver_name or driver_name.startswith('{'):
                    pass
                else:
                    driver_name = f"{{{driver_name}}}"
                
                odbc_conn_str = (
                    f"DRIVER={driver_name};"
                    f"HOSTNAME={self.host};"
                    f"PORT={self.port or 50000};"
                    f"DATABASE={self.database_name};"
                    f"PROTOCOL=TCPIP;"
                    f"UID={self.username};"
                    f"PWD={self.get_password()};"
                )
                quoted_odbc = urllib.parse.quote_plus(odbc_conn_str)
                return f"db2+pyodbc:///?odbc_connect={quoted_odbc}"
            elif driver.lower() in ('ibm_db', 'ibm_db_sa', 'db2', ''):
                return f"db2://{encoded_username}:{encoded_password}@{self.host}:{self.port or 50000}/{self.database_name}"
            else:
                return f"db2+{driver}://{encoded_username}:{encoded_password}@{self.host}:{self.port or 50000}/{self.database_name}"
        elif self.connection_type == 'oracle':
            driver = self.driver.strip() if self.driver else 'oracledb'
            return f"oracle+{driver}://{encoded_username}:{encoded_password}@{self.host}:{self.port or 1521}/{self.database_name}"
        elif self.connection_type == 'lakehouse':
            driver = self.driver.strip() if self.driver else 'pyodbc'
            return f"{driver}://{encoded_username}:{encoded_password}@{self.host}:{self.port or 443}/{self.database_name}"
        elif self.connection_type == 'sqlserver':
            driver = self.driver.strip() if self.driver else 'ODBC Driver 17 for SQL Server'
            if 'pymssql' in driver.lower():
                return f"mssql+pymssql://{encoded_username}:{encoded_password}@{self.host}:{self.port or 1433}/{self.database_name}"
            else:
                quoted_driver = urllib.parse.quote_plus(driver)
                return f"mssql+pyodbc://{encoded_username}:{encoded_password}@{self.host}:{self.port or 1433}/{self.database_name}?driver={quoted_driver}"
        return None
