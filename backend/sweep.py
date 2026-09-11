"""Independent stepped spectrum assembly for KiwiSDR spectrum packets.

No HackRF source is used. Power levels are receiver-relative, not calibrated dBm.
Each pass measures eight adjacent windows and averages two settled frames per
window in linear power. A completed pass has a fixed frequency axis.
"""
import math
import struct
from datetime import datetime, timezone


class Sweep:
    zoom = 3
    windows = 1 << zoom
    samples_per_window = 2
    output_bins_per_window = 256

    def __init__(self, bandwidth, offset=0):
        if not math.isfinite(bandwidth) or not 0 < bandwidth <= 64000000:
            raise ValueError('Invalid receiver bandwidth')
        if not math.isfinite(offset):
            raise ValueError('Invalid frequency offset')
        self.bandwidth, self.offset = bandwidth, offset
        self.span = bandwidth / self.windows
        self.index = self.passes = 0
        self.bins = []
        self._reset_window()

    @property
    def center_khz(self):
        return (self.offset + (self.index + .5) * self.span) / 1000

    def _reset_window(self):
        self.settled = False
        self.samples = 0
        self.power = [0.0] * self.output_bins_per_window

    def progress(self):
        return dict(type='sweep-progress', window=self.index + 1,
                    windows=self.windows, completed=self.passes,
                    frequency=self.center_khz, lowHz=self.offset,
                    highHz=self.offset + self.bandwidth)

    def accept(self, packet):
        """Return (window_completed, completed_pass_or_None).

        Reject queued packets for a previous tuning position. Then discard the
        first matching frame to allow settling. Partial passes are never emitted.
        """
        if len(packet) != 1040 or packet[:3] != b'W/F':
            return False, None
        start, zoom = struct.unpack_from('<II', packet, 4)
        if zoom & 0xffff != self.zoom:
            return False, None
        left = start * self.bandwidth / (1024 * 2**14)
        if abs(left - self.index * self.span) > self.span / 1024 * 2:
            return False, None
        if not self.settled:
            self.settled = True
            return False, None
        values = packet[16:]
        # Four native bins per output bin; average in power, not decibels.
        for index, value in enumerate(values):
            self.power[index // 4] += 10 ** ((value - 255) / 10)
        self.samples += 1
        if self.samples < self.samples_per_window:
            return False, None
        self.bins.extend(round(10 * math.log10(power / (4 * self.samples)), 2)
                         for power in self.power)
        self.index += 1
        result = None
        if self.index == self.windows:
            self.passes += 1
            result = dict(type='sweep', completed=self.passes,
                          timestamp=datetime.now(timezone.utc).isoformat(),
                          lowHz=self.offset, highHz=self.offset + self.bandwidth,
                          binWidthHz=self.bandwidth / len(self.bins), bins=self.bins)
            self.bins = []
            self.index = 0
        self._reset_window()
        return True, result
