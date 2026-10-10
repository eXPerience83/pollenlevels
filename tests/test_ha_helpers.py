"""Characterize test-side ownership snapshots for supported registry models."""

from types import SimpleNamespace

import pytest
from homeassistant.helpers.device_registry import DeviceEntry

from tests.ha_helpers import device_ownership


@pytest.mark.parametrize(
    ("owners", "associations"),
    [
        ({"parent"}, {"parent": {"location"}}),
        ({"parent"}, {"parent": {None}}),
        (
            {"parent", "other"},
            {"parent": {"location", "extra", None}, "other": {"other-location"}},
        ),
    ],
)
def test_device_ownership_preserves_legacy_associations(owners, associations):
    """The HA 2026.5 representation retains all owners and subentries."""
    device = SimpleNamespace(
        config_entries=owners, config_entries_subentries=associations
    )
    snapshot = device_ownership(device)
    assert snapshot == (owners, associations)
    owners.add("later")
    associations["parent"].add("later-location")
    assert "later" not in snapshot[0]
    assert "later-location" not in snapshot[1]["parent"]


@pytest.mark.parametrize("subentry_id", ["location", None])
def test_device_ownership_never_reads_new_model_legacy_properties(subentry_id):
    """Single-owner fields include parent-only ownership without legacy reads."""

    class SingleOwnerDevice:
        """Expose the public HA 2026.8+ ordinary-device ownership contract."""

        config_entry_id = "parent"
        config_subentry_id = subentry_id

        @property
        def config_entries(self):
            raise AssertionError("Deprecated config_entries was read")

        @property
        def config_entries_subentries(self):
            raise AssertionError("Deprecated config_entries_subentries was read")

    assert device_ownership(SingleOwnerDevice()) == (
        {"parent"},
        {"parent": {subentry_id}},
    )


def test_device_ownership_with_installed_device_entry(monkeypatch):
    """Exercise the actual registry class in every compatibility environment."""
    if hasattr(DeviceEntry, "config_entry_id"):
        device = DeviceEntry(config_entry_id="parent", config_subentry_id="location")

        def deprecated_read(_device):
            raise AssertionError("An actual DeviceEntry legacy property was read")

        for name in ("config_entries", "config_entries_subentries"):
            monkeypatch.setattr(DeviceEntry, name, property(deprecated_read))
    else:
        device = DeviceEntry(
            config_entries={"parent"},
            config_entries_subentries={"parent": {"location"}},
        )
    assert device_ownership(device) == ({"parent"}, {"parent": {"location"}})
