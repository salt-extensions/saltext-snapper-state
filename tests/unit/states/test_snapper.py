from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from saltext.snapper_state.states import snapper


@pytest.fixture(autouse=True)
def setup_snapper_module():
    """
    Fixture to set up mock objects for __salt__ and __opts__
    before each test function.
    """
    mock_salt = MagicMock()
    mock_opts = {"test": False}
    snapper.__salt__ = mock_salt
    snapper.__opts__ = mock_opts
    yield mock_salt, mock_opts
    # Clean up after the test (optional, but good practice for globals)
    del snapper.__salt__
    del snapper.__opts__


def test_get_baseline_from_tag_single_snapshot(setup_snapper_module):
    mock_salt, _ = setup_snapper_module
    snapshots = [
        {
            "id": 1,
            "timestamp": "2023-01-01T10:00:00",
            "userdata": {"baseline_tag": "my_tag"},
        }
    ]
    mock_salt["snapper.list_snapshots"].return_value = snapshots
    result = snapper._get_baseline_from_tag("root", "my_tag")
    assert result == snapshots[0]


def test_get_baseline_from_tag_multiple_snapshots_latest(setup_snapper_module):
    mock_salt, _ = setup_snapper_module
    snapshots = [
        {
            "id": 1,
            "timestamp": "2023-01-01T10:00:00",
            "userdata": {"baseline_tag": "my_tag"},
        },
        {
            "id": 2,
            "timestamp": "2023-01-02T10:00:00",
            "userdata": {"baseline_tag": "my_tag"},
        },
        {
            "id": 3,
            "timestamp": "2023-01-01T09:00:00",
            "userdata": {"baseline_tag": "another_tag"},
        },
    ]
    mock_salt["snapper.list_snapshots"].return_value = snapshots
    result = snapper._get_baseline_from_tag("root", "my_tag")
    assert result == snapshots[1]


def test_baseline_snapshot_no_number_or_tag():
    ret = snapper.baseline_snapshot("test_baseline")
    assert not ret["result"]
    assert ret["comment"] == "Snapshot tag or number must be specified"


def test_baseline_snapshot_both_number_and_tag():
    ret = snapper.baseline_snapshot("test_baseline", number=1, tag="my_tag")
    assert not ret["result"]
    assert ret["comment"] == "Cannot use snapshot tag and number at the same time"


def test_baseline_snapshot_tag_not_found(setup_snapper_module):
    mock_salt, _ = setup_snapper_module
    mock_salt["snapper.list_snapshots"].return_value = []
    ret = snapper.baseline_snapshot("test_baseline", tag="non_existent_tag")
    assert not ret["result"]
    assert ret["comment"] == 'Baseline tag "non_existent_tag" not found'


@patch("os.path.isfile", return_value=True)
@patch("os.path.isdir", return_value=False)
def test_baseline_snapshot_test_mode_with_changes_and_ignore_file(
    mock_isdir, mock_isfile, setup_snapper_module
):
    mock_salt, mock_opts = setup_snapper_module
    mock_opts["test"] = True
    mock_salt["snapper.status"].return_value = {
        "/etc/file1": {"status": "modified"},
        "/var/log/mylog": {"status": "modified"},
    }
    mock_salt["snapper.diff"].return_value = {
        "/etc/file1": {"status": "modified", "diff": "--- a/file1\n+++ b/file1\n-old\n+new"}
    }

    ret = snapper.baseline_snapshot(
        "test_baseline", number=1, include_diff=True, ignore=["/var/log/mylog"]
    )

    assert ret["result"] is None
    assert ret["comment"] == "1 files changes are set to be undone"
    assert "/etc/file1" in ret["changes"]
    assert "/var/log/mylog" not in ret["changes"]
    assert ret["changes"]["/etc/file1"]["diff"] == "--- a/file1\n+++ b/file1\n-old\n+new"


@patch("os.path.isfile", return_value=False)
@patch("os.path.isdir", return_value=True)
def test_baseline_snapshot_test_mode_with_changes_and_ignore_directory(
    mock_isdir, mock_isfile, setup_snapper_module
):
    mock_salt, mock_opts = setup_snapper_module
    mock_opts["test"] = True
    mock_salt["snapper.status"].return_value = {
        "/etc/file1": {"status": "modified"},
        "/var/cache/data/file": {"status": "modified"},
        "/var/cache/another": {"status": "added"},
    }
    mock_salt["snapper.diff"].return_value = {
        "/etc/file1": {"status": "modified", "diff": "--- a/file1\n+++ b/file1\n-old\n+new"}
    }

    ret = snapper.baseline_snapshot(
        "test_baseline", number=1, include_diff=True, ignore=["/var/cache"]
    )

    assert ret["result"] is None
    assert ret["comment"] == "1 files changes are set to be undone"
    assert "/etc/file1" in ret["changes"]
    assert "/var/cache/data/file" not in ret["changes"]
    assert "/var/cache/another" not in ret["changes"]


def test_baseline_snapshot_test_mode_no_changes(setup_snapper_module):
    mock_salt, mock_opts = setup_snapper_module
    mock_opts["test"] = True
    mock_salt["snapper.status"].return_value = {}

    ret = snapper.baseline_snapshot("test_baseline", number=1)
    assert ret["result"] is True
    assert ret["comment"] == "Nothing to be done"
    assert not ret["changes"]


def test_baseline_snapshot_apply_mode_no_changes(setup_snapper_module):
    mock_salt, mock_opts = setup_snapper_module
    mock_opts["test"] = False
    mock_salt["snapper.status"].return_value = {}

    ret = snapper.baseline_snapshot("test_baseline", number=1)
    assert ret["result"] is True
    assert ret["comment"] == "No changes were done"
    assert not ret["changes"]
