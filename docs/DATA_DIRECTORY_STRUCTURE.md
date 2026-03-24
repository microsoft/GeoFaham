# GeoFaham Data & Artifacts Directory Structure

## Best Practices for File Storage

### 1. Directory Structure

```
GeoFaham/
├── data/                           # Static data files (REQUIRED - copy from v0)
│   ├── stac/
│   │   └── stac_output_mpc_clean.json    # STAC band metadata
│   └── worldpop/                   # Population raster tiles (if needed)
│
├── runtime/                        # Runtime-generated files (gitignored)
│   ├── artifacts/                  # Generated GeoJSON, COG files
│   │   └── query_jsons/           # Tool outputs (auto-cleaned)
│   ├── state/                      # Session state
│   │   ├── team_state.json        # Agent team state
│   │   └── response_store.jsonl   # Tool response history
│   ├── history/                    # Conversation logs
│   │   └── conversation_history.json
│   └── user_data/                  # User uploads
│       └── user_artifacts.json
│
├── agents/                         # Agent code (version controlled)
├── backend/                        # API routes
├── frontend/                       # UI assets
└── ...
```

### 2. File Categories

#### A. Static Data Files (Version Controlled or Copied)
These are reference data that don't change during runtime:

| File | Current Location | Recommended Location | Purpose |
|------|-----------------|---------------------|---------|
| `stac_output_mpc_clean.json` | `dump/notebooks/` | `data/stac/` | STAC band metadata for rescale values |
| `schema.json` | `./` | `data/db/` | Cached database schema |
| `disasters_summary.json` | `backend/db/` | `data/db/` | Disaster catalog |

#### B. Runtime Artifacts (Ephemeral, Gitignored)
Generated during tool execution, can be cleaned periodically:

| File Pattern | Purpose | Retention |
|--------------|---------|-----------|
| `stac_results_*.geojson` | STAC search results | Session |
| `raster_code_result_*.tif` | Raster analysis COGs | Session |
| `vector_code_result_*.geojson` | Vector analysis results | Session |
| `osm_*.geojson` | OSM feature extractions | Session |
| `stac_mosaic_*.json` | MosaicJSON tiles | Session |

#### C. Persistent State Files (Gitignored but Important)
Session state that persists across restarts:

| File | Purpose | Backup Strategy |
|------|---------|-----------------|
| `response_store.jsonl` | Tool call history with artifacts | Daily backup |
| `team_state.json` | Agent team checkpoint | Per-session backup |
| `conversation_history.json` | Chat history | Per-session backup |
| `user_artifacts.json` | User upload registry | Per-session backup |

---

## 3. Configuration Updates

### agents/core/config.py - PathsConfig

```python
@dataclass
class PathsConfig:
    """File system paths configuration."""
    
    # Base directories
    base_dir: Path = field(
        default_factory=lambda: Path(os.getenv("GEOFAHAM_BASE_DIR", "./runtime"))
    )
    data_dir: Path = field(
        default_factory=lambda: Path(os.getenv("GEOFAHAM_DATA_DIR", "./data"))
    )
    
    # Static data paths
    band_metadata_path: Optional[str] = field(
        default_factory=lambda: os.getenv("STAC_BAND_METADATA_PATH")
    )
    
    @property
    def stac_band_metadata(self) -> Path:
        """Path to STAC band metadata JSON."""
        if self.band_metadata_path:
            return Path(self.band_metadata_path)
        return self.data_dir / "stac" / "stac_output_mpc_clean.json"
    
    @property
    def export_dir(self) -> Path:
        """Directory for exported GeoJSON/COG files."""
        path = self.base_dir / "artifacts" / "query_jsons"
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    @property
    def state_dir(self) -> Path:
        """Directory for state files."""
        path = self.base_dir / "state"
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    @property
    def user_data_dir(self) -> Path:
        """Directory for user uploaded data."""
        path = self.base_dir / "user_data"
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    @property
    def response_store_path(self) -> Path:
        """Path to response store file."""
        return self.state_dir / "response_store.jsonl"
    
    @property
    def team_state_path(self) -> Path:
        """Path to team state file."""
        return self.state_dir / "team_state.json"
    
    @property
    def conversation_history_path(self) -> Path:
        """Path to conversation history."""
        return self.base_dir / "history" / "conversation_history.json"
```

---

## 4. Environment Variables

Add to `.env.example`:

```bash
# =============================================================================
# Directory Configuration
# =============================================================================

# Runtime directory (artifacts, state, history) - gitignored
GEOFAHAM_BASE_DIR=./runtime

# Static data directory (STAC metadata, schemas)
GEOFAHAM_DATA_DIR=./data

# Override specific paths (optional)
STAC_BAND_METADATA_PATH=
TEAM_STATE_PATH=
CONVERSATION_HISTORY_PATH=
USER_DATA_PATH=
RESPONSE_STORE_PATH=
```

---

## 5. Files to Copy from v0 Project

### Required Files:

```bash
# Create data directory structure
mkdir -p data/stac data/db

# Copy STAC band metadata (REQUIRED for band rescale values)
cp <v0_project>/dump/notebooks/stac_output_mpc_clean.json data/stac/

# Copy disaster summary if exists
cp <v0_project>/backend/db/disasters_summary.json data/db/ 2>/dev/null || true

# Copy schema cache if exists
cp <v0_project>/schema.json data/db/ 2>/dev/null || true
```

### Optional Files (if you have them):

```bash
# Population data tiles
cp -r <v0_project>/worldpop_tiles/ data/worldpop/ 2>/dev/null || true

# Benchmark ground truth
cp -r <v0_project>/benchmark_gt/ data/benchmark/ 2>/dev/null || true
```

---

## 6. .gitignore Updates

```gitignore
# Runtime artifacts (generated during execution)
runtime/
dump/

# But keep the directory structure
!runtime/.gitkeep
!dump/.gitkeep

# State files (contain session data)
**/response_store.jsonl
**/team_state.json
**/conversation_history.json
**/user_artifacts.json

# Generated outputs
*.tif
*.geojson
!data/**/*.geojson
*.json
!data/**/*.json
!backend/db/*.json
!package.json

# Cache
__pycache__/
*.pyc
.cache/
osmnx_cache/
```

---

## 7. Cleanup Scripts

### cleanup_artifacts.py

```python
#!/usr/bin/env python3
"""Clean up old runtime artifacts."""

import os
import time
from pathlib import Path

def cleanup_old_files(directory: Path, max_age_hours: int = 24):
    """Remove files older than max_age_hours."""
    if not directory.exists():
        return
    
    now = time.time()
    max_age_seconds = max_age_hours * 3600
    
    for file in directory.glob("**/*"):
        if file.is_file():
            age = now - file.stat().st_mtime
            if age > max_age_seconds:
                print(f"Removing {file} (age: {age/3600:.1f}h)")
                file.unlink()

if __name__ == "__main__":
    runtime_dir = Path(os.getenv("GEOFAHAM_BASE_DIR", "./runtime"))
    cleanup_old_files(runtime_dir / "artifacts", max_age_hours=24)
```

---

## 8. Migration Checklist

- [ ] Create `data/` directory structure
- [ ] Copy `stac_output_mpc_clean.json` to `data/stac/`
- [ ] Update `agents/core/config.py` with new PathsConfig
- [ ] Update `backend/routes/config.py` to use agents config
- [ ] Update `.env.example` with directory variables
- [ ] Update `.gitignore` for new structure
- [ ] Create `runtime/.gitkeep` to preserve directory in git
- [ ] Test all file paths work correctly
