"""Unit tests for find_watch.py — Xiaomi device detection logic."""

import sys
from pathlib import Path

# Import from src/ via conftest sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from find_watch import is_xiaomi


class MockAdv:
    """Minimal mock for bleak's AdvertisementData."""

    def __init__(
        self, service_uuids=None, service_data=None, manufacturer_data=None, local_name=None
    ):
        self.service_uuids = service_uuids or []
        self.service_data = service_data or {}
        self.manufacturer_data = manufacturer_data or {}
        self.local_name = local_name
        self.rssi = -50


class MockDev:
    """Minimal mock for bleak's BleakDevice."""

    def __init__(self, address="00:00:00:00:00:00", name=None):
        self.address = address
        self.name = name


class TestIsXiaomi:
    """is_xiaomi() flags devices with Xiaomi indicators."""

    def test_name_hint_redmi(self):
        adv = MockAdv(local_name="Redmi Watch")
        dev = MockDev()
        reasons = is_xiaomi(dev, adv)
        assert len(reasons) >= 1
        assert any("redmi" in r.lower() for r in reasons)

    def test_name_hint_xiaomi(self):
        adv = MockAdv(local_name="Xiaomi Band")
        dev = MockDev()
        reasons = is_xiaomi(dev, adv)
        assert len(reasons) >= 1

    def test_name_hint_watch(self):
        adv = MockAdv(local_name="Smart Watch")
        dev = MockDev()
        reasons = is_xiaomi(dev, adv)
        assert len(reasons) >= 1

    def test_name_hint_mi_space(self):
        adv = MockAdv(local_name="Mi Fitness")
        dev = MockDev()
        reasons = is_xiaomi(dev, adv)
        assert len(reasons) >= 1

    def test_xiaomi_uuid(self):
        adv = MockAdv(service_uuids=["0000fe95-0000-1000-8000-00805f9b34fb"])
        dev = MockDev()
        reasons = is_xiaomi(dev, adv)
        assert len(reasons) >= 1
        assert any("fe95" in r.lower() for r in reasons)

    def test_xiaomi_company_id(self):
        adv = MockAdv(manufacturer_data={0x038F: b"\x01\x02"})
        dev = MockDev()
        reasons = is_xiaomi(dev, adv)
        assert len(reasons) >= 1
        assert any("Xiaomi" in r for r in reasons)

    def test_anhui_huami_id(self):
        adv = MockAdv(manufacturer_data={0x0157: b"\x01"})
        dev = MockDev()
        reasons = is_xiaomi(dev, adv)
        assert len(reasons) >= 1
        assert "Huami" in reasons[0]

    def test_no_match(self):
        adv = MockAdv(
            local_name="Generic BLE Device", service_uuids=["00001234-0000-1000-8000-00805f9b34fb"]
        )
        dev = MockDev()
        reasons = is_xiaomi(dev, adv)
        assert reasons == []

    def test_multiple_reasons(self):
        adv = MockAdv(
            local_name="Redmi Watch",
            service_uuids=["0000fe95-0000-1000-8000-00805f9b34fb"],
            manufacturer_data={0x038F: b"\x01"},
        )
        dev = MockDev()
        reasons = is_xiaomi(dev, adv)
        assert len(reasons) >= 3  # name + uuid + company

    def test_service_data_uuid(self):
        adv = MockAdv(service_data={"0000fee0-0000-1000-8000-00805f9b34fb": b"\x01"})
        dev = MockDev()
        reasons = is_xiaomi(dev, adv)
        assert len(reasons) >= 1

    def test_empty_device(self):
        adv = MockAdv()
        dev = MockDev()
        reasons = is_xiaomi(dev, adv)
        assert reasons == []

    def test_none_local_name(self):
        adv = MockAdv(local_name=None)
        dev = MockDev(name="Redmi Watch")
        reasons = is_xiaomi(dev, adv)
        assert len(reasons) >= 1
