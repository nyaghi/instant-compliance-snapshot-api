"""Deterministic cgroup fixtures; no cloud, browser or application requests."""
import tempfile
import unittest
from pathlib import Path
from deployment.queue_worker import ResourceAdmission


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.now=0
        self.gate=ResourceAdmission(self.root,lambda:self.now)
        self.metrics(0)

    def metrics(self,cpu,memory=1_000_000_000,maximum=4*1024**3):
        for file,text in {'cpu.max':'200000 100000','cpu.stat':f'usage_usec {cpu}',
                          'memory.current':str(memory),'memory.max':str(maximum)}.items():
            (self.root/file).write_text(text)

    def test_extra_slots_require_measured_headroom(self):
        self.assertEqual(self.gate.limit(12,0),8)
        self.now=1;self.metrics(500000)
        self.assertEqual(self.gate.limit(12,8),12)

    def test_cpu_pressure_pauses_new_work_without_releasing_active_work(self):
        self.gate.limit(12,0);self.now=1;self.metrics(1900000)
        self.assertEqual(self.gate.limit(12,7),7)
        self.assertEqual(self.gate.snapshot['reason'],'cpu_pressure')
        self.now=2;self.metrics(2200000)
        self.assertEqual(self.gate.limit(12,7),12)

    def test_memory_headroom_includes_next_process_and_browser(self):
        self.gate.limit(12,0);self.now=1;self.metrics(200000,memory=3_400_000_000)
        self.assertEqual(self.gate.limit(12,9),9)
        self.assertEqual(self.gate.snapshot['reason'],'memory_headroom')

    def test_launches_are_paced_even_with_low_cpu(self):
        self.gate.launched();self.now=.1
        self.assertEqual(self.gate.limit(12,1),1)
        self.assertEqual(self.gate.snapshot['reason'],'launch_pacing')

    def test_missing_cgroup_cannot_expand_beyond_original_capacity(self):
        (self.root/'cpu.stat').unlink()
        self.assertEqual(self.gate.limit(12,8),8)
        self.assertEqual(self.gate.snapshot['reason'],'metrics_unavailable')

    def test_unbounded_or_malformed_allocations_are_not_extra_capacity(self):
        for value in ('max 100000','0 100000','garbled'):
            (self.root/'cpu.max').write_text(value)
            self.assertEqual(self.gate.limit(12,0),8)

    def test_never_exceeds_configured_capacity(self):
        self.gate.limit(8,0);self.now=1;self.metrics(100000)
        self.assertEqual(self.gate.limit(8,0),8)

    def test_regressed_cpu_counter_does_not_prove_headroom(self):
        self.metrics(1000000);self.gate.limit(12,0);self.now=1;self.metrics(500000)
        self.assertEqual(self.gate.limit(12,0),8)


if __name__=='__main__':unittest.main(verbosity=2)
