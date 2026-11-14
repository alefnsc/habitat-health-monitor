"""Optional DHT22 on a GPIO pin. Frame decoding is pure; the GPIO read uses adafruit_dht if present.

DHT22 is read no faster than every 2 s. The Python timing on a Pi is loose, so failed reads are
normal: the caller treats None as "no reading this time".
"""

from __future__ import annotations

from collections.abc import Callable


def decode_frame(b: bytes) -> tuple[float, float]:
    """5 bytes: RH hi/lo (0.1 %), T hi/lo (0.1 degC, bit 15 = sign), checksum. Raises ValueError."""
    if len(b) != 5:
        raise ValueError("DHT22 frame must be 5 bytes")
    if (b[0] + b[1] + b[2] + b[3]) & 0xFF != b[4]:
        raise ValueError("DHT22 checksum mismatch")
    rh = ((b[0] << 8) | b[1]) / 10.0
    raw_t = ((b[2] & 0x7F) << 8) | b[3]
    t = raw_t / 10.0
    if b[2] & 0x80:
        t = -t
    return t, rh


def gpio_reader(bcm_pin: int) -> Callable[[], tuple[float, float] | None] | None:
    """Reader for a DHT22 on BCM pin, or None when the library is not installed."""
    try:
        import adafruit_dht  # type: ignore[import-not-found]
        import board  # type: ignore[import-not-found]
    except ImportError:
        return None
    dev = adafruit_dht.DHT22(getattr(board, f"D{bcm_pin}"))

    def read() -> tuple[float, float] | None:
        try:
            return float(dev.temperature), float(dev.humidity)
        except (RuntimeError, TypeError):  # checksum or timing error, try again next cycle
            return None

    return read
