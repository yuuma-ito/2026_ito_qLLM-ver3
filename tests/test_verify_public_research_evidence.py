"""Ensure evidence checks reject plausible data corruption."""
import csv
import shutil

import pytest

from scripts.verify_public_research_evidence import audit, ROOT, B4, CORE, CATALOG


@pytest.fixture
def evidence_copy(tmp_path):
    baseline = audit()
    # A pending document edit may legitimately differ from HEAD. The fixture
    # tests evidence corruption independently of whether changes are committed.
    assert all(value for name, value in baseline['checks'].items()
               if name != 'inputs_equal_committed_bytes')
    for path in baseline['inputs_sha256']:
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / path, target)
    return tmp_path


@pytest.mark.parametrize('path,field,value,failed_check', [
    (CATALOG, 'F_rate_percent', '99.9', 'catalog_all_counts_and_rates'),
    (CORE / 'paired_records.csv', 'rescued', 'True', 'R_original_pair_records'),
])
def test_rejects_changed_claim(evidence_copy, path, field, value, failed_check):
    target = evidence_copy / path
    with target.open() as stream:
        reader = csv.DictReader(stream)
        columns, records = reader.fieldnames, list(reader)
    assert records[0][field] != value
    records[0][field] = value
    with target.open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(records)
    result = audit(evidence_copy)
    assert result['checks'][failed_check] is False
    assert result['passed'] is False


def test_rejects_duplicate_request(evidence_copy):
    target = evidence_copy / B4 / 'repetitions.csv'
    with target.open() as stream:
        lines = stream.readlines()
    with target.open('a') as stream:
        stream.write(lines[1])
    result = audit(evidence_copy)
    assert result['checks']['B4_request_and_success_rows'] is False
    assert result['checks']['nine_frozen_hashes'] is False
