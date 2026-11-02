import pytest
from app.ingest import run_sync
from pathlib import Path

def test_ingest_sync_logic(mocker):
    # Mock file system and Qdrant state
    mocker.patch('app.ingest.get_local_files', return_value={
        "file1.md": "hash1",
        "file2.md": "hash2_new",
        "file3.md": "hash3"
    })

    mocker.patch('app.ingest.get_qdrant_files', return_value={
        "file1.md": "hash1",
        "file2.md": "hash2_old",
        "file4.md": "hash4"
    })

    mock_delete = mocker.patch('app.ingest.delete_file_chunks')
    mock_ingest = mocker.patch('app.ingest.ingest_file')

    # Run sync
    run_sync()

    # Assertions
    # file1: no change (no calls)
    # file2: update (delete + ingest)
    # file3: add (ingest)
    # file4: delete (delete)

    assert mock_delete.call_count == 2 # file2, file4
    assert mock_ingest.call_count == 2 # file2, file3

    # Check specific calls
    deleted_paths = [call.args[0] for call in mock_delete.call_args_list]
    assert "file4.md" in deleted_paths
    assert "file2.md" in deleted_paths

    ingested_paths = [call.args[1] for call in mock_ingest.call_args_list]
    assert "file2.md" in ingested_paths
    assert "file3.md" in ingested_paths
