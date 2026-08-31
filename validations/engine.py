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


def values_differ(val1, val2):
    p_null1 = pd.isna(val1) or val1 is None
    p_null2 = pd.isna(val2) or val2 is None
    if p_null1 and p_null2:
        return False
    if p_null1 != p_null2:
        return True
    if type(val1) != type(val2):
        try:
            return float(val1) != float(val2)
        except Exception:
            pass
    return str(val1).strip() != str(val2).strip()


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
        total_inserted = 0
        total_updated = 0
        total_failed = 0
        first_batch = True
        batch_size = self.mapping.batch_size or 10000

        try:
            # 1. Execute Pre-SQL
            if self.mapping.pre_sql:
                try:
                    logger.info(f"Executing Pre-SQL on {self.mapping.pre_sql_location} connection.")
                    if self.mapping.pre_sql_location == 'source':
                        self.source_engine.execute_statement(self.mapping.pre_sql)
                    else:
                        self.target_engine.execute_statement(self.mapping.pre_sql)
                    
                    self.run.pre_sql_status = 'SUCCESS'
                    self.run.save(update_fields=['pre_sql_status'])
                    
                    ETLResult.objects.create(
                        run=self.run,
                        source_column='Pre-SQL',
                        target_column='Executed',
                        operation='pre_sql',
                        source_value=self.mapping.pre_sql_location,
                        target_value='SUCCESS',
                        is_match=True,
                        difference='0',
                        details={'info': f'Pre-SQL successfully executed on {self.mapping.pre_sql_location}'}
                    )
                except Exception as e:
                    self.run.pre_sql_status = 'FAILED'
                    self.run.error_message = f"Pre-SQL failed: {e}"
                    self.run.status = 'failed'
                    self.run.completed_at = timezone.now()
                    self.run.save()
                    
                    ETLResult.objects.create(
                        run=self.run,
                        source_column='Pre-SQL',
                        target_column='Failed',
                        operation='pre_sql',
                        source_value=self.mapping.pre_sql_location,
                        target_value='FAILED',
                        is_match=False,
                        difference=str(e)[:250]
                    )
                    raise ValueError(f"Pre-SQL failed: {e}")

            # 2. Extraction, Transformation, and Load Loop
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

                # 3. Transformation
                try:
                    transformed_chunk = self._transform_data(chunk)
                except Exception as te:
                    logger.error(f"Transformation failed on batch: {te}")
                    total_failed += chunk_len
                    self.run.records_loaded = total_loaded
                    self.run.records_failed = total_failed
                    self.run.save(update_fields=['records_loaded', 'records_failed'])
                    raise ValueError(f"Transformation failed: {te}")

                # 4. Load Phase (Write Chunk)
                try:
                    if self.mapping.load_mode in ('scd1', 'scd2'):
                        loaded_count, inserted_count, updated_count, failed_count = self._load_scd(transformed_chunk)
                        total_loaded += loaded_count
                        total_inserted += inserted_count
                        total_updated += updated_count
                        total_failed += failed_count
                    else:
                        mode = 'replace' if (first_batch and self.mapping.load_mode == 'truncate') else 'append'
                        loaded_count = self._load_data(transformed_chunk, mode)
                        total_loaded += loaded_count
                        total_inserted += loaded_count
                        first_batch = False
                except Exception as le:
                    logger.error(f"Loading failed on batch: {le}")
                    total_failed += chunk_len
                    self.run.records_loaded = total_loaded
                    self.run.records_failed = total_failed
                    self.run.save(update_fields=['records_loaded', 'records_failed'])
                    raise ValueError(f"Loading failed: {le}")

            # Update final execution status
            self.run.records_extracted = total_extracted
            self.run.records_loaded = total_loaded
            self.run.records_inserted = total_inserted
            self.run.records_updated = total_updated
            self.run.records_failed = total_failed
            self.run.progress = 80
            self.run.save(update_fields=[
                'records_extracted', 'records_loaded', 'records_inserted',
                'records_updated', 'records_failed', 'progress'
            ])

            # 5. Execute Post-SQL
            if self.mapping.post_sql:
                try:
                    logger.info(f"Executing Post-SQL on {self.mapping.post_sql_location} connection.")
                    if self.mapping.post_sql_location == 'source':
                        self.source_engine.execute_statement(self.mapping.post_sql)
                    else:
                        self.target_engine.execute_statement(self.mapping.post_sql)
                    
                    self.run.post_sql_status = 'SUCCESS'
                    self.run.save(update_fields=['post_sql_status'])
                    
                    ETLResult.objects.create(
                        run=self.run,
                        source_column='Post-SQL',
                        target_column='Executed',
                        operation='post_sql',
                        source_value=self.mapping.post_sql_location,
                        target_value='SUCCESS',
                        is_match=True,
                        difference='0',
                        details={'info': f'Post-SQL successfully executed on {self.mapping.post_sql_location}'}
                    )
                except Exception as e:
                    self.run.post_sql_status = 'FAILED'
                    self.run.error_message = f"Post-SQL failed: {e}"
                    self.run.status = 'failed'
                    self.run.completed_at = timezone.now()
                    self.run.save()
                    
                    ETLResult.objects.create(
                        run=self.run,
                        source_column='Post-SQL',
                        target_column='Failed',
                        operation='post_sql',
                        source_value=self.mapping.post_sql_location,
                        target_value='FAILED',
                        is_match=False,
                        difference=str(e)[:250]
                    )
                    raise ValueError(f"Post-SQL failed: {e}")

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
            
            total_checks = 3
            passed_checks = 3
            if self.mapping.pre_sql:
                total_checks += 1
                passed_checks += 1
            if self.mapping.post_sql:
                total_checks += 1
                passed_checks += 1

            self.run.total_checks = total_checks
            self.run.passed_checks = passed_checks
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
            yield from self._execute_db_query_generator(query, {}, batch_size)
            return

        # Mock connection handling
        if self.source_engine.is_mocked():
            logger.info("Generating mock source data batch.")
            yield self._generate_mock_data()
            return

        # File connection handling
        if self.source_engine.connection.is_file:
            logger.info(f"Extracting file data from: {self.mapping.source_table}")
            yield from self._read_file_generator(batch_size)
            return

        # Database extraction query construction
        query, params = self._build_extraction_query()
        yield from self._execute_db_query_generator(query, params, batch_size)

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

    def _load_scd(self, df):
        """Execute SCD Type 1 or SCD Type 2 logic on target."""
        if df is None or df.empty:
            return 0, 0, 0, 0

        business_key = self.mapping.scd_business_key
        if not business_key:
            raise ValueError("SCD business key is not configured.")

        # Ensure business key exists in the input DataFrame
        if business_key not in df.columns:
            found = False
            for col in df.columns:
                if col.lower() == business_key.lower():
                    df = df.rename(columns={col: business_key})
                    found = True
                    break
            if not found:
                raise ValueError(f"SCD business key column '{business_key}' not found in source dataset columns: {list(df.columns)}")

        # Parse tracked columns list
        track_cols_str = self.mapping.scd_track_columns or ''
        track_cols = [c.strip() for c in track_cols_str.split(',') if c.strip()]
        if not track_cols:
            scd_cols = {
                self.mapping.scd_effective_from, 
                self.mapping.scd_effective_to, 
                self.mapping.scd_active_flag
            }
            track_cols = [c for c in df.columns if c.lower() != business_key.lower() and c not in scd_cols]

        current_time = timezone.now().replace(tzinfo=None)

        # File target connection handling
        if self.target_engine.connection.is_file:
            logger.info("Performing SCD load on file target.")
            return self._load_scd_file(df, business_key, track_cols, current_time)

        # Database target connection handling
        if self.target_engine.is_mocked():
            logger.info("Simulating SCD database load.")
            total = len(df)
            inserted = int(total * 0.6)
            updated = total - inserted
            return total, inserted, updated, 0

        # Database target execution
        if self.mapping.load_mode == 'scd1':
            return self._load_scd1_db(df, business_key, track_cols)
        elif self.mapping.load_mode == 'scd2':
            return self._load_scd2_db(df, business_key, track_cols, current_time)

        return 0, 0, 0, 0

    def _load_scd_file(self, df, business_key, track_cols, current_time):
        target_full_df = self.target_engine.read_file(table=self.mapping.target_table)
        
        # Determine if we should use date-only format or ISO timestamp
        is_date_only = False
        eff_from_col = self.mapping.scd_effective_from
        eff_to_col = self.mapping.scd_effective_to
        active_flag_col = self.mapping.scd_active_flag

        if target_full_df is not None and not target_full_df.empty and eff_from_col in target_full_df.columns:
            col_dtype = str(target_full_df[eff_from_col].dtype).lower()
            if 'date' in col_dtype and 'time' not in col_dtype and 'timestamp' not in col_dtype:
                is_date_only = True
        
        current_time_str = current_time.date().isoformat() if is_date_only else str(current_time)

        # If target file is empty/non-existent, initialize it
        if target_full_df is None or target_full_df.empty:
            if self.mapping.load_mode == 'scd2':
                df[eff_from_col] = current_time_str
                df[eff_to_col] = '9999-12-31'
                df[active_flag_col] = True
            
            self.target_engine.write_data(df, schema=self.mapping.target_schema, table=self.mapping.target_table, mode='replace')
            return len(df), len(df), 0, 0

        # Perform in-memory SCD
        inserted_count = 0
        updated_count = 0

        # Coerce business key columns to strings for reliable match
        target_full_df[business_key] = target_full_df[business_key].astype(str).str.strip()
        df[business_key] = df[business_key].astype(str).str.strip()

        if self.mapping.load_mode == 'scd1':
            new_rows = []
            for _, row in df.iterrows():
                bk_val = row[business_key]
                match_indices = target_full_df[target_full_df[business_key] == bk_val].index
                if not match_indices.empty:
                    changed = False
                    for col in track_cols:
                        if col in target_full_df.columns and col in df.columns:
                            if values_differ(target_full_df.loc[match_indices[0], col], row[col]):
                                changed = True
                                break
                    if changed:
                        for col in df.columns:
                            if col in target_full_df.columns:
                                target_full_df.loc[match_indices[0], col] = row[col]
                        updated_count += 1
                else:
                    new_rows.append(row)
                    inserted_count += 1
            if new_rows:
                target_full_df = pd.concat([target_full_df, pd.DataFrame(new_rows)], ignore_index=True)
                
        elif self.mapping.load_mode == 'scd2':
            # Ensure columns exist
            for col in (eff_from_col, eff_to_col, active_flag_col):
                if col not in target_full_df.columns:
                    target_full_df[col] = None

            # Dynamically resolve active/inactive values
            active_val, inactive_val = self._resolve_flag_values(active_flag_col, target_full_df)

            new_rows = []
            for _, row in df.iterrows():
                bk_val = row[business_key]
                # Match only active target record
                active_mask = (target_full_df[business_key] == bk_val) & (target_full_df[active_flag_col] == active_val)
                match_indices = target_full_df[active_mask].index

                if not match_indices.empty:
                    changed = False
                    for col in track_cols:
                        if col in target_full_df.columns and col in df.columns:
                            if values_differ(target_full_df.loc[match_indices[0], col], row[col]):
                                changed = True
                                break
                    if changed:
                        # Close active
                        target_full_df.loc[match_indices[0], eff_to_col] = current_time_str
                        target_full_df.loc[match_indices[0], active_flag_col] = inactive_val
                        updated_count += 1

                        # Insert new version
                        new_row = row.copy()
                        new_row[eff_from_col] = current_time_str
                        new_row[eff_to_col] = '9999-12-31'
                        new_row[active_flag_col] = active_val
                        new_rows.append(new_row)
                        inserted_count += 1
                else:
                    new_row = row.copy()
                    new_row[eff_from_col] = current_time_str
                    new_row[eff_to_col] = '9999-12-31'
                    new_row[active_flag_col] = active_val
                    new_rows.append(new_row)
                    inserted_count += 1
            if new_rows:
                target_full_df = pd.concat([target_full_df, pd.DataFrame(new_rows)], ignore_index=True)

        self.target_engine.write_data(target_full_df, schema=self.mapping.target_schema, table=self.mapping.target_table, mode='replace')
        return (inserted_count + updated_count), inserted_count, updated_count, 0

    def _resolve_flag_values(self, col_name, target_df):
        active_val = True
        inactive_val = False
        if col_name in target_df.columns:
            unique_vals = target_df[col_name].dropna().unique()
            if len(unique_vals) > 0:
                val = unique_vals[0]
                if isinstance(val, str):
                    if val.upper() in ('Y', 'YES', 'TRUE', 'ACTIVE', 'A', '1'):
                        active_val = val
                        inactive_val = 'N' if val.upper() in ('Y', 'YES') else ('Inactive' if val.upper() == 'ACTIVE' else 'I')
                    else:
                        active_val = 'Y'
                        inactive_val = 'N'
                elif isinstance(val, (int, float)):
                    active_val = 1
                    inactive_val = 0
        return active_val, inactive_val

    def _load_scd1_db(self, df, business_key, track_cols):
        target_df = self._fetch_matching_target_records(df, business_key)
        
        inserted_count = 0
        updated_count = 0
        
        inserts = []
        updates = []

        if not target_df.empty:
            target_df[business_key] = target_df[business_key].astype(str).str.strip()
        df_bk_str = df[business_key].astype(str).str.strip()

        for idx, row in df.iterrows():
            bk_val = df_bk_str.loc[idx]
            match_indices = target_df[target_df[business_key] == bk_val].index if not target_df.empty else pd.Index([])

            if not match_indices.empty:
                changed = False
                for col in track_cols:
                    if col in target_df.columns and col in df.columns:
                        if values_differ(target_df.loc[match_indices[0], col], row[col]):
                            changed = True
                            break
                if changed:
                    updates.append(row)
                    updated_count += 1
            else:
                inserts.append(row)
                inserted_count += 1

        if updates:
            updates_df = pd.DataFrame(updates)
            self._execute_db_scd1_updates(updates_df, business_key, track_cols)

        if inserts:
            inserts_df = pd.DataFrame(inserts)
            self.target_engine.write_data(
                inserts_df,
                schema=self.mapping.target_schema,
                table=self.mapping.target_table,
                catalog=self.mapping.target_catalog if self.mapping.target_connection.connection_type == 'databricks' else None,
                mode='append'
            )

        return (inserted_count + updated_count), inserted_count, updated_count, 0

    def _execute_db_scd1_updates(self, updates_df, business_key, track_cols):
        full_table = self.target_engine._build_full_table_name(
            self.mapping.target_table,
            schema=self.mapping.target_schema,
            catalog=self.mapping.target_catalog if self.mapping.target_connection.connection_type == 'databricks' else None
        )
        engine = self.target_engine.get_engine()
        with engine.begin() as conn:
            for _, row in updates_df.iterrows():
                set_parts = []
                params = {}
                for col in track_cols:
                    if col.lower() == business_key.lower():
                        continue
                    q_col = self.target_engine._quote_identifier(col)
                    set_parts.append(f"{q_col} = :{col}")
                    val = row[col]
                    params[col] = None if pd.isna(val) else val
                
                q_bk = self.target_engine._quote_identifier(business_key)
                bk_val = row[business_key]
                params['bk_val'] = None if pd.isna(bk_val) else bk_val
                
                update_sql = f"UPDATE {full_table} SET {', '.join(set_parts)} WHERE {q_bk} = :bk_val"
                conn.execute(text(update_sql), params)

    def _load_scd2_db(self, df, business_key, track_cols, current_time):
        target_df = self._fetch_matching_target_records(df, business_key)

        eff_from_col = self.mapping.scd_effective_from
        eff_to_col = self.mapping.scd_effective_to
        active_flag_col = self.mapping.scd_active_flag

        if not eff_from_col or not eff_to_col or not active_flag_col:
            raise ValueError("SCD Type 2 Effective From, Effective To, or Active Flag columns are not configured.")

        active_val, inactive_val = self._resolve_flag_values(active_flag_col, target_df)

        inserted_count = 0
        updated_count = 0

        inserts = []
        updates_to_close = []

        if not target_df.empty:
            target_df[business_key] = target_df[business_key].astype(str).str.strip()
        df_bk_str = df[business_key].astype(str).str.strip()

        eff_from_time = self._format_scd_time(eff_from_col, current_time)
        eff_to_time = self._format_scd_time(eff_to_col, current_time)

        for idx, row in df.iterrows():
            bk_val = df_bk_str.loc[idx]
            
            if not target_df.empty:
                active_mask = (target_df[business_key] == bk_val) & (target_df[active_flag_col] == active_val)
                match_indices = target_df[active_mask].index
            else:
                match_indices = pd.Index([])

            if not match_indices.empty:
                changed = False
                for col in track_cols:
                    if col in target_df.columns and col in df.columns:
                        if values_differ(target_df.loc[match_indices[0], col], row[col]):
                            changed = True
                            break
                if changed:
                    updates_to_close.append(row)
                    updated_count += 1

                    new_row = row.copy()
                    new_row[eff_from_col] = eff_from_time
                    new_row[eff_to_col] = '9999-12-31'
                    new_row[active_flag_col] = active_val
                    inserts.append(new_row)
                    inserted_count += 1
            else:
                new_row = row.copy()
                new_row[eff_from_col] = eff_from_time
                new_row[eff_to_col] = '9999-12-31'
                new_row[active_flag_col] = active_val
                inserts.append(new_row)
                inserted_count += 1

        if updates_to_close:
            updates_df = pd.DataFrame(updates_to_close)
            self._execute_db_scd2_closures(updates_df, business_key, eff_to_col, active_flag_col, eff_to_time, active_val, inactive_val)

        if inserts:
            inserts_df = pd.DataFrame(inserts)
            self.target_engine.write_data(
                inserts_df,
                schema=self.mapping.target_schema,
                table=self.mapping.target_table,
                catalog=self.mapping.target_catalog if self.mapping.target_connection.connection_type == 'databricks' else None,
                mode='append'
            )

        return (inserted_count + updated_count), inserted_count, updated_count, 0

    def _format_scd_time(self, col_name, current_time):
        try:
            cols = self.target_engine.get_columns(self.mapping.target_schema, self.mapping.target_table)
            for c in cols:
                if c['name'].lower() == col_name.lower():
                    ctype = str(c['type']).lower()
                    if 'date' in ctype and 'time' not in ctype and 'timestamp' not in ctype:
                        return current_time.date().isoformat()
        except Exception:
            pass
        return current_time

    def _execute_db_scd2_closures(self, updates_df, business_key, eff_to_col, active_flag_col, eff_to_time, active_val, inactive_val):
        full_table = self.target_engine._build_full_table_name(
            self.mapping.target_table,
            schema=self.mapping.target_schema,
            catalog=self.mapping.target_catalog if self.mapping.target_connection.connection_type == 'databricks' else None
        )
        engine = self.target_engine.get_engine()
        with engine.begin() as conn:
            for _, row in updates_df.iterrows():
                q_eff_to = self.target_engine._quote_identifier(eff_to_col)
                q_flag = self.target_engine._quote_identifier(active_flag_col)
                q_bk = self.target_engine._quote_identifier(business_key)

                params = {
                    'eff_to': eff_to_time,
                    'inactive_val': inactive_val,
                    'bk_val': row[business_key],
                    'active_val': active_val
                }

                close_sql = f"""
                    UPDATE {full_table}
                    SET {q_eff_to} = :eff_to, {q_flag} = :inactive_val
                    WHERE {q_bk} = :bk_val AND {q_flag} = :active_val
                """
                conn.execute(text(close_sql), params)

    def _fetch_matching_target_records(self, df, business_key):
        target_df = pd.DataFrame()
        keys = df[business_key].dropna().unique().tolist()
        if not keys:
            return target_df

        quoted_bk = self.target_engine._quote_identifier(business_key)
        full_table = self.target_engine._build_full_table_name(
            self.mapping.target_table,
            schema=self.mapping.target_schema,
            catalog=self.mapping.target_catalog if self.mapping.target_connection.connection_type == 'databricks' else None
        )

        formatted_keys = []
        for k in keys:
            if isinstance(k, (int, float)):
                formatted_keys.append(str(k))
            else:
                escaped_k = str(k).replace("'", "''")
                formatted_keys.append(f"'{escaped_k}'")

        chunk_size = 1000
        for i in range(0, len(formatted_keys), chunk_size):
            sub_keys = formatted_keys[i:i+chunk_size]
            in_list = ",".join(sub_keys)
            query = f"SELECT * FROM {full_table} WHERE {quoted_bk} IN ({in_list})"
            try:
                sub_target_df = self.target_engine.execute_query(query)
                if sub_target_df is not None and not sub_target_df.empty:
                    target_df = pd.concat([target_df, sub_target_df], ignore_index=True)
            except Exception as e:
                logger.warning(f"Failed to query matching target records: {e}")
                
        return target_df
