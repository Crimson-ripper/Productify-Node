"""Resource boundary allocation and strict containment enforcer."""

import os
import shutil
import logging
from productify_node.config import config
from productify_node.telemetry import probe_ram, probe_disk, probe_cpu

logger = logging.getLogger("productify_node.boundary")


class BoundaryEnforcer:
    """Enforces host-determined RAM, Disk, and CPU allocation boundaries."""

    def __init__(self):
        self.refresh_hardware_limits()

    def refresh_hardware_limits(self):
        ram = probe_ram()
        disk = probe_disk()
        cpu = probe_cpu()

        self.physical_ram_total = ram["total_gb"]
        self.physical_disk_free = disk["free_gb"]
        self.physical_cpu_cores = cpu["cores"]

        # Ensure safety buffer for host operating system
        self.max_allowable_ram_gb = max(0.5, round(self.physical_ram_total - 1.5, 1))
        self.max_allowable_disk_gb = max(2.0, round(self.physical_disk_free - 5.0, 1))
        self.max_allowable_cpus = max(1, self.physical_cpu_cores - 1)

    def validate_and_clamp_allocation(self, ram_gb=None, disk_gb=None, cpus=None):
        """Clamp proposed allocation to safe hardware bounds."""
        self.refresh_hardware_limits()

        current_ram = ram_gb if ram_gb is not None else config.ram_limit_gb
        current_disk = disk_gb if disk_gb is not None else config.disk_limit_gb
        current_cpus = cpus if cpus is not None else config.cpu_limit_cores

        clamped_ram = max(0.5, min(float(current_ram), self.max_allowable_ram_gb))
        clamped_disk = max(2.0, min(float(current_disk), self.max_allowable_disk_gb))
        clamped_cpus = max(1, min(int(current_cpus), self.max_allowable_cpus))

        return {
            "ram_limit_gb": round(clamped_ram, 1),
            "disk_limit_gb": round(clamped_disk, 1),
            "cpu_limit_cores": clamped_cpus,
        }

    def set_allocations(self, ram_gb, disk_gb, cpus=None):
        """Save new host resource allocation limits."""
        clamped = self.validate_and_clamp_allocation(ram_gb, disk_gb, cpus)
        config.set("ram_limit_gb", clamped["ram_limit_gb"], auto_save=False)
        config.set("disk_limit_gb", clamped["disk_limit_gb"], auto_save=False)
        config.set("cpu_limit_cores", clamped["cpu_limit_cores"], auto_save=True)
        logger.info(f"Allocation boundaries updated: {clamped}")
        return clamped

    def get_docker_boundary_flags(self):
        """Generate command-line flags to strictly enforce limits in Docker."""
        clamped = self.validate_and_clamp_allocation()
        ram_gb = clamped["ram_limit_gb"]
        cpus = clamped["cpu_limit_cores"]

        # Hard memory constraint + zero swap expansion + CPU throttling
        return [
            f"--memory={ram_gb}g",
            f"--memory-swap={ram_gb}g",
            f"--cpus={cpus}",
            f"--shm-size=1g" if ram_gb <= 2.0 else "--shm-size=2g",
        ]

    def check_pod_disk_usage(self, pod_workspace_dir):
        """Calculate active pod scratch directory size and verify against disk limit."""
        if not os.path.exists(pod_workspace_dir):
            return {"used_gb": 0.0, "limit_gb": config.disk_limit_gb, "violation": False}

        total_bytes = 0
        try:
            for root, dirs, files in os.walk(pod_workspace_dir):
                for f in files:
                    fp = os.path.join(root, f)
                    if not os.path.islink(fp):
                        total_bytes += os.path.getsize(fp)
        except Exception as e:
            logger.warning(f"Error calculating pod disk size: {e}")

        used_gb = round(total_bytes / (1024 ** 3), 3)
        limit_gb = config.disk_limit_gb
        violation = used_gb > limit_gb

        return {
            "used_gb": used_gb,
            "limit_gb": limit_gb,
            "violation": violation,
        }


enforcer = BoundaryEnforcer()
