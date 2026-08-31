from django.test import TestCase
from django.contrib.auth.models import User
from django.urls import reverse
from .models import DataConnection

class ConnectionViewsTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='password123')
        from accounts.models import UserProfile
        profile, created = UserProfile.objects.get_or_create(user=self.user)
        profile.role = 'contributor'
        profile.save()
        
        self.connection = DataConnection.objects.create(
            name='Test Postgres',
            connection_type='postgresql',
            host='localhost',
            port=5432,
            database_name='test_db',
            username='postgres',
            created_by=self.user
        )
        self.connection.set_password('mysecretpass')
        self.connection.save()

    def test_connection_list_view(self):
        self.client.login(username='testuser', password='password123')
        response = self.client.get(reverse('connections:list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test Postgres')
        self.assertContains(response, 'PostgreSQL')

    def test_connection_edit_get_view(self):
        self.client.login(username='testuser', password='password123')
        response = self.client.get(reverse('connections:edit', args=[self.connection.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Edit Data Connection')
        self.assertContains(response, 'Test Postgres')
        # Check that is_edit flag is in the template context
        self.assertTrue(response.context['is_edit'])

    def test_connection_edit_post_success(self):
        self.client.login(username='testuser', password='password123')
        # We don't submit password, so it should keep the old password
        response = self.client.post(reverse('connections:edit', args=[self.connection.id]), {
            'name': 'Updated Name',
            'connection_type': 'postgresql',
            'host': 'localhost-new',
            'port': 5433,
            'database_name': 'test_db_new',
            'username': 'postgres-new',
        })
        self.assertEqual(response.status_code, 302)
        self.connection.refresh_from_db()
        self.assertEqual(self.connection.name, 'Updated Name')
        self.assertEqual(self.connection.host, 'localhost-new')
        self.assertEqual(self.connection.port, 5433)
        self.assertEqual(self.connection.database_name, 'test_db_new')
        self.assertEqual(self.connection.username, 'postgres-new')
        # Verify the password was NOT cleared since we left password blank
        self.assertEqual(self.connection.get_password(), 'mysecretpass')

    def test_connection_edit_post_with_new_password(self):
        self.client.login(username='testuser', password='password123')
        response = self.client.post(reverse('connections:edit', args=[self.connection.id]), {
            'name': 'Updated Name',
            'connection_type': 'postgresql',
            'host': 'localhost-new',
            'port': 5433,
            'database_name': 'test_db_new',
            'username': 'postgres-new',
            'password': 'newpassword123',
        })
        self.assertEqual(response.status_code, 302)
        self.connection.refresh_from_db()
        self.assertEqual(self.connection.get_password(), 'newpassword123')

    def test_connection_delete_post(self):
        self.client.login(username='testuser', password='password123')
        response = self.client.post(reverse('connections:delete', args=[self.connection.id]))
        self.assertEqual(response.status_code, 302)
        self.connection.refresh_from_db()
        self.assertFalse(self.connection.is_active)

    def test_file_connection_lifecycle(self):
        import os
        from django.core.files.uploadedfile import SimpleUploadedFile
        from .connector import ConnectorEngine

        # Create a mock CSV file content
        csv_content = b"emp_id,name,salary\n101,Alice,50000\n102,Bob,60000\n103,Charlie,70000"
        uploaded_file = SimpleUploadedFile("employees.csv", csv_content, content_type="text/csv")
        
        # Create a file data connection
        file_conn = DataConnection.objects.create(
            name='File Connection',
            connection_type='csv',
            file=uploaded_file,
            created_by=self.user
        )
        
        try:
            # 1. Test engine introspection (get_tables)
            engine = ConnectorEngine(file_conn)
            tables = engine.get_tables()
            self.assertEqual(len(tables), 1)
            self.assertTrue(tables[0].endswith('employees.csv'))
            
            # 2. Test engine introspection (get_columns)
            columns = engine.get_columns(table=tables[0])
            column_names = [col['name'] for col in columns]
            self.assertIn('emp_id', column_names)
            self.assertIn('name', column_names)
            self.assertIn('salary', column_names)
            
            # 3. Test reading the file
            read_df = engine.read_file(table=tables[0])
            self.assertEqual(len(read_df), 3)
            self.assertEqual(list(read_df['emp_id']), [101, 102, 103])
            
            # 4. Test connection testing
            success, msg = engine.test_connection()
            self.assertTrue(success)
            self.assertIn('File readable', msg)
            
        finally:
            # Cleanup files
            if file_conn.file and os.path.exists(file_conn.file.path):
                try:
                    os.remove(file_conn.file.path)
                except Exception:
                    pass

    def test_databricks_catalog_endpoints(self):
        self.client.login(username='testuser', password='password123')
        # Create a Databricks connection (mocked due to dummy host)
        db_conn = DataConnection.objects.create(
            name='Databricks Mock',
            connection_type='databricks',
            host='dummy-host',
            database_name='default',
            created_by=self.user
        )
        
        # Test GET /connections/api/catalogs/
        response = self.client.get(reverse('connections:api_catalogs'), {'connection_id': db_conn.id})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('catalogs', data)
        self.assertListEqual(data['catalogs'], ['hive_metastore', 'default', 'prod_catalog'])

        # Test GET /connections/api/schemas/ with catalog
        response = self.client.get(reverse('connections:api_schemas'), {'connection_id': db_conn.id, 'catalog': 'prod_catalog'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('schemas', data)
        self.assertListEqual(data['schemas'], ['prod_catalog_schema', 'default'])

        # Test GET /connections/api/tables/ with schema and catalog
        response = self.client.get(reverse('connections:api_tables'), {'connection_id': db_conn.id, 'schema': 'default', 'catalog': 'prod_catalog'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('tables', data)
        self.assertIn('customers', data['tables'])

        # Test GET /connections/api/columns/ with table, schema, and catalog
        response = self.client.get(reverse('connections:api_columns'), {
            'connection_id': db_conn.id,
            'schema': 'default',
            'table': 'customers',
            'catalog': 'prod_catalog'
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('columns', data)
        col_names = [col['name'] for col in data['columns']]
        self.assertIn('customer_id', col_names)

    def test_lakehouse_catalog_endpoints(self):
        self.client.login(username='testuser', password='password123')
        # Create a Lakehouse connection (mocked due to dummy host)
        lakehouse_conn = DataConnection.objects.create(
            name='Lakehouse Mock',
            connection_type='lakehouse',
            host='dummy-host',
            database_name='default',
            created_by=self.user
        )
        
        # Test GET /connections/api/catalogs/
        response = self.client.get(reverse('connections:api_catalogs'), {'connection_id': lakehouse_conn.id})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('catalogs', data)
        self.assertListEqual(data['catalogs'], ['hive_metastore', 'default', 'prod_catalog'])

        # Test GET /connections/api/schemas/ with catalog
        response = self.client.get(reverse('connections:api_schemas'), {'connection_id': lakehouse_conn.id, 'catalog': 'prod_catalog'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('schemas', data)
        self.assertListEqual(data['schemas'], ['prod_catalog_schema', 'default'])

        # Test GET /connections/api/tables/ with schema and catalog
        response = self.client.get(reverse('connections:api_tables'), {'connection_id': lakehouse_conn.id, 'schema': 'default', 'catalog': 'prod_catalog'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('tables', data)
        self.assertIn('customers', data['tables'])

        # Test GET /connections/api/columns/ with table, schema, and catalog
        response = self.client.get(reverse('connections:api_columns'), {
            'connection_id': lakehouse_conn.id,
            'schema': 'default',
            'table': 'customers',
            'catalog': 'prod_catalog'
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('columns', data)
        col_names = [col['name'] for col in data['columns']]
        self.assertIn('customer_id', col_names)

    def test_db2_schemas_endpoint(self):
        self.client.login(username='testuser', password='password123')
        db2_conn = DataConnection.objects.create(
            name='DB2 Mock Connection',
            connection_type='db2',
            host='dummy-db2-host',
            database_name='SAMPLEDB',
            username='db2admin',
            created_by=self.user
        )

        response = self.client.get(reverse('connections:api_schemas'), {'connection_id': db2_conn.id})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('schemas', data)
        self.assertFalse(data['is_file'])
        self.assertIn('DB2ADMIN', data['schemas'])
        self.assertIn('SAMPLEDB', data['schemas'])
        self.assertIn('DB2INST1', data['schemas'])

    def test_db2_tables_endpoint(self):
        self.client.login(username='testuser', password='password123')
        db2_conn = DataConnection.objects.create(
            name='DB2 Mock Connection',
            connection_type='db2',
            host='dummy-db2-host',
            database_name='SAMPLEDB',
            username='db2admin',
            created_by=self.user
        )

        response = self.client.get(reverse('connections:api_tables'), {'connection_id': db2_conn.id, 'schema': 'DB2ADMIN'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('tables', data)
        self.assertIn('customers', data['tables'])

    def test_excel_and_text_connection_lifecycle(self):
        import os
        import tempfile
        import pandas as pd
        from django.core.files.uploadedfile import SimpleUploadedFile
        from .connector import ConnectorEngine

        # 1. Test Text File Connection
        txt_content = b"emp_id,name,salary\n101,Alice,50000\n102,Bob,60000\n103,Charlie,70000"
        uploaded_txt = SimpleUploadedFile("employees.txt", txt_content, content_type="text/plain")
        text_conn = DataConnection.objects.create(
            name='Text Connection',
            connection_type='text',
            file=uploaded_txt,
            created_by=self.user
        )
        
        try:
            engine_txt = ConnectorEngine(text_conn)
            tables_txt = engine_txt.get_tables()
            self.assertEqual(len(tables_txt), 1)
            self.assertTrue(tables_txt[0].endswith('employees.txt'))
            
            columns_txt = engine_txt.get_columns(table=tables_txt[0])
            column_names_txt = [col['name'] for col in columns_txt]
            self.assertIn('emp_id', column_names_txt)
            self.assertIn('name', column_names_txt)
            self.assertIn('salary', column_names_txt)
            
            read_df_txt = engine_txt.read_file(table=tables_txt[0])
            self.assertEqual(len(read_df_txt), 3)
            self.assertEqual(list(read_df_txt['emp_id']), [101, 102, 103])
            
            success_txt, msg_txt = engine_txt.test_connection()
            self.assertTrue(success_txt)
        finally:
            if text_conn.file and os.path.exists(text_conn.file.path):
                try:
                    os.remove(text_conn.file.path)
                except Exception:
                    pass

        # 2. Test Excel File Connection
        df = pd.DataFrame({'emp_id': [101, 102, 103], 'name': ['Alice', 'Bob', 'Charlie'], 'salary': [50000, 60000, 70000]})
        with tempfile.TemporaryDirectory() as tmpdir:
            excel_path = os.path.join(tmpdir, "employees.xlsx")
            df.to_excel(excel_path, index=False)
            with open(excel_path, 'rb') as f:
                excel_bytes = f.read()
        
        uploaded_excel = SimpleUploadedFile("employees.xlsx", excel_bytes, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        excel_conn = DataConnection.objects.create(
            name='Excel Connection',
            connection_type='excel',
            file=uploaded_excel,
            created_by=self.user
        )
        
        try:
            engine_excel = ConnectorEngine(excel_conn)
            tables_excel = engine_excel.get_tables()
            self.assertEqual(len(tables_excel), 1)
            self.assertTrue(tables_excel[0].endswith('employees.xlsx'))
            
            columns_excel = engine_excel.get_columns(table=tables_excel[0])
            column_names_excel = [col['name'] for col in columns_excel]
            self.assertIn('emp_id', column_names_excel)
            self.assertIn('name', column_names_excel)
            self.assertIn('salary', column_names_excel)
            
            read_df_excel = engine_excel.read_file(table=tables_excel[0])
            self.assertEqual(len(read_df_excel), 3)
            self.assertEqual(list(read_df_excel['emp_id']), [101, 102, 103])
            
            success_excel, msg_excel = engine_excel.test_connection()
            self.assertTrue(success_excel)
        finally:
            if excel_conn.file and os.path.exists(excel_conn.file.path):
                try:
                    os.remove(excel_conn.file.path)
                except Exception:
                    pass

    def test_connection_string_generation(self):
        # 1. Test PostgreSQL connection string
        conn_pg = DataConnection.objects.create(
            name='Test PG ConnStr',
            connection_type='postgresql',
            host='10.0.0.1',
            port=5432,
            database_name='my_db',
            username='user1',
            created_by=self.user
        )
        conn_pg.set_password('pass123')
        self.assertEqual(
            conn_pg.get_connection_string(),
            'postgresql+psycopg2://user1:pass123@10.0.0.1:5432/my_db'
        )

        # 2. Test Databricks connection string with URL encoding
        conn_db = DataConnection.objects.create(
            name='Test DB ConnStr',
            connection_type='databricks',
            host='databricks-host',
            database_name='sql/protocolv1/o/123/http_path_value',
            username='',
            created_by=self.user
        )
        conn_db.set_password('dapi token 123')
        self.assertEqual(
            conn_db.get_connection_string(),
            'databricks://token:dapi+token+123@databricks-host?http_path=sql/protocolv1/o/123/http_path_value'
        )

        # 3. Test SQL Server (sqlserver) connection string default pyodbc
        conn_sql = DataConnection.objects.create(
            name='Test SQL ConnStr default',
            connection_type='sqlserver',
            host='10.0.0.2',
            port=1433,
            database_name='sales_db',
            username='sa',
            created_by=self.user
        )
        conn_sql.set_password('Secret@123!')
        self.assertEqual(
            conn_sql.get_connection_string(),
            'mssql+pyodbc://sa:Secret%40123%21@10.0.0.2:1433/sales_db?driver=ODBC+Driver+17+for+SQL+Server'
        )

        # 4. Test SQL Server (sqlserver) connection string with pymssql driver override
        conn_sql_py = DataConnection.objects.create(
            name='Test SQL ConnStr pymssql',
            connection_type='sqlserver',
            host='10.0.0.2',
            port=1433,
            database_name='sales_db',
            username='sa',
            driver='pymssql',
            created_by=self.user
        )
        conn_sql_py.set_password('Secret@123!')
        self.assertEqual(
            conn_sql_py.get_connection_string(),
            'mssql+pymssql://sa:Secret%40123%21@10.0.0.2:1433/sales_db'
        )

    def test_lakehouse_parameter_conversion(self):
        from unittest.mock import MagicMock, patch
        import pandas as pd
        from connections.connector import ConnectorEngine

        lakehouse_conn = DataConnection.objects.create(
            name='Test Lakehouse',
            connection_type='lakehouse',
            host='lakehouse-host',
            port=8443,
            database_name='lakehouse_db',
            username='user',
            created_by=self.user
        )
        engine = ConnectorEngine(lakehouse_conn)

        with patch.object(engine, 'is_mocked', return_value=False), \
             patch.object(engine, 'get_lakehouse_connection') as mock_get_conn, \
             patch('pandas.read_sql') as mock_read_sql:
            
            mock_conn = MagicMock()
            mock_get_conn.return_value = mock_conn
            mock_read_sql.return_value = pd.DataFrame([{'result': 42}])

            query = "SELECT COUNT(*) AS result FROM my_table WHERE created_at >= :date_start AND created_at <= :date_end"
            params = {'date_start': '2026-01-01T00:00', 'date_end': '2026-01-10T14:30'}

            res = engine.execute_query(query, params)

            # Assert that read_sql was called with the modified query containing '?' and positional params list
            expected_query = "SELECT COUNT(*) AS result FROM my_table WHERE created_at >= ? AND created_at <= ?"
            expected_params = ['2026-01-01', '2026-01-10 14:30']

            mock_read_sql.assert_called_once_with(expected_query, mock_conn, params=expected_params)

    def test_db2_odbc_connection_string_generation(self):
        import urllib.parse
        # 1. Test standard default pyodbc driver
        conn_db2 = DataConnection.objects.create(
            name='Test DB2 ODBC',
            connection_type='db2',
            host='db2-host',
            port=50001,
            database_name='db2_db',
            username='db2user',
            driver='pyodbc',
            created_by=self.user
        )
        conn_db2.set_password('db2pass')
        conn_str = conn_db2.get_connection_string()
        self.assertIn('db2+pyodbc:///?odbc_connect=', conn_str)
        # Verify it contains URL-encoded driver name {IBM DB2}
        decoded = urllib.parse.unquote_plus(conn_str)
        self.assertIn('DRIVER={IBM DB2}', decoded)
        self.assertIn('HOSTNAME=db2-host', decoded)
        self.assertIn('PORT=50001', decoded)
        self.assertIn('DATABASE=db2_db', decoded)
        self.assertIn('UID=db2user', decoded)
        self.assertIn('PWD=db2pass', decoded)

        # 2. Test custom DRIVER parameter in driver field
        conn_db2_custom = DataConnection.objects.create(
            name='Test DB2 Custom ODBC',
            connection_type='db2',
            host='db2-host-2',
            port=50002,
            database_name='db2_db_2',
            username='db2user2',
            driver='pyodbc;DRIVER={IBM DB2_64}',
            created_by=self.user
        )
        conn_db2_custom.set_password('db2pass2')
        conn_str_custom = conn_db2_custom.get_connection_string()
        decoded_custom = urllib.parse.unquote_plus(conn_str_custom)
        self.assertIn('DRIVER={IBM DB2_64}', decoded_custom)
        self.assertIn('HOSTNAME=db2-host-2', decoded_custom)

        # 3. Test direct file path driver (no curly braces)
        conn_db2_path = DataConnection.objects.create(
            name='Test DB2 Path ODBC',
            connection_type='db2',
            host='db2-host-3',
            port=50003,
            database_name='db2_db_3',
            username='db2user3',
            driver='pyodbc;DRIVER=/usr/lib/db2/odbc_cli/clidriver/lib/libdb2o.so',
            created_by=self.user
        )
        conn_db2_path.set_password('db2pass3')
        conn_str_path = conn_db2_path.get_connection_string()
        decoded_path = urllib.parse.unquote_plus(conn_str_path)
        self.assertIn('DRIVER=/usr/lib/db2/odbc_cli/clidriver/lib/libdb2o.so', decoded_path)

    def test_azure_blob_connection(self):
        from unittest.mock import patch, MagicMock
        from .connector import ConnectorEngine
        
        # Create an Azure Blob connection
        azure_conn = DataConnection.objects.create(
            name='Test Azure Blob',
            connection_type='azure_blob',
            host='blob/mkt-shared/Qualix',
            database_name='data1',
            username='myaccount',
            created_by=self.user
        )
        azure_conn.set_password('mysecretkey')
        azure_conn.save()

        # Mock the entire BlobServiceClient structure
        mock_client = MagicMock()
        mock_container_client = MagicMock()
        mock_blob_client = MagicMock()
        
        # mock_container_client.list_blobs returns some dummy blob names
        mock_blob1 = MagicMock()
        mock_blob1.name = 'blob/mkt-shared/Qualix/sales.csv'
        mock_blob2 = MagicMock()
        mock_blob2.name = 'blob/mkt-shared/Qualix/customers.parquet'
        mock_blob3 = MagicMock()
        mock_blob3.name = 'blob/mkt-shared/Qualix/other.txt'
        mock_blob4 = MagicMock()
        mock_blob4.name = 'blob/mkt-shared/Qualix/subfolder/' # directory placeholder
        
        mock_container_client.list_blobs.return_value = [mock_blob1, mock_blob2, mock_blob3, mock_blob4]
        
        # download_blob returns a stream with content
        mock_stream = MagicMock()
        mock_stream.readall.return_value = b"col1,col2\nval1,val2"
        mock_blob_client.download_blob.return_value = mock_stream
        
        mock_container_client.get_blob_client.return_value = mock_blob_client
        mock_client.get_container_client.return_value = mock_container_client

        with patch('connections.connector.BlobServiceClient') as mock_blob_service_class:
            # Configure dynamic import mock
            mock_blob_service_class.from_connection_string.return_value = mock_client
            mock_blob_service_class.return_value = mock_client
            
            engine = ConnectorEngine(azure_conn)
            
            # Test get_tables()
            tables = engine.get_tables()
            # The prefix is 'blob/mkt-shared/Qualix/' so tables should be relative
            self.assertEqual(tables, ['customers.parquet', 'other.txt', 'sales.csv'])
            
            # Test read_file()
            df = engine.read_file(table='sales.csv')
            self.assertIsNotNone(df)
            self.assertEqual(list(df.columns), ['col1', 'col2'])
            self.assertEqual(df.shape[0], 1)
            
            # Test with container auto-parse from host
            azure_conn.database_name = ''
            azure_conn.host = 'data1/blob/mkt-shared/Qualix'
            azure_conn.save()
            
            tables_auto = engine.get_tables()
            self.assertEqual(tables_auto, ['customers.parquet', 'other.txt', 'sales.csv'])

            # Test custom endpoint (full URL)
            azure_conn.driver = 'http://127.0.0.1:10000/devstoreaccount1'
            azure_conn.save()
            engine.get_tables()
            mock_blob_service_class.assert_called_with(
                account_url='http://127.0.0.1:10000/devstoreaccount1',
                credential='mysecretkey'
            )

            # Test custom endpoint suffix
            azure_conn.driver = 'blob.core.chinacloudapi.cn'
            azure_conn.save()
            engine.get_tables()
            mock_blob_service_class.assert_called_with(
                account_url='https://myaccount.blob.core.chinacloudapi.cn',
                credential='mysecretkey'
            )


