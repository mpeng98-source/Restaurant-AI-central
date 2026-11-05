"""Historical migrations must remain byte-for-byte stable across the stack."""
import hashlib
from pathlib import Path


def test_four_historical_migrations_are_unchanged():
    expected={
        '0001_foundation.py':'a1dc8ce0edd4dc776ce9cb71ec61cf648eef6f8209828a585441f75a84842e2d',
        '0002_inventory.py':'6730095587156c0506e416f4a9486d17e60ed55e70c493ae8c6924555fef9f10',
        '0003_inventory_counting.py':'c9290a0d20d7469fc63c1b6a6f77186218bc4bfba19938e7948dd2381e4a65c2',
        '0004_inventory_approvals.py':'c1aa5a9126ddec1f7177a8954c85b3b529e92185dc42dc6f896aaad6cf9bfe08',
    }
    root=Path(__file__).resolve().parents[1]/'migrations'/'versions'
    assert {file:hashlib.sha256((root/file).read_bytes()).hexdigest() for file in expected}==expected
