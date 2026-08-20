from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MaxLengthValidator
from connections.models import DataConnection


class Mapping(models.Model):
    """Source-to-Target mapping definition."""

    DATE_FILTER_TYPES = [
        ('none', 'No Filter'),
        ('range', 'Date Range'),
        ('specific', 'Specific Date'),
    ]

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, validators=[MaxLengthValidator(1000)])

    # Source
    source_connection = models.ForeignKey(
        DataConnection, on_delete=models.CASCADE, related_name='source_mappings'
    )
    source_catalog = models.CharField(max_length=200, blank=True)
    source_schema = models.CharField(max_length=200, blank=True)
    source_table = models.CharField(max_length=200)

    # Target
    target_connection = models.ForeignKey(
        DataConnection, on_delete=models.CASCADE, related_name='target_mappings'
    )
    target_catalog = models.CharField(max_length=200, blank=True)
    target_schema = models.CharField(max_length=200, blank=True)
    target_table = models.CharField(max_length=200)

    # Date Filter
    date_filter_column = models.CharField(max_length=200, blank=True)
    date_filter_type = models.CharField(max_length=20, choices=DATE_FILTER_TYPES, default='none')
    date_filter_start = models.CharField(max_length=50, null=True, blank=True)
    date_filter_end = models.CharField(max_length=50, null=True, blank=True)
    date_operator = models.CharField(max_length=5, default='=')

    # Separate Date Filters
    source_date_column = models.CharField(max_length=200, blank=True)
    source_date_filter_type = models.CharField(max_length=20, choices=DATE_FILTER_TYPES, default='none')
    source_date_filter_start = models.CharField(max_length=50, null=True, blank=True)
    source_date_filter_end = models.CharField(max_length=50, null=True, blank=True)
    source_date_operator = models.CharField(max_length=5, default='=')
    source_date_range_operator_start = models.CharField(max_length=5, default='>=')
    source_date_range_operator_end = models.CharField(max_length=5, default='<=')

    target_date_column = models.CharField(max_length=200, blank=True)
    target_date_filter_type = models.CharField(max_length=20, choices=DATE_FILTER_TYPES, default='none')
    target_date_filter_start = models.CharField(max_length=50, null=True, blank=True)
    target_date_filter_end = models.CharField(max_length=50, null=True, blank=True)
    target_date_operator = models.CharField(max_length=5, default='=')
    target_date_range_operator_start = models.CharField(max_length=5, default='>=')
    target_date_range_operator_end = models.CharField(max_length=5, default='<=')

    # ETL Configuration
    query_type = models.CharField(
        max_length=20,
        choices=[('table', 'Table Select'), ('custom_query', 'Custom Query')],
        default='table'
    )
    custom_query = models.TextField(blank=True, null=True)
    filter_column = models.CharField(max_length=200, blank=True, null=True)
    filter_condition = models.CharField(max_length=500, blank=True, null=True)
    load_mode = models.CharField(
        max_length=20,
        choices=[('truncate', 'Truncate Load'), ('incremental', 'Incremental Load')],
        default='truncate'
    )
    incremental_column = models.CharField(max_length=200, blank=True, null=True)
    incremental_value = models.CharField(max_length=200, blank=True, null=True)

    # Metadata
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='mappings')
    created_at = models.DateTimeField(auto_now_add=True)
    modified_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='modified_mappings')
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    is_draft = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Mapping'

    def __str__(self):
        return f"{self.name}: {self.source_table} → {self.target_table}"


class ColumnMapping(models.Model):
    """Maps individual columns between source and target."""

    mapping = models.ForeignKey(Mapping, on_delete=models.CASCADE, related_name='column_mappings')
    source_column = models.CharField(max_length=200)
    source_datatype = models.CharField(max_length=100, blank=True)
    target_column = models.CharField(max_length=200)
    target_datatype = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.source_column} → {self.target_column}"


class ValidationRule(models.Model):
    """Validation operation to apply on a column mapping."""

    OPERATION_CHOICES = [
        ('count', 'Count'),
        ('min', 'Minimum'),
        ('max', 'Maximum'),
        ('sum', 'Sum'),
        ('distinct_count', 'Distinct Count'),
        ('null_check', 'Null Check'),
        ('duplicate_check', 'Duplicate Check'),
        ('data_type_check', 'Data Type Check'),
        ('row_count', 'Row Count Match'),
        ('avg', 'Average'),
        ('length_sum_check', 'Length Sum Check'),
        ('sum_length', 'Sum Length'),
        ('regex_check', 'Regex Check'),
        ('unique_check', 'Unique Check'),
        ('range_check', 'Range Check'),
        ('min_date', 'Min Date'),
        ('max_date', 'Max Date'),
        ('pattern_match', 'Pattern Match'),
        ('std_dev', 'Standard Deviation'),
        ('variance', 'Variance'),
        ('median', 'Median'),
        ('mode', 'Mode'),
    ]

    column_mapping = models.ForeignKey(
        ColumnMapping, on_delete=models.CASCADE, related_name='rules'
    )
    operation = models.CharField(max_length=30, choices=OPERATION_CHOICES)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['operation']
        unique_together = ['column_mapping', 'operation']

    def __str__(self):
        return f"{self.column_mapping} — {self.get_operation_display()}"


class PipelineGroup(models.Model):
    """User-defined groups for categorizing pipelines."""
    name = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class PipelineGroupAssignment(models.Model):
    """Assigns a pipeline (Mapping) to a custom PipelineGroup."""
    group = models.ForeignKey(PipelineGroup, on_delete=models.CASCADE, related_name='assignments')
    mapping = models.OneToOneField(Mapping, on_delete=models.CASCADE, related_name='group_assignment')
    assigned_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.mapping.name} -> {self.group.name}"



