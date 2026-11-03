# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Restore the portable GeoFaham snapshot into a new PostgreSQL database."""

from __future__ import annotations

import argparse
import gzip
import os
from pathlib import Path
import shlex
import shutil
import subprocess

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BACKUP_PATH = REPO_ROOT / 'data/backups/geofaham_data_v1.sql.gz'


def load_environment() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        # Only database settings are needed when running before dependency setup.
        path = REPO_ROOT / '.env'
        if path.exists():
            for line in path.read_text().splitlines():
                key, sep, value = line.strip().removeprefix('export ').partition('=')
                if sep and key.strip().startswith('POSTGRES_'):
                    os.environ.setdefault(key.strip(), ' '.join(shlex.split(value, comments=True)))
    else:
        load_dotenv(REPO_ROOT / '.env')


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backup', type=Path, default=DEFAULT_BACKUP_PATH)
    parser.add_argument('--target-db', default=os.getenv('POSTGRES_DB') or 'geofaham',
                        help='New database to create (default: POSTGRES_DB or geofaham).')
    parser.add_argument('--maintenance-db', default=os.getenv('POSTGRES_MAINTENANCE_DB') or 'postgres')
    parser.add_argument('--dry-run', action='store_true', help='Print the plan without connecting or changing databases.')
    return parser.parse_args()


def psql_cmd(database: str) -> list[str]:
    return ['psql', '-X', '-w', '--set=ON_ERROR_STOP=1',
            '-h', os.getenv('POSTGRES_HOST') or 'localhost',
            '-p', os.getenv('POSTGRES_PORT') or '5432',
            '-U', os.getenv('POSTGRES_USER') or 'postgres', '--dbname=' + database]


def connection_env() -> dict[str, str]:
    env = os.environ.copy()
    if env.get('POSTGRES_PASSWORD'):
        env['PGPASSWORD'] = env['POSTGRES_PASSWORD']
    env.setdefault('PGCONNECT_TIMEOUT', '10')
    return env


def create_database(target: str, maintenance: str) -> None:
    # Hex encoding avoids interpolating a database name into an SQL literal.
    literal = "convert_from(decode('" + target.encode().hex() + "', 'hex'), 'UTF8')"
    result = subprocess.run(
        [*psql_cmd(maintenance), '-t', '-A', '-c',
         f'SELECT 1 FROM pg_database WHERE datname = {literal}'],
        env=connection_env(), check=True, capture_output=True, text=True,
    )
    if result.stdout.strip():
        raise ValueError(f'Database {target!r} already exists. Choose a new --target-db.')
    identifier = '"' + target.replace('"', '""') + '"'
    subprocess.run(
        [*psql_cmd(maintenance), '-c',
         f"CREATE DATABASE {identifier} WITH TEMPLATE template0 ENCODING 'UTF8'"],
        env=connection_env(), check=True,
    )


def restore_backup(backup: Path, target: str) -> None:
    process = subprocess.Popen(
        [*psql_cmd(target), '--single-transaction', '--file=-'],
        stdin=subprocess.PIPE, env=connection_env(),
    )
    try:
        assert process.stdin is not None
        with gzip.open(backup, 'rb') as stream:
            shutil.copyfileobj(stream, process.stdin, length=1024 * 1024)
        process.stdin.close()
        if process.wait():
            raise subprocess.CalledProcessError(process.returncode, process.args)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()


def main() -> int:
    load_environment()
    args = parse_args()
    backup = args.backup.resolve()
    if not backup.is_file():
        raise FileNotFoundError(f'Download the database snapshot to {backup}, or provide --backup PATH.')
    if not args.target_db or '\x00' in args.target_db or len(args.target_db.encode()) > 63:
        raise ValueError('Target database name must contain 1–63 UTF-8 bytes and no null characters.')
    print(f'Backup: {backup}')
    print(f'Create new database: {args.target_db}')
    print('Restore schema and data in one transaction; existing databases are refused.')
    if args.dry_run:
        print('Dry run: no database connection or changes.')
        return 0
    if not shutil.which('psql'):
        raise RuntimeError('Install PostgreSQL 18 client tools (psql) first.')
    create_database(args.target_db, args.maintenance_db)
    try:
        restore_backup(backup, args.target_db)
    except Exception:
        print(f'Restore failed. The newly created database {args.target_db!r} remains; inspect it before retrying.')
        raise
    print(f'Restore completed. Configure POSTGRES_DB={args.target_db} in .env.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
