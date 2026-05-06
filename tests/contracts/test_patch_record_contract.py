from source_registry.contracts.patch_record import PatchRecord


def test_patch_record_defaults_for_lists_and_metadata() -> None:
    record = PatchRecord(
        patch_id="P-1",
        source_name="archon",
        title="Patch title",
        status="local",
    )
    assert record.touched_files == []
    assert record.metadata == {}
    assert record.notes == ""
