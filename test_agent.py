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

    def test_nvidia_gpu_parser(self):
        output = "0, GPU-abc, NVIDIA H100, 75, 1024, 81920, 55, 280.5\n"
        with patch.object(agent.subprocess, "run", return_value=type("Result", (), {"stdout": output})()):
            gpu = agent.gpu_stats()[0]
        self.assertEqual(gpu["memoryUsedBytes"], 1024 * agent.MIB)
        self.assertEqual(gpu["utilizationPercent"], 75)
        self.assertEqual(gpu["powerW"], 280.5)

    def test_missing_nvidia_smi_reports_no_gpus(self):
        with patch.object(agent.subprocess, "run", side_effect=FileNotFoundError):
            self.assertEqual(agent.gpu_stats(), [])


if __name__ == "__main__":
    unittest.main()
