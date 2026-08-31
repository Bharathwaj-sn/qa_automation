from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from app.models.metadata import MetadataCatalog, MetadataSnapshot, MetadataSchema, MetadataTable


class MetadataSnapshotNotFoundError(RuntimeError):
    pass


class MetadataTableNotFoundError(RuntimeError):
    def __init__(self, catalog_name: str, schema_name: str, table_name: str):
        super().__init__(f"Table '{catalog_name}.{schema_name}.{table_name}' was not found in the metadata snapshot.")


class MetadataRepository:
    def __init__(self, file_path: str | Path | None = None):
        base_path = Path(file_path) if file_path else Path(__file__).resolve().parents[2] / "data" / "metadata" / "metadata.json"
        self.file_path = Path(base_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)

    def _empty_snapshot(self) -> MetadataSnapshot:
        # build an empty snapshot with refresh.scope present but empty
        refresh = {
            "status": "SUCCESS",
            "refreshed_at": datetime.now(timezone.utc),
            "scope": {"type": "catalog", "catalog_name": ""},
        }
        return MetadataSnapshot(
            metadata_version="1.0",
            refresh=refresh,  # type: ignore[arg-type]
            catalogs=[],
        )

    def _atomic_write(self, data: dict) -> None:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.file_path.with_suffix(".json.tmp")
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
            handle.write("\n")
        temp_path.replace(self.file_path)

    def load_snapshot(self) -> MetadataSnapshot | None:
        if not self.file_path.exists():
            return None

        with self.file_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)

        return MetadataSnapshot.model_validate(data)

    def exists(self) -> bool:
        return self.file_path.exists()

    def _find_catalog(self, snapshot: MetadataSnapshot, catalog_name: str) -> MetadataCatalog | None:
        for catalog in snapshot.catalogs:
            if catalog.name == catalog_name:
                return catalog
        return None

    def _find_schema(self, catalog: MetadataCatalog, schema_name: str) -> MetadataSchema | None:
        for schema in catalog.schemas:
            if schema.name == schema_name:
                return schema
        return None

    def _find_table(self, schema: MetadataSchema, table_name: str) -> MetadataTable | None:
        for table in schema.tables:
            if table.name.casefold() == table_name.casefold():
                return table
        return None

    def get_table_metadata(self, catalog_name: str, schema_name: str, table_name: str) -> MetadataTable:
        snapshot = self.load_snapshot()
        if snapshot is None:
            raise MetadataSnapshotNotFoundError("No metadata snapshot has been generated yet.")

        catalog = self._find_catalog(snapshot, catalog_name)
        schema = self._find_schema(catalog, schema_name) if catalog else None
        table = self._find_table(schema, table_name) if schema else None
        if table is None:
            raise MetadataTableNotFoundError(catalog_name, schema_name, table_name)
        return table

    def save_snapshot(self, snapshot: MetadataSnapshot | dict) -> MetadataSnapshot | dict:
        if isinstance(snapshot, MetadataSnapshot):
            payload = snapshot.model_dump(mode="json")
        else:
            # accept older dicts that might have top-level 'scope' and move into refresh
            payload = dict(snapshot)
            if "scope" in payload and "refresh" in payload and isinstance(payload["refresh"], dict):
                # move top-level scope into refresh.scope if not already present
                if "scope" not in payload["refresh"]:
                    payload["refresh"]["scope"] = payload.pop("scope")
            elif "scope" in payload and "refresh" not in payload:
                payload["refresh"] = {"scope": payload.pop("scope")}

        self._atomic_write(payload)
        return snapshot

    def update_table_metadata(self, catalog_name: str, schema_name: str, table_name: str, table_data: MetadataTable) -> MetadataSnapshot:
        snapshot = self.load_snapshot() or self._empty_snapshot()
        catalog = self._find_catalog(snapshot, catalog_name)
        if catalog is None:
            catalog = MetadataCatalog(name=catalog_name, schemas=[])
            snapshot.catalogs.append(catalog)

        schema = self._find_schema(catalog, schema_name)
        if schema is None:
            schema = MetadataSchema(name=schema_name, tables=[], volumes=[])
            catalog.schemas.append(schema)

        existing_table = self._find_table(schema, table_name)
        if existing_table is not None:
            for index, current_table in enumerate(schema.tables):
                if current_table.name == table_name:
                    schema.tables[index] = table_data
                    break
        else:
            schema.tables.append(table_data)

        self._atomic_write(snapshot.model_dump(mode="json"))
        return snapshot

    def update_schema_metadata(self, catalog_name: str, schema_name: str, schema_data: MetadataSchema) -> MetadataSnapshot:
        snapshot = self.load_snapshot() or self._empty_snapshot()
        catalog = self._find_catalog(snapshot, catalog_name)
        if catalog is None:
            catalog = MetadataCatalog(name=catalog_name, schemas=[])
            snapshot.catalogs.append(catalog)

        existing_schema = self._find_schema(catalog, schema_name)
        if existing_schema is not None:
            existing_schema.metadata = deepcopy(schema_data.metadata)
            existing_schema.tables = deepcopy(schema_data.tables)
            existing_schema.volumes = deepcopy(schema_data.volumes)
        else:
            catalog.schemas.append(deepcopy(schema_data))

        self._atomic_write(snapshot.model_dump(mode="json"))
        return snapshot

    def update_catalog_metadata(self, catalog_name: str, catalog_data: MetadataCatalog) -> MetadataSnapshot:
        snapshot = self.load_snapshot() or self._empty_snapshot()
        existing_catalog = self._find_catalog(snapshot, catalog_name)
        if existing_catalog is not None:
            existing_catalog.metadata = deepcopy(catalog_data.metadata)
            existing_catalog.schemas = deepcopy(catalog_data.schemas)
        else:
            snapshot.catalogs.append(deepcopy(catalog_data))

        self._atomic_write(snapshot.model_dump(mode="json"))
        return snapshot

    def get_metadata_document(self) -> dict:
        if not self.file_path.exists():
            return {"metadata_version": "1.0", "catalogs": []}
        with self.file_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def get_summary(self) -> dict:
        document = self.get_metadata_document()
        catalogs = document.get("catalogs", [])
        catalog_count = len(catalogs)
        schema_count = 0
        table_count = 0
        volume_count = 0
        last_refreshed_at = None

        for catalog in catalogs:
            for schema in catalog.get("schemas", []):
                schema_count += 1
                for table in schema.get("tables", []):
                    table_count += 1
                    metadata = table.get("metadata", {})
                    if metadata.get("refreshed_at"):
                        last_refreshed_at = metadata["refreshed_at"]
                for volume in schema.get("volumes", []):
                    volume_count += 1

        if last_refreshed_at is None:
            for catalog in catalogs:
                if catalog.get("metadata", {}).get("refreshed_at"):
                    last_refreshed_at = catalog["metadata"]["refreshed_at"]
                    break

        return {
            "catalog_count": catalog_count,
            "schema_count": schema_count,
            "table_count": table_count,
            "volume_count": volume_count,
            "last_refreshed_at": last_refreshed_at,
            "status": "SUCCESS",
        }
