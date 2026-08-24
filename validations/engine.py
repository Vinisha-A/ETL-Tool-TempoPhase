"""
ETL Engine — Core logic for executing Extract, Transform, Load workflows.
Extracts source datasets in batches/chunks, validates query safety, transforms schemas, and writes to target systems.
"""
import logging
import time
import re
import pandas as pd
from django.utils import timezone
from sqlalchemy import text
from connections.connector import ConnectorEngine
from .models import ETLRun, ETLResult

logger = logging.getLogger('validations')


class ETLEngine:
    """Execute ETL load operations between source and target."""

    def __init__(self, etl_run):
        self.run = etl_run
        self.mapping = etl_run.mapping
        self.source_engine = ConnectorEngine(self.mapping.source_connection)
        self.target_engine = ConnectorEngine(self.mapping.target_connection)

    def execute(self):
        """Execute ETL mapping pipeline (Extract, Transform, Load) in batches."""
        self.run.status = 'running'
        self.run.started_at = timezone.now()
        self.run.progress = 10
        self.run.save()

        total_extracted = 0
        total_loaded = 0
        total_failed = 0
        first_batch = True
        batch_size = self.mapping.batch_size or 10000

        try:
            # 1. Extraction, Transformation, and Load Loop
            chunk_generator = self._extract_data_generator(batch_size)
            
            for chunk in chunk_generator:
                if chunk is None or chunk.empty:
                    continue
                
                chunk_len = len(chunk)
                total_extracted += chunk_len
                
                # Progress increment (10% to 70%)
                current_progress = min(70, 10 + int((total_extracted / (total_extracted + batch_size)) * 50))
                self.run.progress = current_progress
                self.run.records_extracted = total_extracted
                self.run.save(update_fields=['records_extracted', 'progress'])

                # 2. Transformation
                try:
                    transformed_chunk = self._transform_data(chunk)
                except Exception as te:
                    logger.error(f"Transformation failed on batch: {te}")
                    total_failed += chunk_len
                    self.run.records_loaded = total_loaded
                    self.run.save(update_fields=['records_loaded'])
                    raise ValueError(f"Transformation failed: {te}")

                # 3. Load Phase (Write Chunk)
                try:
                    mode = 'replace' if (first_batch and self.mapping.load_mode == 'truncate') else 'append'
                    loaded_count = self._load_data(transformed_chunk, mode)
                    total_loaded += loaded_count
                    first_batch = False
                except Exception as le:
                    logger.error(f"Loading failed on batch: {le}")
                    total_failed += chunk_len
                    self.run.records_loaded = total_loaded
                    self.run.save(update_fields=['records_loaded'])
                    raise ValueError(f"Loading failed: {le}")

            # Update final execution status
            self.run.records_extracted = total_extracted
            self.run.records_loaded = total_loaded
            self.run.progress = 90
            self.run.save(update_fields=['records_extracted', 'records_loaded', 'progress'])

            # Log step 1: Extract Data
            ETLResult.objects.create(
                run=self.run,
                source_column='Source Data',
                target_column='Extracted',
                operation='extraction',
                source_value=str(total_extracted),
                target_value='SUCCESS',
                is_match=True,
                difference='0',
                details={'info': f'Successfully extracted {total_extracted} rows from source'}
            )

            # Log step 2: Target action
            ETLResult.objects.create(
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

            # Log step 3: Load Data
            ETLResult.objects.create(
                run=self.run,
                source_column='Target Data',
                target_column='Loaded',
                operation='loading',
                source_value=str(total_loaded),
                target_value='SUCCESS',
                is_match=True,
                difference='0',
                details={'info': f'Successfully loaded {total_loaded} rows into target'}
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

            # Log failure details using ETLResult if possible
            try:
                step_name = 'extraction'
                if hasattr(self.run, 'records_extracted') and self.run.records_extracted > 0:
                    step_name = 'loading'
                ETLResult.objects.create(
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

    def _validate_readonly_query(self, query):
        """Verify custom SQL queries are read-only and don't contain destructive operations."""
        # Strip comments to prevent bypass checks inside comments
        clean_query = re.sub(r'--.*$', '', query, flags=re.MULTILINE)
        clean_query = re.sub(r'/\*.*?\*/', '', clean_query, flags=re.DOTALL)

        forbidden_pattern = re.compile(
            r'\b(insert|update|delete|drop|alter|truncate)\b',
            re.IGNORECASE
        )
        match = forbidden_pattern.search(clean_query)
        if match:
            raise ValueError(
                f"Destructive SQL operation detected in custom query: '{match.group(1).upper()}'. "
                f"Only read-only SELECT queries are allowed."
            )

    def _extract_data_generator(self, batch_size):
        """Extract data from source connection, returning a generator of DataFrames."""
        # Custom Query mode
        if self.mapping.query_type == 'custom_query':
            logger.info("Executing custom source query extraction in batches.")
            query = self.mapping.custom_query
            if not query:
                raise ValueError("Custom query is empty")
            self._validate_readonly_query(query)
            return self._execute_db_query_generator(query, {}, batch_size)

        # Mock connection handling
        if self.source_engine.is_mocked():
            logger.info("Generating mock source data batch.")
            yield self._generate_mock_data()
            return

        # File connection handling
        if self.source_engine.connection.is_file:
            logger.info(f"Extracting file data from: {self.mapping.source_table}")
            return self._read_file_generator(batch_size)

        # Database extraction query construction
        query, params = self._build_extraction_query()
        return self._execute_db_query_generator(query, params, batch_size)

    def _execute_db_query_generator(self, query, params, batch_size):
        """Yield DataFrame chunks directly from database."""
        db_type = str(self.mapping.source_connection.connection_type).strip().lower()

        if db_type == 'lakehouse':
            conn = self.source_engine.get_lakehouse_connection()
            conn.rollback = lambda *args, **kwargs: None
            try:
                df = pd.read_sql(query, conn, params=params)
                for i in range(0, len(df), batch_size):
                    yield df.iloc[i : i + batch_size]
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

        elif db_type == 'db2':
            import pyodbc
            conn = self.source_engine.get_db2_pyodbc_connection()
            try:
                cursor = conn.cursor()
                param_values = []
                if params and isinstance(params, dict):
                    if ":date_start" in query:
                        query = query.replace(":date_start", "?")
                        param_values.append(params["date_start"])
                    if ":date_end" in query:
                        query = query.replace(":date_end", "?")
                        param_values.append(params["date_end"])
                
                if param_values:
                    cursor.execute(query, param_values)
                else:
                    cursor.execute(query)
                
                columns = [col[0] for col in cursor.description]
                
                while True:
                    rows = []
                    for _ in range(batch_size):
                        try:
                            row = cursor.fetchone()
                            if row is None:
                                break
                            rows.append(tuple(row))
                        except pyodbc.ProgrammingError:
                            break
                        except Exception as e:
                            logger.error(f"DB2 row fetch error: {e}")
                            break
                    if not rows:
                        break
                    yield pd.DataFrame(rows, columns=columns)
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

        else:
            engine = self.source_engine.get_engine()
            with engine.connect() as conn:
                for chunk in pd.read_sql(text(query), conn, params=params, chunksize=batch_size):
                    yield chunk

    def _read_file_generator(self, batch_size):
        """Yield DataFrame chunks from file sources."""
        df = self.source_engine.read_file(table=self.mapping.source_table)
        if df is None:
            raise ValueError(f"Failed to read file from source: {self.mapping.source_table}")

        # Apply Column Selection
        cols = [cm.source_column for cm in self.mapping.column_mappings.all()]
        if cols:
            df = df[[c for c in cols if c in df.columns]]

        # Apply Custom filter
        if self.mapping.filter_column and self.mapping.filter_condition:
            col = self.mapping.filter_column
            cond = self.mapping.filter_condition.strip()
            if col in df.columns:
                try:
                    if not any(cond.startswith(op) for op in ('=', '>', '<', '!', 'like', 'in', 'LIKE', 'IN')):
                        # Wrap condition value in quotes if it's a string/date and not quoted
                        if not (cond.startswith("'") or cond.startswith('"') or cond.replace('.', '', 1).isdigit()):
                            cond = f"'{cond}'"
                        expr = f"`{col}` == {cond}"
                    else:
                        clean_cond = cond
                        if cond.startswith('='):
                            val = cond[1:].strip()
                            if not (val.startswith("'") or val.startswith('"') or val.replace('.', '', 1).isdigit()):
                                val = f"'{val}'"
                            clean_cond = '==' + val
                        else:
                            # Handle >, <, >=, <=
                            for op in ('>=', '<=', '>', '<', '!='):
                                if cond.startswith(op):
                                    val = cond[len(op):].strip()
                                    if not (val.startswith("'") or val.startswith('"') or val.replace('.', '', 1).isdigit()):
                                        val = f"'{val}'"
                                    clean_cond = op + val
                                    break
                        expr = f"`{col}` {clean_cond}"
                    df = df.query(expr)
                except Exception as fe:
                    logger.warning(f"Failed to filter pandas dataframe using query '{expr}': {fe}")

        for i in range(0, len(df), batch_size):
            yield df.iloc[i : i + batch_size]

    def _build_extraction_query(self):
        """Construct SELECT statement with date filters and incremental filters."""
        cols = [cm.source_column for cm in self.mapping.column_mappings.all()]
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

        # Custom Filter Column & Condition
        if self.mapping.filter_column and self.mapping.filter_condition:
            q_filter_col = self.source_engine._quote_identifier(self.mapping.filter_column)
            cond = self.mapping.filter_condition.strip()
            
            # Extract operator and value
            operator = "="
            value = cond
            for op in ('>=', '<=', '!=', '>', '<', '=', 'like', 'in', 'LIKE', 'IN'):
                if cond.lower().startswith(op.lower()):
                    operator = op
                    value = cond[len(op):].strip()
                    break
            
            # Wrap strings and dates in quotes if they are not already quoted
            if not (value.startswith("'") or value.startswith('"') or value.replace('.', '', 1).isdigit()):
                value = f"'{value}'"
                
            conditions.append(f"{q_filter_col} {operator} {value}")

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
                # Wrap start_val if it is string or date and not quoted
                if not (start_val.startswith("'") or start_val.startswith('"') or start_val.replace('.', '', 1).isdigit()):
                    start_val_quoted = f"'{start_val}'"
                else:
                    start_val_quoted = start_val
                conditions.append(f"{q_inc_col} > {start_val_quoted}")
                logger.info(f"Applying incremental filter: {inc_col} > {start_val}")

        where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
        query = f"SELECT {select_cols} FROM {full_table}{where_clause}"
        return query, params

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
        """Rename columns according to mapping definitions and drop unmapped columns."""
        if df is None:
            return None
        
        rename_dict = {}
        target_cols = []
        for cm in self.mapping.column_mappings.all():
            rename_dict[cm.source_column] = cm.target_column
            target_cols.append(cm.target_column)

        df = df.rename(columns=rename_dict)

        if rename_dict:
            df = df[[col for col in target_cols if col in df.columns]]
            
        return df

    def _load_data(self, df, mode):
        """Load DataFrame chunk into target table."""
        return self.target_engine.write_data(
            df,
            schema=self.mapping.target_schema,
            table=self.mapping.target_table,
            catalog=self.mapping.target_catalog if self.mapping.target_connection.connection_type == 'databricks' else None,
            mode=mode
        )

    def _generate_mock_data(self):
        """Generate mock DataFrame for simulated runs."""
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
