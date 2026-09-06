from processor.settings import load_settings


def test_load_settings_scalars():
    s = load_settings()
    assert s.cycle_seconds == 5
    assert s.drift_window == 30
    assert s.gap_seconds == 20
    assert s.spike_window == 20


def test_load_settings_thresholds():
    s = load_settings()
    temp = s.thresholds["temperature_c"]
    assert temp.valid_range == (-10.0, 60.0)
    assert temp.baseline == 22.0
    assert temp.spike_sigma == 4.0
    assert temp.drift_delta == 3.0
    assert "vibration_mm_s" in s.thresholds
