"""Serial transport for the ML3 mbed drivetrain firmware.

Owns the port and raw byte I/O only; the wire format itself lives in ``protocol``
so it can be unit-tested without a serial device. SerialLink is exercised by
``colcon test`` inside the ROS2 build, not the standalone pytest job.
"""

import serial

from kuas_mechlab3.drive.protocol import format_led, format_servo_us, format_setpoints


class SerialLink:
    """Owns the /dev/ttyACM* port; delegates the packet format to ``protocol``."""

    def __init__(self, port: str, baud: int = 115200, timeout: float = 0.1) -> None:
        """Store connection settings; call open() before use."""
        self._port = port
        self._baud = baud
        self._timeout = timeout
        self._ser: serial.Serial | None = None

    def open(self) -> None:
        """Open the serial port (raises serial.SerialException on failure)."""
        self._ser = serial.Serial(self._port, self._baud, timeout=self._timeout)

    def close(self) -> None:
        """Release the port if it is open."""
        if self._ser is not None:
            self._ser.close()
            self._ser = None

    @property
    def is_open(self) -> bool:
        """Return True while the underlying port is open."""
        return self._ser is not None and bool(self._ser.is_open)

    def send_setpoints(self, s1: float, s2: float, s3: float, s4: float) -> None:
        """Write one setpoint packet to the firmware."""
        if self._ser is None:
            raise RuntimeError("serial port is not open")
        self._ser.write(format_setpoints(s1, s2, s3, s4).encode())

    def send_servo_us(self, us1: int, us2: int) -> None:
        """Write one servo packet (two pulse widths in µs) to the firmware.

        Independent of the setpoint packet (distinct 'a' terminator in
        ``protocol``), so the 4-wheel drive path is unaffected.
        """
        if self._ser is None:
            raise RuntimeError("serial port is not open")
        self._ser.write(format_servo_us(us1, us2).encode())

    def send_led(self, on: bool) -> None:
        """Write one LED packet (on/off) to the firmware.

        Independent of the setpoint and servo packets (distinct 'l'
        terminator), so neither the drive nor the servo path is affected.
        """
        if self._ser is None:
            raise RuntimeError("serial port is not open")
        self._ser.write(format_led(on).encode())

    def read_pending(self) -> list[str]:
        """Return all telemetry lines currently buffered, without blocking long.

        Drains only the bytes already waiting; at the firmware's ~1 kHz output a
        trailing partial line completes within the read timeout, so this never
        stalls the caller waiting for data that has not been sent yet.
        """
        lines: list[str] = []
        while self._ser is not None and self._ser.in_waiting:
            line = self._ser.readline().decode("utf-8", errors="replace").strip()
            if line:
                lines.append(line)
        return lines
