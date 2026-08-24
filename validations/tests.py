import json
from django.test import TestCase
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from connections.models import DataConnection
from mappings.models import Mapping, ColumnMapping, ETLStep
from validations.models import ETLRun, ETLResult
from validations.views import get_datatype_category, get_applicable_operations

class ValidationWorkspaceEnhancementsTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='password123')
        # Ensure user has a profile with contributor/admin role if required
        from accounts.models import UserProfile
        profile, created = UserProfile.objects.get_or_create(user=self.user)
        profile.role = 'contributor'
        profile.save()

        self.source_conn = DataConnection.objects.create(
            name='Dummy Source',
            connection_type='postgresql',
            host='dummy-host',
            database_name='source_db',
            created_by=self.user
        )
        self.target_conn = DataConnection.objects.create(
            name='Dummy Target',
            connection_type='postgresql',
            host='dummy-host',
            database_name='target_db',
            created_by=self.user
        )

    def test_datatype_categorization(self):
        self.assertEqual(get_datatype_category('INTEGER'), 'INTEGER')
        self.assertEqual(get_datatype_category('varchar(255)'), 'VARCHAR')
        self.assertEqual(get_datatype_category('DATE'), 'DATE')
        self.assertEqual(get_datatype_category('boolean'), 'BOOLEAN')
        self.assertEqual(get_datatype_category('FLOAT8'), 'INTEGER')
        self.assertEqual(get_datatype_category('TIMESTAMP WITH TIME ZONE'), 'DATE')
        self.assertEqual(get_datatype_category(None), 'VARCHAR')
        self.assertEqual(get_datatype_category('object', 'created_at'), 'DATE')
        self.assertEqual(get_datatype_category('object', 'closed_on'), 'DATE')
        self.assertEqual(get_datatype_category('string', 'my_date_dt'), 'DATE')

    def test_applicable_operations_by_category(self):
        int_ops = get_applicable_operations('INTEGER')
        self.assertIn('sum', int_ops)
        self.assertIn('avg', int_ops)
        self.assertNotIn('length_sum_check', int_ops)
        self.assertNotIn('equals', int_ops)
        self.assertIn('unique_check', int_ops)
        self.assertIn('distinct_count', int_ops)
        self.assertIn('data_type_check', int_ops)
        self.assertIn('std_dev', int_ops)
        self.assertIn('variance', int_ops)
        self.assertIn('median', int_ops)
        self.assertIn('mode', int_ops)

        str_ops = get_applicable_operations('VARCHAR')
        self.assertIn('length_sum_check', str_ops)
        self.assertIn('regex_check', str_ops)
        self.assertNotIn('sum', str_ops)
        self.assertNotIn('equals_check', str_ops)
        self.assertNotIn('case_insensitive_check', str_ops)
        self.assertNotIn('trim_check', str_ops)
        self.assertNotIn('contains_check', str_ops)
        self.assertNotIn('starts_with_check', str_ops)
        self.assertNotIn('ends_with_check', str_ops)
        self.assertIn('pattern_match', str_ops)
        self.assertIn('unique_check', str_ops)
        self.assertIn('distinct_count', str_ops)
        self.assertIn('data_type_check', str_ops)

        date_ops = get_applicable_operations('DATE')
        self.assertIn('min_date', date_ops)
        self.assertIn('max_date', date_ops)
        self.assertNotIn('sum', date_ops)
        self.assertIn('unique_check', date_ops)
        self.assertIn('distinct_count', date_ops)

    def test_new_validation_queries_execution(self):
        import pandas as pd
        import tempfile
        import os
        
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "test_data.csv")
            df = pd.DataFrame({
                'str_col': [' hello', 'world', 'apple', 'banana', '12345'],
                'int_col': [10, 20, 30, 40, 50]
            })
            df.to_csv(csv_path, index=False)
            
            file_conn = DataConnection.objects.create(
                name='Temp CSV',
                connection_type='csv',
                host=tmpdir,
                created_by=self.user
            )
            from connections.connector import ConnectorEngine
            engine = ConnectorEngine(file_conn)
            
            # String checks
            self.assertEqual(engine.get_aggregation('file', 'test_data.csv', 'str_col', 'pattern_match'), 5)
            self.assertEqual(engine.get_aggregation('file', 'test_data.csv', 'str_col', 'distinct_count'), 5)
            self.assertEqual(engine.get_aggregation('file', 'test_data.csv', 'str_col', 'unique_check'), 5)
            
            # Numeric checks
            self.assertEqual(engine.get_aggregation('file', 'test_data.csv', 'int_col', 'count'), 5)
            self.assertAlmostEqual(engine.get_aggregation('file', 'test_data.csv', 'int_col', 'std_dev'), 15.811388, places=5)
            self.assertEqual(engine.get_aggregation('file', 'test_data.csv', 'int_col', 'variance'), 250.0)
            self.assertEqual(engine.get_aggregation('file', 'test_data.csv', 'int_col', 'median'), 30.0)
            self.assertEqual(engine.get_aggregation('file', 'test_data.csv', 'int_col', 'mode'), 10)
            
            # Mock DB checks
            db_conn = DataConnection.objects.create(
                name='Temp Mock DB',
                connection_type='sqlite',
                host='dummy_mock_host',
                created_by=self.user
            )
            db_engine = ConnectorEngine(db_conn)
            self.assertEqual(db_engine.get_aggregation('main', 'tbl', 'val', 'unique_check'), 1250)
            self.assertEqual(db_engine.get_aggregation('main', 'tbl', 'val', 'distinct_count'), 150)
            self.assertEqual(db_engine.get_aggregation('main', 'tbl', 'val', 'std_dev'), 2.5)
            self.assertEqual(db_engine.get_aggregation('main', 'tbl', 'val', 'variance'), 6.25)
            self.assertEqual(db_engine.get_aggregation('main', 'tbl', 'val', 'median'), 250.0)
            self.assertEqual(db_engine.get_aggregation('main', 'tbl', 'val', 'mode'), 250.0)

    def test_quick_validate_with_all_columns(self):
        # Authenticate client
        self.client.login(username='testuser', password='password123')
        
        # Build JSON column mapping representing "__all__" columns selection
        column_mappings_json = json.dumps([
            {
                "source_column": "__all__",
                "source_datatype": "unknown",
                "target_column": "__all__",
                "target_datatype": "unknown",
                "operations": []
            }
        ])

        response = self.client.post(reverse('validations:quick'), {
            'source_connection': self.source_conn.id,
            'source_schema': 'public',
            'source_table': 'customers',
            'target_connection': self.target_conn.id,
            'target_schema': 'public',
            'target_table': 'customers',
            'column_mappings_json': column_mappings_json,
            # Source Date Filter
            'source_date_column': 'created_at',
            'source_date_filter_type': 'specific',
            'source_date_single': '2026-06-05',
            # Target Date Filter
            'target_date_column': 'created_at',
            'target_date_filter_type': 'range',
            'target_date_filter_start': '2026-06-01',
            'target_date_filter_end': '2026-06-10',
        })

        # Should redirect to validation progress
        self.assertEqual(response.status_code, 302)
        
        # Verify mapping and validation run were created correctly
        mapping = Mapping.objects.first()
        self.assertIsNotNone(mapping)
        self.assertEqual(mapping.source_date_column, 'created_at')
        self.assertEqual(mapping.source_date_filter_type, 'specific')
        self.assertEqual(str(mapping.source_date_filter_start), '2026-06-05')
        self.assertEqual(str(mapping.source_date_filter_end), '2026-06-05') # Equal bounds for specific

        self.assertEqual(mapping.target_date_column, 'created_at')
        self.assertEqual(mapping.target_date_filter_type, 'range')
        self.assertEqual(str(mapping.target_date_filter_start), '2026-06-01')
        self.assertEqual(str(mapping.target_date_filter_end), '2026-06-10')

        run = ETLRun.objects.first()
        self.assertIsNotNone(run)
        self.assertEqual(str(run.source_date_filter_start), '2026-06-05')
        self.assertEqual(str(run.source_date_filter_end), '2026-06-05')
        self.assertEqual(str(run.target_date_filter_start), '2026-06-01')
        self.assertEqual(str(run.target_date_filter_end), '2026-06-10')

        # Since it was '__all__', check if column mappings were automatically expanded based on mock columns
        col_mappings = ColumnMapping.objects.filter(mapping=mapping)
        self.assertTrue(col_mappings.exists())
        
        # Check that rules were created for the mock columns (e.g. customer_id, first_name)
        customer_id_mapping = col_mappings.filter(source_column='customer_id').first()
        self.assertIsNotNone(customer_id_mapping)
        # Check INTEGER operations were created for customer_id
        rules = customer_id_mapping.rules.all()
        operations = [r.operation for r in rules]
        self.assertIn('sum', operations)
        self.assertIn('avg', operations)
        self.assertIn('null_check', operations)

    def test_pipeline_mapping_creation_view(self):
        # Authenticate client
        self.client.login(username='testuser', password='password123')
        
        column_mappings_json = json.dumps([
            {
                "source_column": "first_name",
                "source_datatype": "VARCHAR(100)",
                "target_column": "first_name",
                "target_datatype": "VARCHAR(100)",
                "operations": ["null_check", "length_sum_check"]
            },
            {
                "source_column": "customer_id",
                "source_datatype": "INTEGER",
                "target_column": "customer_id",
                "target_datatype": "INTEGER",
                "operations": ["sum", "avg"]
            }
        ])

        response = self.client.post(reverse('mappings:create'), {
            'name': 'Test Pipeline',
            'description': 'My E2E Pipeline',
            'source_connection': self.source_conn.id,
            'source_schema': 'public',
            'source_table': 'customers',
            'target_connection': self.target_conn.id,
            'target_schema': 'public',
            'target_table': 'customers',
            'column_mappings_json': column_mappings_json,
            # Source Date Filter
            'source_date_column': 'created_at',
            'source_date_filter_type': 'specific',
            'source_date_single': '2026-06-05',
            # Target Date Filter
            'target_date_column': 'created_at',
            'target_date_filter_type': 'range',
            'target_date_filter_start': '2026-06-01',
            'target_date_filter_end': '2026-06-10',
        })

        self.assertEqual(response.status_code, 302)
        
        mapping = Mapping.objects.first()
        self.assertIsNotNone(mapping)
        self.assertEqual(mapping.name, 'Test Pipeline')
        self.assertEqual(mapping.source_date_column, 'created_at')
        
        col_mappings = ColumnMapping.objects.filter(mapping=mapping)
        self.assertEqual(col_mappings.count(), 2)

        fn_mapping = col_mappings.filter(source_column='first_name').first()
        self.assertIsNotNone(fn_mapping)
        self.assertEqual(fn_mapping.source_datatype, 'VARCHAR(100)')
        self.assertEqual(fn_mapping.rules.count(), 2)
        self.assertListEqual(
            sorted([r.operation for r in fn_mapping.rules.all()]),
            sorted(['null_check', 'length_sum_check'])
        )

    def test_monitor_runs_list_search(self):
        # Authenticate client
        self.client.login(username='testuser', password='password123')
        
        # Create mapping and validation run
        mapping_match = Mapping.objects.create(
            name='My Searchable Pipeline',
            source_connection=self.source_conn,
            target_connection=self.target_conn,
            created_by=self.user
        )
        mapping_mismatch = Mapping.objects.create(
            name='Mismatched Pipeline',
            source_connection=self.source_conn,
            target_connection=self.target_conn,
            created_by=self.user
        )
        
        run_match = ETLRun.objects.create(
            mapping=mapping_match,
            status='completed',
            triggered_by=self.user
        )
        run_mismatch = ETLRun.objects.create(
            mapping=mapping_mismatch,
            status='completed',
            triggered_by=self.user
        )
        
        # Test loading monitor list with query matching mapping_match name
        response = self.client.get(reverse('validations:list') + '?query=Searchable')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'My Searchable Pipeline')
        self.assertNotContains(response, 'Mismatched Pipeline')
        
        # Test loading monitor list without query
        response_all = self.client.get(reverse('validations:list'))
        self.assertEqual(response_all.status_code, 200)
        self.assertContains(response_all, 'My Searchable Pipeline')
        self.assertContains(response_all, 'Mismatched Pipeline')

    def test_description_length_limit(self):
        from django.core.exceptions import ValidationError
        
        # Test DataConnection description validator
        invalid_conn = DataConnection(
            name='Invalid Conn',
            connection_type='postgresql',
            description='x' * 1001,
            created_by=self.user
        )
        with self.assertRaises(ValidationError):
            invalid_conn.full_clean()
            
        # Test Mapping description validator
        invalid_mapping = Mapping(
            name='Invalid Mapping',
            description='x' * 1001,
            source_connection=self.source_conn,
            target_connection=self.target_conn,
            created_by=self.user
        )
        with self.assertRaises(ValidationError):
            invalid_mapping.full_clean()

        # Test Workflow description validator
        from workflows.models import Workflow
        dummy_map = Mapping.objects.create(
            name='Dummy Map',
            source_connection=self.source_conn,
            target_connection=self.target_conn,
            created_by=self.user
        )
        invalid_workflow = Workflow(
            name='Invalid Workflow',
            description='x' * 1001,
            mapping=dummy_map,
            created_by=self.user
        )
        with self.assertRaises(ValidationError):
            invalid_workflow.full_clean()

    def test_calendar_date_resolution_on_run_save(self):
        import datetime
        mapping = Mapping.objects.create(
            name='Calendar Date Map',
            source_connection=self.source_conn,
            target_connection=self.target_conn,
            created_by=self.user,
            source_date_column='created_at',
            source_date_filter_type='specific',
            source_date_filter_start=datetime.date(2026, 6, 5),
            
            target_date_column='updated_at',
            target_date_filter_type='range',
            target_date_filter_start=datetime.date(2026, 6, 1),
            target_date_filter_end=datetime.date(2026, 6, 10)
        )
        
        run = ETLRun.objects.create(
            mapping=mapping,
            triggered_by=self.user
        )
        
        self.assertEqual(run.source_date_filter_start, datetime.date(2026, 6, 5))
        self.assertEqual(run.source_date_filter_end, datetime.date(2026, 6, 5))
        self.assertEqual(run.target_date_filter_start, datetime.date(2026, 6, 1))
        self.assertEqual(run.target_date_filter_end, datetime.date(2026, 6, 10))

    def test_date_comparison_operators(self):
        import pandas as pd
        # Create a dummy dataset
        df_data = pd.DataFrame({
            'date_col': ['2026-06-05', '2026-06-06', '2026-06-07'],
            'val': [10, 20, 30]
        })
        
        # Create a dummy CSV connection so is_mocked() returns False
        csv_conn = DataConnection.objects.create(
            name='Test CSV',
            connection_type='csv',
            host='dummy_folder_path',
            created_by=self.user
        )
        from connections.connector import ConnectorEngine
        engine = ConnectorEngine(csv_conn)
        
        # Monkeypatch read_file to return our dummy dataframe
        original_read_file = engine.read_file
        engine.read_file = lambda limit=None, table=None: df_data.copy()
        
        try:
            # Test '=' operator
            res_eq = engine.get_aggregation(
                schema='file', table='dummy', column='val', operation='sum',
                date_column='date_col', date_start='2026-06-06', date_operator='='
            )
            self.assertEqual(res_eq, 20)
            
            # Test '>' operator
            res_gt = engine.get_aggregation(
                schema='file', table='dummy', column='val', operation='sum',
                date_column='date_col', date_start='2026-06-05', date_operator='>'
            )
            self.assertEqual(res_gt, 50)  # 20 + 30
            
            # Test '<=' operator
            res_le = engine.get_aggregation(
                schema='file', table='dummy', column='val', operation='sum',
                date_column='date_col', date_start='2026-06-06', date_operator='<='
            )
            self.assertEqual(res_le, 30)  # 10 + 20
            
        finally:
            engine.read_file = original_read_file

    def test_pipeline_mapping_edit_view(self):
        # Authenticate client
        self.client.login(username='testuser', password='password123')
        
        # Create an initial mapping to edit
        mapping = Mapping.objects.create(
            name='Initial Pipeline',
            description='Original description',
            source_connection=self.source_conn,
            source_table='customers',
            target_connection=self.target_conn,
            target_table='customers',
            created_by=self.user
        )
        col_map = ColumnMapping.objects.create(
            mapping=mapping,
            source_column='first_name',
            source_datatype='VARCHAR',
            target_column='first_name',
            target_datatype='VARCHAR'
        )
        ETLStep.objects.create(
            column_mapping=col_map,
            operation='null_check'
        )

        column_mappings_json = json.dumps([
            {
                "source_column": "customer_id",
                "source_datatype": "INTEGER",
                "target_column": "customer_id",
                "target_datatype": "INTEGER",
                "operations": ["sum"]
            }
        ])

        response = self.client.post(reverse('mappings:edit', args=[mapping.id]), {
            'name': 'Updated Pipeline Name ',  # note the extra space to test trimming
            'description': 'Updated description',
            'source_connection': self.source_conn.id,
            'source_schema': 'public',
            'source_table': 'customers',
            'target_connection': self.target_conn.id,
            'target_schema': 'public',
            'target_table': 'customers',
            'column_mappings_json': column_mappings_json,
            'source_date_column': 'created_at',
            'source_date_filter_type': 'specific',
            'source_date_single': '2026-06-08',
        })

        self.assertEqual(response.status_code, 302)
        
        # Verify changes in DB
        mapping.refresh_from_db()
        self.assertEqual(mapping.name, 'Updated Pipeline Name')  # should be trimmed!
        self.assertEqual(mapping.description, 'Updated description')
        self.assertEqual(mapping.source_date_column, 'created_at')
        self.assertEqual(mapping.source_date_filter_type, 'specific')
        self.assertEqual(str(mapping.source_date_filter_start), '2026-06-08')

        # Check that old column mapping/rule was deleted and new one was created
        col_mappings = mapping.column_mappings.all()
        self.assertEqual(col_mappings.count(), 1)
        new_col_map = col_mappings.first()
        self.assertEqual(new_col_map.source_column, 'customer_id')
        self.assertEqual(new_col_map.rules.count(), 1)
        self.assertEqual(new_col_map.rules.first().operation, 'sum')

    def test_validation_engine_enhancements(self):
        # Test ETLEngine execution pipeline
        import tempfile
        import os
        import pandas as pd
        
        with tempfile.TemporaryDirectory() as tmpdir:
            src_csv = os.path.join(tmpdir, "source.csv")
            tgt_csv = os.path.join(tmpdir, "target.csv")
            
            df_src = pd.DataFrame({'col': ['Active ', 'inactive', 'pending']})
            df_src.to_csv(src_csv, index=False)
            
            src_conn = DataConnection.objects.create(
                name='Src File', connection_type='csv', host=tmpdir, created_by=self.user
            )
            tgt_conn = DataConnection.objects.create(
                name='Tgt File', connection_type='csv', host=tmpdir, created_by=self.user
            )
            
            mapping = Mapping.objects.create(
                name='Test Refactor Mapping',
                source_connection=src_conn,
                source_table='source.csv',
                target_connection=tgt_conn,
                target_table='target.csv',
                load_mode='truncate',
                batch_size=10000,
                created_by=self.user
            )
            
            ColumnMapping.objects.create(
                mapping=mapping,
                source_column='col',
                source_datatype='VARCHAR',
                target_column='col',
                target_datatype='VARCHAR'
            )
            
            run = ETLRun.objects.create(
                mapping=mapping,
                triggered_by=self.user,
                trigger_type='manual'
            )
            
            from validations.engine import ETLEngine
            engine = ETLEngine(run)
            engine.execute()
            
            self.assertEqual(run.status, 'completed')
            self.assertEqual(run.records_extracted, 3)
            self.assertEqual(run.records_loaded, 3)
            
            # Read target and verify data
            df_tgt_loaded = pd.read_csv(tgt_csv)
            self.assertEqual(len(df_tgt_loaded), 3)
            self.assertEqual(list(df_tgt_loaded['col']), ['Active ', 'inactive', 'pending'])

    def test_databricks_catalog_aware_validation(self):
        from unittest.mock import patch
        import pandas as pd
        
        db_src = DataConnection.objects.create(
            name='DB Src', connection_type='databricks', host='dummy_host', database_name='db1', created_by=self.user
        )
        db_tgt = DataConnection.objects.create(
            name='DB Tgt', connection_type='databricks', host='dummy_host', database_name='db2', created_by=self.user
        )

        mapping = Mapping.objects.create(
            name='Databricks Catalog Pipeline',
            source_connection=db_src,
            source_catalog='src_catalog',
            source_schema='src_schema',
            source_table='customers',
            target_connection=db_tgt,
            target_catalog='tgt_catalog',
            target_schema='tgt_schema',
            target_table='customers',
            created_by=self.user
        )

        ColumnMapping.objects.create(
            mapping=mapping,
            source_column='customer_id',
            source_datatype='INTEGER',
            target_column='customer_id',
            target_datatype='INTEGER'
        )

        run = ETLRun.objects.create(
            mapping=mapping,
            triggered_by=self.user,
            trigger_type='manual'
        )

        from validations.engine import ETLEngine
        engine = ETLEngine(run)
        
        # Mock database extraction and load
        mock_df = pd.DataFrame({'customer_id': [1, 2]})
        with patch.object(engine, '_extract_data_generator', return_value=[mock_df]), \
             patch.object(engine.target_engine, 'write_data', return_value=2) as mock_write:
            
            engine.execute()
            
            self.assertEqual(run.status, 'completed')
            mock_write.assert_called_once()
            called_kwargs = mock_write.call_args[1]
            self.assertEqual(called_kwargs['catalog'], 'tgt_catalog')
            self.assertEqual(called_kwargs['schema'], 'tgt_schema')
            self.assertEqual(called_kwargs['table'], 'customers')

    def test_pipeline_monitor_history_view(self):
        # Authenticate client
        self.client.login(username='testuser', password='password123')
        
        # Create mapping and validation runs
        mapping = Mapping.objects.create(
            name='My Test Pipeline History Mapping',
            source_connection=self.source_conn,
            target_connection=self.target_conn,
            created_by=self.user
        )
        run1 = ETLRun.objects.create(
            mapping=mapping,
            status='completed',
            triggered_by=self.user
        )
        run2 = ETLRun.objects.create(
            mapping=mapping,
            status='failed',
            triggered_by=self.user
        )
        
        url = reverse('validations:pipeline_history', args=[mapping.id])
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'My Test Pipeline History Mapping')
        self.assertContains(response, 'Monitor Run History')
        # Check that both validation runs are rendered
        self.assertContains(response, f'status-badge-{run1.id}')
        self.assertContains(response, f'status-badge-{run2.id}')

    def test_etl_results_preserved_on_pipeline_edit(self):
        # Authenticate client
        self.client.login(username='testuser', password='password123')
        
        # Create mapping and column mapping
        mapping = Mapping.objects.create(
            name='Preservation Test Mapping',
            source_connection=self.source_conn,
            target_connection=self.target_conn,
            created_by=self.user,
            source_table='customers'
        )
        col_map = ColumnMapping.objects.create(
            mapping=mapping,
            source_column='email',
            source_datatype='VARCHAR',
            target_column='email',
            target_datatype='VARCHAR'
        )
        
        # Create run and validation result
        run = ETLRun.objects.create(
            mapping=mapping,
            status='completed',
            triggered_by=self.user
        )
        result = ETLResult.objects.create(
            run=run,
            column_mapping=col_map,
            source_column=col_map.source_column,
            target_column=col_map.target_column,
            operation='null_check',
            source_value='0',
            target_value='0',
            is_match=True
        )
        
        # Verify result is initially linked and has column values
        self.assertEqual(result.column_mapping, col_map)
        self.assertEqual(result.source_column, 'email')
        
        # Delete column mapping (simulating pipeline edit or deletion of a column mapping)
        col_map.delete()
        
        # Verify the validation result is PRESERVED (not cascaded-deleted)
        result.refresh_from_db()
        self.assertIsNone(result.column_mapping)
        self.assertEqual(result.source_column, 'email')
        self.assertEqual(result.target_column, 'email')
        
        # Verify the report page renders successfully with column names intact
        url = reverse('validations:report', args=[run.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'email')
        
        # Verify Excel export also runs successfully and handles the deleted mapping
        export_url = reverse('validations:export', args=[run.id])
        response_export = self.client.get(export_url)
        self.assertEqual(response_export.status_code, 200)
        self.assertEqual(response_export['Content-Type'], 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        self.assertEqual(response_export['Content-Disposition'], 'attachment; filename="Preservation Test Mapping.xlsx"')


import os
from workflows.models import Workflow, EmailNotification

class AutomatedEmailNotificationTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testemailuser', password='password123')
        from accounts.models import UserProfile
        profile, created = UserProfile.objects.get_or_create(user=self.user)
        profile.role = 'contributor'
        profile.save()

        self.source_conn = DataConnection.objects.create(
            name='Src Conn',
            connection_type='postgresql',
            host='dummy',
            database_name='src_db',
            created_by=self.user
        )
        self.target_conn = DataConnection.objects.create(
            name='Tgt Conn',
            connection_type='postgresql',
            host='dummy',
            database_name='tgt_db',
            created_by=self.user
        )
        self.mapping = Mapping.objects.create(
            name='Daily Customer Sync',
            source_connection=self.source_conn,
            source_table='customers',
            target_connection=self.target_conn,
            target_table='customers',
            created_by=self.user
        )
        self.col_map = ColumnMapping.objects.create(
            mapping=self.mapping,
            source_column='customer_id',
            source_datatype='INTEGER',
            target_column='customer_id',
            target_datatype='INTEGER'
        )
        self.rule = ETLStep.objects.create(
            column_mapping=self.col_map,
            operation='count'
        )
        self.workflow = Workflow.objects.create(
            name='Customer_Data_Reconciliation',
            description='Customer Master Data Validation',
            mapping=self.mapping,
            recipient_email='recipient@example.com',
            created_by=self.user
        )

    def test_report_generation(self):
        run = ETLRun.objects.create(
            mapping=self.mapping,
            workflow=self.workflow,
            status='completed',
            triggered_by=self.user,
            trigger_type='scheduled',
            total_checks=1,
            passed_checks=1,
            failed_checks=0
        )
        from validations.models import ETLResult
        ETLResult.objects.create(
            run=run,
            column_mapping=self.col_map,
            operation='count',
            source_value='100',
            target_value='100',
            is_match=True,
            difference='0'
        )

        from notifications.report_generator import generate_excel_report
        filepath = generate_excel_report(run)
        self.assertTrue(filepath.endswith('.xlsx'))
        self.assertTrue(os.path.exists(filepath))
        if os.path.exists(filepath):
            os.remove(filepath)

    def test_email_sending_flow(self):
        run = ETLRun.objects.create(
            mapping=self.mapping,
            workflow=self.workflow,
            status='completed',
            triggered_by=self.user,
            trigger_type='scheduled',
            total_checks=1,
            passed_checks=0,
            failed_checks=1
        )
        from validations.models import ETLResult
        ETLResult.objects.create(
            run=run,
            column_mapping=self.col_map,
            operation='count',
            source_value='100',
            target_value='98',
            is_match=False,
            difference='2'
        )

        from notifications.email_service import send_validation_email
        notification = send_validation_email(run)
        
        self.assertIsNotNone(notification)
        self.assertEqual(notification.recipient_email, 'recipient@example.com')
        self.assertEqual(notification.sent_status, 'success')
        self.assertIn('Customer_Data_Reconciliation', notification.subject)
        self.assertIn('Status: Failed', notification.email_body)
        self.assertTrue(os.path.exists(notification.attachment_path))
        
        if os.path.exists(notification.attachment_path):
            os.remove(notification.attachment_path)

    def test_api_send_email_endpoint(self):
        self.client.login(username='testemailuser', password='password123')
        run = ETLRun.objects.create(
            mapping=self.mapping,
            workflow=self.workflow,
            status='completed',
            triggered_by=self.user,
            trigger_type='manual',
            total_checks=1,
            passed_checks=1,
            failed_checks=0
        )
        from validations.models import ETLResult
        ETLResult.objects.create(
            run=run,
            column_mapping=self.col_map,
            operation='count',
            source_value='100',
            target_value='100',
            is_match=True,
            difference='0'
        )

        url = reverse('validations:api_send_email', args=[run.id])
        response = self.client.post(url, json.dumps({'email': 'manual_recipient@example.com'}), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertIn('Report email successfully sent', data['message'])

        # Verify EmailNotification record
        notification = EmailNotification.objects.filter(run=run).latest('created_at')
        self.assertEqual(notification.recipient_email, 'manual_recipient@example.com')
        self.assertEqual(notification.sent_status, 'success')
        
        if os.path.exists(notification.attachment_path):
            os.remove(notification.attachment_path)

    def test_api_send_email_endpoint_none_error_handling(self):
        self.client.login(username='testemailuser', password='password123')
        run = ETLRun.objects.create(
            mapping=self.mapping,
            workflow=self.workflow,
            status='completed',
            triggered_by=self.user,
            trigger_type='manual',
            total_checks=1,
            passed_checks=1,
            failed_checks=0
        )
        from validations.models import ETLResult
        ETLResult.objects.create(
            run=run,
            column_mapping=self.col_map,
            operation='count',
            source_value='100',
            target_value='100',
            is_match=True,
            difference='0'
        )

        from django.core.mail import EmailMessage
        import smtplib
        mock_send = MagicMock(side_effect=smtplib.SMTPConnectError(None, None))
        
        with patch.object(EmailMessage, 'send', mock_send):
            url = reverse('validations:api_send_email', args=[run.id])
            response = self.client.post(url, json.dumps({'email': 'manual_recipient@example.com'}), content_type='application/json')
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertFalse(data['success'])
            self.assertNotIn('None', data['error'])
            self.assertIn('SMTP/Connection Error', data['error'])


from unittest.mock import patch, MagicMock
from validations.engine import ETLEngine
from connections.connector import ConnectorEngine

class LakehouseAggregationTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='lakeuser', password='password123')
        self.conn = DataConnection.objects.create(
            name='Lakehouse Connection',
            connection_type='lakehouse',
            host='lakehouse-server',
            database_name='lakehouse_db',
            created_by=self.user,
            is_active=True
        )
        self.mapping = Mapping.objects.create(
            name='Lakehouse Test Mapping',
            source_connection=self.conn,
            source_table='int_fct_vp_ath3',
            source_schema='lm_edw_hdfc_dse',
            target_connection=self.conn,
            target_table='int_fct_vp_ath3',
            target_schema='lm_edw_hdfc_dse',
            created_by=self.user,
            self.assertIn('SMTP/Connection Error', data['error'])
