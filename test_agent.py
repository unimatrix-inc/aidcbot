import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import aidcbot_agent as agent


class AgentTests(unittest.TestCase):
    def test_cpu_delta(self):
        self.assertEqual(agent.cpu_percent((100, 40), (200, 60)), 80.0)
        self.assertIsNone(agent.cpu_percent((100, 40), (100, 40)))

    def test_linux_memory(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "meminfo"
            path.write_text("MemTotal: 1000 kB\nMemAvailable: 250 kB\n")
            self.assertEqual(agent.memory_stats(path)["utilizationPercent"], 75.0)

    def test_linux_cpu_spec(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cpuinfo"
            path.write_text("processor : 0\nmodel name : AMD EPYC 9R14\nphysical id : 0\ncore id : 0\n\nprocessor : 1\nmodel name : AMD EPYC 9R14\nphysical id : 0\ncore id : 1\n")
            spec = agent.cpu_spec(path)
            self.assertEqual(spec["modelName"], "AMD EPYC 9R14")
            self.assertEqual(spec["logicalCores"], 2)
            self.assertEqual(spec["physicalCores"], 2)

    def test_disk_includes_device_and_filesystem(self):
        with tempfile.TemporaryDirectory() as directory:
            mounts = Path(directory) / "mounts"
            mounts.write_text("/dev/nvme0n1p1 / ext4 rw 0 0\n")
            disk = agent.disk_stats(directory, mounts)
            self.assertIsNone(disk["device"])
            root = agent.disk_stats("/", mounts)
            self.assertEqual(root["device"], "/dev/nvme0n1p1")
            self.assertEqual(root["fileSystem"], "ext4")

    def test_nvidia_gpu_parser(self):
        output = "0, GPU-abc, NVIDIA H100, 570.86.15, 00000000:31:00.0, 75, 1024, 81920, 55, 280.5\n"
        with patch.object(agent.subprocess, "run", return_value=type("Result", (), {"stdout": output})()):
            gpu = agent.gpu_stats()[0]
        self.assertEqual(gpu["memoryUsedBytes"], 1024 * agent.MIB)
        self.assertEqual(gpu["utilizationPercent"], 75)
        self.assertEqual(gpu["powerW"], 280.5)
        self.assertEqual(gpu["driverVersion"], "570.86.15")
        self.assertEqual(gpu["pciBusId"], "00000000:31:00.0")

    def test_missing_nvidia_smi_reports_no_gpus(self):
        with patch.object(agent.subprocess, "run", side_effect=FileNotFoundError):
            self.assertEqual(agent.gpu_stats(), [])


if __name__ == "__main__":
    unittest.main()
