# GeoFaham database snapshot v1

Download [`geofaham_data_v1.sql.gz`](https://huggingface.co/datasets/msohaildanish/geofaham-data/resolve/main/geofaham_data_v1.sql.gz?download=true)
from the [GeoFaham data repository](https://huggingface.co/datasets/msohaildanish/geofaham-data). The archive is hosted on Hugging Face;
the checksum and manifest are included here. The snapshot contains disaster
records, building damage assessments, flood maps, table definitions, indexes,
constraints, and sequences.

From the GeoFaham repository root:

```bash
curl --fail --location \
  --output data/backups/geofaham_data_v1.sql.gz \
  https://huggingface.co/datasets/msohaildanish/geofaham-data/resolve/main/geofaham_data_v1.sql.gz
```

## Requirements

- PostgreSQL 18 with PostGIS installed on the server.
- PostgreSQL 18 client tools (`psql`) on your PATH.
- A database role permitted to create databases and install the PostGIS extension.

## Verify the download

From this directory:

```bash
shasum -a 256 -c geofaham_data_v1.sql.gz.sha256
```

The accompanying `geofaham_data_v1.manifest.json` records the export time,
compressed file size, checksum, and exported table row counts.

## Restore

Configure the connection in the repository's `.env` file:

```dotenv
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_password
POSTGRES_DB=geofaham
```

From the repository root, preview the setup and then restore:

```bash
python3 scripts/db_init.py --dry-run
python3 scripts/db_init.py
```

The script creates the configured database and restores its schema and data in
one transaction. It refuses an existing database. If a restore fails, the newly
created database remains for inspection; choose a new target before retrying.
The snapshot already includes the schema, so do not run `schema.sql` first.

To use a different backup location or create a database with a different name:

```bash
python3 scripts/db_init.py --backup /path/to/geofaham_data_v1.sql.gz --target-db geofaham_demo
```

Set `POSTGRES_DB` to the restored database name before starting GeoFaham.

The restore role above needs elevated privileges; do not run GeoFaham with it.
Point `POSTGRES_USER` at a non-superuser role that only has `SELECT` on the
restored tables. See [execution limits](../../docs/CONFIGURATION.md#execution-limits).
