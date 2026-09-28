"""Unit tests for resource boundary validation and containment flags."""

import os
import unittest
from productify_node.boundary import BoundaryEnforcer


class TestBoundaryEnforcer(unittest.TestCase):

    def setUp(self):
        self.enforcer = BoundaryEnforcer()

    def test_clamp_allocation_limits(self):
        # Requesting 1000 GB RAM on a regular PC should clamp to max_allowable_ram_gb
        res = self.enforcer.validate_and_clamp_allocation(ram_gb=1000.0, disk_gb=50000.0, cpus=128)
        self.assertLessEqual(res["ram_limit_gb"], self.enforcer.max_allowable_ram_gb)
        self.assertLessEqual(res["disk_limit_gb"], self.enforcer.max_allowable_disk_gb)
        self.assertLessEqual(res["cpu_limit_cores"], self.enforcer.max_allowable_cpus)

    def test_minimum_allocations(self):
        # Requesting 0 or negative should clamp to minimum safety threshold
        res = self.enforcer.validate_and_clamp_allocation(ram_gb=-5.0, disk_gb=0.1, cpus=0)
        self.assertGreaterEqual(res["ram_limit_gb"], 0.5)
        self.assertGreaterEqual(res["disk_limit_gb"], 2.0)
        self.assertGreaterEqual(res["cpu_limit_cores"], 1)

    def test_docker_boundary_flags(self):
        flags = self.enforcer.get_docker_boundary_flags()
        self.assertTrue(any(f.startswith("--memory=") for f in flags))
        self.assertTrue(any(f.startswith("--memory-swap=") for f in flags))
        self.assertTrue(any(f.startswith("--cpus=") for f in flags))


if __name__ == "__main__":
    unittest.main()
