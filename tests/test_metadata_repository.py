from data_health_monitor.models.metadata import MetadataRefreshInfo, MetadataSnapshot
from data_health_monitor.repositories.metadata_repository import MetadataRepository, MetadataTableNotFoundError


def test_get_table_metadata_reads_the_selected_table_from_the_persisted_snapshot(tmp_path):
    repository = MetadataRepository(file_path=tmp_path / "metadata.json")
    repository.save_snapshot(
        MetadataSnapshot.model_validate(
            {
                "refresh": MetadataRefreshInfo().model_dump(mode="json"),
                "catalogs": [
                    {
                        "name": "main",
                        "schemas": [
                            {
                                "name": "sales",
                                "tables": [
                                    {"catalog_name": "main", "schema_name": "sales", "name": "claims"}
                                ],
                            }
                        ],
                    }
                ],
            }
        )
    )

    table = repository.get_table_metadata("main", "sales", "CLAIMS")

    assert table.name == "claims"
    assert table.schema_name == "sales"

    try:
        repository.get_table_metadata("main", "sales", "members")
    except MetadataTableNotFoundError:
        pass
    else:
        raise AssertionError("Expected a missing metadata table error.")