from common.messages import Reading


def test_reading_roundtrip():
    r = Reading(
        device_external_id="temp-01",
        device_kind="temp-probe",
        metric="temperature_c",
        value=22.5,
        unit="C",
        sampled_at="2026-01-01T00:00:00+00:00",
        location="rack-a",
        firmware="1.4.2",
    )
    assert Reading.from_bytes(r.to_bytes()) == r


def test_reading_optional_fields_default_none():
    r = Reading("d1", "k", "m", 1.0, "u", "2026-01-01T00:00:00+00:00")
    assert r.location is None and r.firmware is None
    assert Reading.from_bytes(r.to_bytes()) == r
