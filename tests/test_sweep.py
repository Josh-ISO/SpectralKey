"""Deterministic sweep coverage, settling, power averaging, and packet checks."""
import math
import struct
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'backend'))
from sweep import Sweep


def packet(index, level=-100, zoom=3):
    start = index * (1024 * 2**14 // 8)
    return b'W/F ' + struct.pack('<III', start, zoom, 1) + bytes([level + 255]) * 1024


class SweepTests(unittest.TestCase):
    def test_coverage_and_linear_average(self):
        sweep = Sweep(30000000, 1000000)
        for pass_number in (1, 2):
            for index in range(8):
                self.assertEqual(sweep.center_khz, (1000000 + (index + .5) * 3750000) / 1000)
                self.assertEqual(sweep.accept(packet(index, -10)), (False, None))
                self.assertEqual(sweep.accept(packet(index, -100)), (False, None))
                advanced, result = sweep.accept(packet(index, -90))
                self.assertTrue(advanced)
                if index != 7:
                    self.assertIsNone(result, 'Partial passes must not be displayed')
                else:
                    self.assertEqual(result['completed'], pass_number)
                    self.assertEqual(len(result['bins']), 2048)
                    self.assertEqual(result['lowHz'], 1000000)
                    self.assertEqual(result['highHz'], 31000000)
                    self.assertEqual(result['binWidthHz'] * len(result['bins']), 30000000)
                    self.assertTrue(all(abs(x - 10 * math.log10((1e-10 + 1e-9) / 2)) < .01 for x in result['bins']))

    def test_reject_wrong_position_and_malformed_packets(self):
        sweep = Sweep(30000000)
        for data in (b'bad', packet(0, zoom=5), packet(1)):
            self.assertEqual(sweep.accept(data), (False, None))
            self.assertFalse(sweep.settled)
        for _ in range(3): sweep.accept(packet(0))
        self.assertEqual(sweep.index, 1)
        sweep.accept(packet(0))
        self.assertFalse(sweep.settled)
        self.assertEqual(sweep.samples, 0)

    def test_invalid_receiver_range(self):
        for bandwidth in (0, -1, float('nan'), float('inf'), 64000001):
            with self.assertRaises(ValueError): Sweep(bandwidth)
        with self.assertRaises(ValueError): Sweep(30000000, float('nan'))


if __name__ == '__main__': unittest.main()
