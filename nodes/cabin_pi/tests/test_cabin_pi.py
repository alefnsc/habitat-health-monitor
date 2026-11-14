import json

import pytest

from hub.contract import validate_reading
from nodes.cabin_pi import bme280, dht22, scd41
from nodes.cabin_pi.node import Cabin, Ring, Sample, format_reading, next_boot
from nodes.cabin_pi.tests import fakes

NO_SLEEP = lambda _s: None


# ---- BME280 -----------------------------------------------------------------------------


def calib() -> bme280.Calib:
    return bme280.parse_calibration(fakes.cal_block1(), fakes.CAL["H1"], fakes.cal_block2())


def test_calibration_round_trip():
    c = calib()
    for k, v in fakes.CAL.items():
        assert getattr(c, k) == v, k


def _t_double(adc_t, c):
    """Bosch BME280 datasheet rev 1.23, section 8.1: temperature in double precision."""
    v1 = (adc_t / 16384.0 - c.T1 / 1024.0) * c.T2
    v2 = ((adc_t / 131072.0 - c.T1 / 8192.0) ** 2) * c.T3
    return int(v1 + v2), (v1 + v2) / 5120.0


def _p_double(adc_p, t_fine, c):
    """Same document, section 8.1: pressure in Pa, double precision."""
    v1 = t_fine / 2.0 - 64000.0
    v2 = v1 * v1 * c.P6 / 32768.0
    v2 = v2 + v1 * c.P5 * 2.0
    v2 = v2 / 4.0 + c.P4 * 65536.0
    v1 = (c.P3 * v1 * v1 / 524288.0 + c.P2 * v1) / 524288.0
    v1 = (1.0 + v1 / 32768.0) * c.P1
    p = 1048576.0 - adc_p
    p = (p - v2 / 4096.0) * 6250.0 / v1
    v1 = c.P9 * p * p / 2147483648.0
    v2 = p * c.P8 / 32768.0
    return p + (v1 + v2 + c.P7) / 16.0


def test_temperature_matches_datasheet_double_formula():
    c = calib()
    t_fine_ref, t_ref = _t_double(fakes.ADC_T, c)
    t_fine, t = bme280.compensate_temperature(fakes.ADC_T, c)
    assert abs(t_fine - t_fine_ref) <= 1
    assert abs(t / 100.0 - t_ref) < 0.01
    assert abs(t / 100.0 - 25.08) < 0.01  # the value usually quoted for these inputs


def test_pressure_matches_datasheet_double_formula():
    c = calib()
    t_fine, _ = bme280.compensate_temperature(fakes.ADC_T, c)
    got = bme280.compensate_pressure(fakes.ADC_P, t_fine, c) / 256.0
    ref = _p_double(fakes.ADC_P, t_fine, c)
    assert abs(got - ref) < 1.0  # datasheet accuracy of the integer path is about 1 Pa
    assert abs(got - 100653.27) < 0.1  # the value usually quoted for these inputs


def test_humidity_matches_datasheet_double_formula():
    c = calib()
    t_fine, _ = bme280.compensate_temperature(fakes.ADC_T, c)
    v = t_fine - 76800.0
    v = (fakes.ADC_H - (c.H4 * 64.0 + c.H5 / 16384.0 * v)) * (
        c.H2 / 65536.0 * (1.0 + c.H6 / 67108864.0 * v * (1.0 + c.H3 / 67108864.0 * v))
    )
    v = v * (1.0 - c.H1 * v / 524288.0)
    expected = min(max(v, 0.0), 100.0)
    got = bme280.compensate_humidity(fakes.ADC_H, t_fine, c) / 1024.0
    assert abs(got - expected) < 0.1
    assert 0 < got < 100


def test_humidity_clamps():
    c = calib()
    t_fine, _ = bme280.compensate_temperature(fakes.ADC_T, c)
    assert bme280.compensate_humidity(0, t_fine, c) == 0
    assert bme280.compensate_humidity(65535, t_fine, c) <= 100 * 1024


def test_probe_finds_0x77_and_reads():
    bus = fakes.FakeBus(bme_addr=0x77)
    dev = bme280.Bme280.probe(bus, NO_SLEEP)
    assert dev.addr == 0x77
    r = dev.read()
    assert abs(r.temp_c - 25.08) < 0.01 and abs(r.pressure_hpa - 1006.5327) < 0.001
    assert (0x77, bytes([0xF4, 0x25])) in bus.writes


def test_probe_rejects_bmp280_chip_id():
    with pytest.raises(bme280.BmeError, match="0x58"):
        bme280.Bme280.probe(fakes.FakeBus(chip_id=0x58), NO_SLEEP)


def test_probe_no_device():
    with pytest.raises(bme280.BmeError, match="no BME280"):
        bme280.Bme280.probe(fakes.FakeBus(bme_addr=None), NO_SLEEP)


def test_skipped_measurement_is_an_error():
    with pytest.raises(bme280.BmeError):
        bme280.decode_raw(fakes.raw_data(adc_t=0x80000), calib())


# ---- SCD41 ------------------------------------------------------------------------------


def test_crc_sensirion_example():
    assert scd41.crc8(bytes([0xBE, 0xEF])) == 0x92  # Sensirion datasheet example


def test_measurement_frame_parse_and_bad_crc():
    frame = scd41.word_frame(500) + scd41.word_frame(0x6667) + scd41.word_frame(0x8000)
    assert scd41.parse_measurement(frame).co2_ppm == 500
    bad = bytes([frame[0] ^ 1]) + frame[1:]
    with pytest.raises(scd41.ScdError, match="CRC"):
        scd41.parse_measurement(bad)
    with pytest.raises(scd41.ScdError):
        scd41.parse_measurement(frame[:8])


def test_start_sequence_and_pressure_command():
    bus = fakes.FakeBus()
    dev = scd41.Scd41(bus, NO_SLEEP)
    dev.start()
    dev.set_ambient_pressure(1006.53)
    cmds = [d for a, d in bus.writes if a == 0x62]
    assert cmds[0] == bytes([0x3F, 0x86]) and cmds[1] == bytes([0x21, 0xB1])
    assert cmds[2] == bytes([0xE0, 0x00]) + scd41.word_frame(1007)  # hPa, rounded


def test_pressure_word_clamped():
    assert scd41.pressure_hpa_word(100.0) == 700
    assert scd41.pressure_hpa_word(5000.0) == 1200


def test_data_ready_and_read():
    bus = fakes.FakeBus()
    dev = scd41.Scd41(bus, NO_SLEEP)
    assert dev.data_ready() is False
    bus.scd_ready = True
    assert dev.data_ready() is True
    assert dev.read().co2_ppm == 612


# ---- DHT22 ------------------------------------------------------------------------------


def test_dht22_frame():
    f = bytes([0x02, 0x92, 0x01, 0x0D])  # 65.8 %RH, 26.9 degC
    assert dht22.decode_frame(f + bytes([sum(f) & 0xFF])) == (26.9, 65.8)
    n = bytes([0x01, 0x90, 0x80, 0x65])  # -10.1 degC
    assert dht22.decode_frame(n + bytes([sum(n) & 0xFF]))[0] == -10.1
    with pytest.raises(ValueError):
        dht22.decode_frame(f + b"\x00")


# ---- Formatting, boot counter -----------------------------------------------------------


def test_line_is_valid_contract_v1():
    s = Sample("cabin_temp", 24.2999, "BME280", (), 10.0)
    line = format_reading(s, 3, 7, 10.25)
    msg = json.loads(line)
    assert validate_reading(msg) == []
    assert msg["age_ms"] == 250 and msg["val"] == 24.3 and msg["q"] == ["ok"]
    assert msg["node"] == "cabin-1" and msg["src"] == "hobby" and len(line) <= 256
    assert " " not in line


def test_co2_is_integer_and_flags_ordered():
    s = Sample("cabin_co2", 5400.4, "SCD41", ("out_of_range", "settling"), 0.0)
    msg = json.loads(format_reading(s, 1, 1, 0.0))
    assert msg["val"] == 5400 and isinstance(msg["val"], int)
    assert msg["q"] == ["settling", "out_of_range"]
    assert validate_reading(msg) == []


def test_boot_counter_persists(tmp_path):
    assert [next_boot(tmp_path) for _ in range(3)] == [1, 2, 3]
    (tmp_path / "cabin-1.boot").write_text("garbage")
    assert next_boot(tmp_path) == 1


def test_ring_drops_oldest():
    r = Ring()
    for i in range(40):
        r.push(Sample("cabin_p", float(i), "BME280", (), 0.0))
    assert len(r.q) == 32 and r.dropped == 8 and r.q[0].val == 8.0


# ---- Scheduling and flags ---------------------------------------------------------------


def make(bus=None, **kw):
    bus = bus or fakes.FakeBus()
    logs: list[str] = []
    cab = Cabin(
        bme280.Bme280.probe(bus, NO_SLEEP), scd41.Scd41(bus, NO_SLEEP), log=logs.append, **kw
    )
    return bus, cab, logs


def run(cab, seconds, start=0.0):
    out = []
    for t in range(seconds):
        out += cab.step(start + t)
    return out


def test_cycle_every_5_s_with_expected_indicators_and_contract():
    bus, cab, _ = make()
    bus.scd_ready = True
    cab.start(0.0)
    out = run(cab, 61)
    inds = [s.ind for s in out]
    assert inds.count("cabin_temp") == 13 and inds.count("cabin_co2") == 13  # t = 0, 5, ..., 60
    for i, s in enumerate(out):
        assert validate_reading(json.loads(format_reading(s, 1, i + 1, 61.0))) == []


def test_scd_settling_for_first_60_s_then_ok():
    bus, cab, _ = make()
    bus.scd_ready = True
    cab.start(0.0)
    co2 = [(s.t, s.q) for s in run(cab, 70) if s.ind == "cabin_co2"]
    assert all(q == ("settling",) for t, q in co2 if t < 60)
    assert all(q == () for t, q in co2 if t >= 60)


def test_scd_retries_until_data_ready_within_cycle():
    bus, cab, _ = make()
    cab.start(0.0)
    assert [s for s in run(cab, 3) if s.ind == "cabin_co2"] == []
    bus.scd_ready = True
    assert [s.t for s in cab.step(3.0) if s.ind == "cabin_co2"] == [3.0]
    assert [s for s in cab.step(4.0) if s.ind == "cabin_co2"] == []  # one per cycle


def test_pressure_sent_at_boot_and_every_60_s():
    bus, cab, _logs = make()
    bus.scd_ready = True
    cab.start(0.0)
    run(cab, 125)
    sent = [d for a, d in bus.writes if a == 0x62 and d[:2] == bytes([0xE0, 0x00])]
    assert len(sent) == 3  # t = 0, 60, 120


def test_pressure_uses_bme_value():
    bus, cab, logs = make()
    cab.start(0.0)
    cab.step(0.0)  # BME read happens before the pressure write in the same step
    assert "# scd41 ambient_pressure_pa=100653" in logs
    sent = [d for a, d in bus.writes if a == 0x62 and d[:2] == bytes([0xE0, 0x00])]
    assert sent[0][2:] == scd41.word_frame(1007)


def test_no_bme_publishes_co2_with_default_pressure():
    bus = fakes.FakeBus(bme_addr=None)
    logs: list[str] = []
    cab = Cabin(None, scd41.Scd41(bus, NO_SLEEP), log=logs.append)
    bus.scd_ready = True
    cab.start(0.0)
    out = run(cab, 6)
    assert {s.ind for s in out} == {"cabin_co2"}
    assert "# scd41 using default pressure 101300 Pa" in logs


def test_first_bme_reading_is_settling_then_ok():
    _bus, cab, _ = make()
    cab.start(0.0)
    first = [s for s in cab.step(0.0) if s.dev == "BME280"]
    second = [s for s in cab.step(5.0) if s.dev == "BME280"]
    assert all(s.q == ("settling",) for s in first) and all(s.q == () for s in second)


def test_scd_out_of_range_above_5000():
    bus, cab, _ = make()
    bus.scd_ready, bus.scd_co2 = True, 5200
    cab.start(0.0)
    s = [s for s in run(cab, 6) if s.ind == "cabin_co2"][-1]
    assert "out_of_range" in s.q


def test_bme_out_of_range_pressure():
    bus, cab, _ = make()
    bus.data = fakes.raw_data(adc_p=1)  # decodes to a pressure far from sea level
    cab.start(0.0)
    p = next(s for s in cab.step(0.0) if s.ind == "cabin_p")
    assert "out_of_range" in p.q


def test_no_contact_after_three_failures_only_if_sensor_worked_before():
    bus, cab, _ = make()
    bus.scd_ready = True
    cab.start(0.0)
    cab.step(0.0)
    bus.fail = True
    seen = []
    for t in (5.0, 10.0, 15.0):
        seen.append([s for s in cab.step(t) if s.dev == "BME280"])
    assert seen[0] == [] and seen[1] == []
    assert [(s.ind, s.val, s.q) for s in seen[2]] == [
        ("cabin_temp", 0.0, ("no_contact",)),
        ("cabin_rh", 0.0, ("no_contact",)),
        ("cabin_p", 0.0, ("no_contact",)),
    ]
    bus.fail = False
    assert next(s for s in cab.step(20.0) if s.dev == "BME280").q == ()  # recovered


def test_scd_crc_error_is_counted_not_published():
    bus, cab, logs = make()
    bus.scd_ready, bus.scd_corrupt = True, True
    cab.start(0.0)
    assert [s for s in run(cab, 6) if s.ind == "cabin_co2"] == []
    assert any("CRC" in m for m in logs)


def test_dht22_adds_second_source_lines():
    _bus, cab, _ = make(dht=lambda: (26.9, 65.8))
    cab.start(0.0)
    devs = [(s.ind, s.dev) for s in cab.step(0.0)]
    assert ("cabin_temp", "DHT22") in devs and ("cabin_rh", "DHT22") in devs


def test_dht22_failed_read_publishes_nothing():
    _bus, cab, _ = make(dht=lambda: None)
    cab.start(0.0)
    assert all(s.dev != "DHT22" for s in cab.step(0.0))
