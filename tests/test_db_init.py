"""Database restore safety and destination checks without a live database."""
import gzip
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from scripts import db_init


class DatabaseRestoreTests(unittest.TestCase):
    def test_dry_run_never_connects_or_restores(self):
        with tempfile.TemporaryDirectory() as directory:
            backup = Path(directory) / 'snapshot.sql.gz'
            with gzip.open(backup, 'wb') as stream:
                stream.write(b'SELECT 1;\n')
            with patch('sys.argv', ['db_init.py', '--dry-run', '--backup', str(backup),
                                    '--target-db', 'geofaham_preview']), \
                    patch.object(db_init, 'load_environment'), \
                    patch.object(db_init.subprocess, 'run') as run, \
                    patch.object(db_init.subprocess, 'Popen') as popen:
                self.assertEqual(db_init.main(), 0)
            run.assert_not_called()
            popen.assert_not_called()

    @patch.object(db_init.subprocess, 'run')
    def test_existing_database_is_never_created_or_replaced(self, run):
        run.return_value.stdout = '1\n'
        with self.assertRaisesRegex(ValueError, 'already exists'):
            db_init.create_database('existing', 'postgres')
        self.assertEqual(run.call_count, 1)

    @patch.object(db_init.subprocess, 'run')
    def test_create_quotes_database_identifier(self, run):
        run.return_value.stdout = ''
        db_init.create_database('geo"demo', 'postgres')
        self.assertIn('CREATE DATABASE "geo""demo"', run.call_args.args[0][-1])

    @patch.object(db_init.subprocess, 'Popen')
    def test_restore_streams_data_to_selected_database_in_transaction(self, popen):
        process = Mock()
        process.wait.return_value = 0
        process.poll.return_value = 0
        popen.return_value = process
        with tempfile.TemporaryDirectory() as directory:
            backup = Path(directory) / 'snapshot.sql.gz'
            with gzip.open(backup, 'wb') as stream:
                stream.write(b'SELECT 1;\n')
            db_init.restore_backup(backup, 'geofaham_demo')
        command = popen.call_args.args[0]
        self.assertIn('--dbname=geofaham_demo', command)
        self.assertIn('--single-transaction', command)
        process.stdin.write.assert_called_once_with(b'SELECT 1;\n')

    @patch.object(db_init.subprocess, 'Popen')
    def test_restore_failure_is_reported(self, popen):
        process = Mock()
        process.wait.return_value = 1
        process.returncode = 1
        process.poll.return_value = 1
        popen.return_value = process
        with tempfile.TemporaryDirectory() as directory:
            backup = Path(directory) / 'snapshot.sql.gz'
            with gzip.open(backup, 'wb') as stream:
                stream.write(b'invalid SQL;\n')
            with self.assertRaises(subprocess.CalledProcessError):
                db_init.restore_backup(backup, 'geofaham_demo')


if __name__ == '__main__':
    unittest.main()
