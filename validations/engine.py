"""
ETL Engine — Core logic for executing Extract, Transform, Load workflows.
Extracts source datasets, applies filtering, transforms schemas, and writes to target systems.
"""
import logging
import time
import pandas as pd
from django.utils import timezone
from sqlalchemy import text
from connections.connector import ConnectorEngine
from .models import ValidationRun, ValidationResult

logger = logging.getLogger('validations')


class ValidationEngine:
    """Execute ETL load operations between source and target."""

    def __init__(self, validation_run):
        self.run = validation_run
        self.mapping = validation_run.mapping
        self.source_engine = ConnectorEngine(self.mapping.source_connection)
        self.target_engine = ConnectorEngine(self.mapping.target_connection)

    def execute(self):
        """Execute ETL mapping pipeline (Extract, Transform, Load)."""
        self.run.status = 'running'
        self.run.started_at = timezone.now()
        self.run.progress = 10
        self.run.save()

        try:
            # 1. Extraction Phase
            df = self._extract_data()
            self.run.records_extracted = len(df)
            self.run.progress = 40
            self.run.save(update_fields=['records_extracted', 'progress'])

            # Log step 1: Extract Data
            ValidationResult.objects.create(
                run=self.run,
                source_column='Source Data',
                target_column='Extracted',
                operation='extraction',
                source_value=str(len(df)),
                target_value='SUCCESS',
                is_match=True,
                difference='0',
                details={'info': 'Successfully extracted data from source'}
            )

            # 2. Transformation / Mapping Phase
            df = self._transform_data(df)
            self.run.progress = 60
            self.run.save(update_fields=['progress'])

            # Log step 2: Target action
            ValidationResult.objects.create(
                run=self.run,
                source_column='Schema Mapping',
                target_column='Prepared',
                operation='target_preparation',
                source_value=self.mapping.get_load_mode_display(),
                target_value='SUCCESS',
                is_match=True,
                difference='0',
                details={'info': 'Successfully prepared target mapping schema'}
            )

            # 3. Load Phase
            loaded_count = self._load_data(df)
            self.run.records_loaded = loaded_count
            self.run.progress = 90
            self.run.save(update_fields=['records_loaded', 'progress'])

            # Log step 3: Load Data
            ValidationResult.objects.create(
                run=self.run,
                source_column='Target Data',
                target_column='Loaded',
                operation='loading',
                source_value=str(loaded_count),
                target_value='SUCCESS',
                is_match=True,
                difference='0',
                details={'info': f'Successfully loaded {loaded_count} rows into target'}
            )

            self.run.status = 'completed'
            self.run.completed_at = timezone.now()
            self.run.progress = 100
            self.run.total_checks = 3
            self.run.passed_checks = 3
            self.run.failed_checks = 0
            self.run.save()

            # Send automated email notification
            try:
                from notifications.email_service import send_validation_email
                send_validation_email(self.run)
            except Exception as email_err:
                logger.error(f"Failed to trigger email notification: {email_err}")

        except Exception as e:
            logger.error(f"ETL pipeline execution failed: {e}", exc_info=True)
            self.run.status = 'failed'
            self.run.error_message = str(e)
            self.run.completed_at = timezone.now()
            self.run.save()

            # Log failure details using ValidationResult if possible
            try:
                step_name = 'extraction'
                if hasattr(self.run, 'records_extracted') and self.run.records_extracted > 0:
                    step_name = 'loading'
                ValidationResult.objects.create(
                    run=self.run,
                    source_column='Pipeline Execution',
                    target_column='Failure',
                    operation=step_name,
                    source_value='ERROR',
                    target_value='FAILED',
                    is_match=False,
                    difference=str(e)[:250]
                )
            except Exception:
                pass

            # Send automated email notification on failure
            try:
                from notifications.email_service import send_validation_email
                send_validation_email(self.run)
            except Exception as email_err:
                logger.error(f"Failed to trigger email notification on run failure: {email_err}")
            raise

    def _extract_data(self):
        """Extract data from source connection."""
        if self.source_engine.is_mocked():
            logger.info("Generating mock source data.")
            cols = [cm.source_column for cm in self.mapping.column_mappings.all()] or ['id', 'name', 'value', 'created_at']
            mock_data = []
            for i in range(15):
                row = {}
                for col in cols:
                    if 'id' in col.lower():
                        row[col] = i + 1
                    elif 'date' in col.lower() or 'time' in col.lower() or 'created' in col.lower():
                        row[col] = '2026-08-19'
                    elif 'value' in col.lower() or 'amount' in col.lower() or 'count' in col.lower():
                        row[col] = (i + 1) * 10.0
                    else:
                        row[col] = f"Mock {col} {i + 1}"
                mock_data.append(row)
            return pd.DataFrame(mock_data)

        if self.mapping.query_type == 'custom_query':
            logger.info("Executing custom source query extraction.")
            query = self.mapping.custom_query
            if not query:
                raise ValueError("Custom query is empty")
            return self.source_engine.execute_query(query)

        # Table select mode
        logger.info(f"Extracting table data from: {self.mapping.source_table}")
        cols = [cm.source_column for cm in self.mapping.column_mappings.all()]
        
        if self.source_engine.connection.is_file:
            df = self.source_engine.read_file(table=self.mapping.source_table)
            if df is None:
                raise ValueError(f"Failed to read file from source: {self.mapping.source_table}")
            
            # Select columns
            if cols:
                df = df[[c for c in cols if c in df.columns]]
            
            # Custom filter
            if self.mapping.filter_column and self.mapping.filter_condition:
                col = self.mapping.filter_column
                cond = self.mapping.filter_condition.strip()
                if col in df.columns:
                    try:
                        if not any(cond.startswith(op) for op in ('=', '>', '<', '!', 'like', 'in', 'LIKE', 'IN')):
                            expr = f"`{col}` == {cond}"
                        else:
                            clean_cond = cond
                            if cond.startswith('='):
                                clean_cond = '==' + cond[1:]
                            expr = f"`{col}` {clean_cond}"
                        df = df.query(expr)
                    except Exception as fe:
                        logger.warning(f"Failed to filter pandas dataframe using query '{expr}': {fe}")
            return df

        # Database extraction query construction
        full_table = self.source_engine._build_full_table_name(
            self.mapping.source_table,
            schema=self.mapping.source_schema,
            catalog=self.mapping.source_catalog
        )

        select_cols = ", ".join(self.source_engine._quote_identifier(c) for c in cols) if cols else "*"
        conditions = []
        params = {}

        # Date Filters
        src_date_column = self.mapping.source_date_column if self.mapping.source_date_filter_type != 'none' else None
        src_date_start = str(self.run.source_date_filter_start) if self.run.source_date_filter_start else None
        src_date_end = str(self.run.source_date_filter_end) if self.run.source_date_filter_end else None
        src_date_operator = getattr(self.mapping, 'source_date_operator', '=') if self.mapping.source_date_filter_type == 'specific' else None

        if src_date_column:
            q_date_col = self.source_engine._quote_identifier(src_date_column)
            if src_date_operator:
                if src_date_start:
                    conditions.append(f"{q_date_col} {src_date_operator} :date_start")
                    params['date_start'] = src_date_start
            else:
                if src_date_start:
                    conditions.append(f"{q_date_col} >= :date_start")
                    params['date_start'] = src_date_start
                if src_date_end:
                    conditions.append(f"{q_date_col} <= :date_end")
                    params['date_end'] = src_date_end

        # Option A Filter Column & Condition
        if self.mapping.filter_column and self.mapping.filter_condition:
            q_filter_col = self.source_engine._quote_identifier(self.mapping.filter_column)
            cond = self.mapping.filter_condition.strip()
            if not any(cond.startswith(op) for op in ('=', '>', '<', '!', 'like', 'in', 'LIKE', 'IN')):
                cond = f"= {cond}"
            conditions.append(f"{q_filter_col} {cond}")

        # Incremental Load strategy
        if self.mapping.load_mode == 'incremental' and self.mapping.incremental_column:
            inc_col = self.mapping.incremental_column
            q_inc_col = self.source_engine._quote_identifier(inc_col)
            
            start_val = self.mapping.incremental_value
            if not start_val:
                try:
                    target_map_col = next(
                        (cm.target_column for cm in self.mapping.column_mappings.all() if cm.source_column.lower() == inc_col.lower()),
                        inc_col
                    )
                    start_val = self._get_target_max_value(target_map_col)
                except Exception as ex:
                    logger.warning(f"Could not derive incremental value from target: {ex}")
                    start_val = None

            if start_val:
                conditions.append(f"{q_inc_col} > :inc_start_val")
                params['inc_start_val'] = start_val
                logger.info(f"Applying incremental filter: {inc_col} > {start_val}")

        where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
        query = f"SELECT {select_cols} FROM {full_table}{where_clause}"
        return self.source_engine.execute_query(query, params)

    def _get_target_max_value(self, column):
        """Get the maximum value of a column in target to start incremental load."""
        if self.target_engine.is_mocked():
            return None
        if self.target_engine.connection.is_file:
            df = self.target_engine.read_file(table=self.mapping.target_table)
            if df is not None and column in df.columns and len(df) > 0:
                return df[column].max()
            return None

        # Database
        full_table = self.target_engine._build_full_table_name(
            self.mapping.target_table,
            schema=self.mapping.target_schema,
            catalog=self.mapping.target_catalog
        )
        q_col = self.target_engine._quote_identifier(column)
        query = f"SELECT MAX({q_col}) AS max_val FROM {full_table}"
        try:
            df = self.target_engine.execute_query(query)
            if df is not None and not df.empty:
                return df.iloc[0]['max_val']
        except Exception as e:
            logger.warning(f"Error querying target max value: {e}")
        return None

    def _transform_data(self, df):
        """Rename columns according to mapping definitions and drop unmapped columns if manual mapping."""
        if df is None:
            return None
        
        rename_dict = {}
        target_cols = []
        for cm in self.mapping.column_mappings.all():
            rename_dict[cm.source_column] = cm.target_column
            target_cols.append(cm.target_column)

        # Rename
        df = df.rename(columns=rename_dict)

        # If manual mappings are defined, drop any source columns not in mappings
        if rename_dict:
            df = df[[col for col in target_cols if col in df.columns]]
            
        return df

    def _load_data(self, df):
        """Load data into target connection."""
        if df is None:
            return 0
        if len(df) == 0:
            logger.info("DataFrame is empty. Nothing to write to target.")
            return 0

        mode = 'replace' if self.mapping.load_mode == 'truncate' else 'append'
        
        return self.target_engine.write_data(
            df,
            schema=self.mapping.target_schema,
            table=self.mapping.target_table,
            catalog=self.mapping.target_catalog if self.mapping.target_connection.connection_type == 'databricks' else None,
            mode=mode
        )
