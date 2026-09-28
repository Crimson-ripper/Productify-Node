"""Unit tests for hardware auto-probe and telemetry."""

import unittest
from productify_node.telemetry import probe_ram, probe_disk, probe_cpu, probe_gpu, get_full_telemetry


class TestTelemetry(unittest.TestCase):

    def test_probe_ram(self):
        ram = probe_ram()
        self.assertIn("total_gb", ram)
        self.assertIn("free_gb", ram)
        self.assertGreater(ram["total_gb"], 0)

    def test_probe_disk(self):
        disk = probe_disk()
        self.assertIn("total_gb", disk)
        self.assertIn("free_gb", disk)
        self.assertGreater(disk["total_gb"], 0)

    def test_probe_cpu(self):
        cpu = probe_cpu()
        self.assertIn("name", cpu)
        self.assertIn("cores", cpu)
        self.assertGreater(cpu["cores"], 0)

    def test_probe_gpu(self):
        gpu = probe_gpu()
        self.assertIn("available", gpu)
        self.assertIn("name", gpu)
        self.assertIn("vram_total_mb", gpu)

    def test_full_telemetry(self):
        t = get_full_telemetry()
        self.assertIn("ram", t)
        self.assertIn("disk", t)
        self.assertIn("cpu", t)
        self.assertIn("gpu", t)
        self.assertIn("max_safe_ram_gb", t)
        self.assertIn("max_safe_disk_gb", t)


if __name__ == "__main__":
    unittest.main()
