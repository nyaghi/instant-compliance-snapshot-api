"""Deterministic cgroup fixtures; no cloud, browser or application requests."""
import tempfile
import unittest
from pathlib import Path
from deployment.queue_worker import ResourceAdmission, AdmissionWindow


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

    def test_sub_sample_poll_cannot_turn_short_spike_into_pressure(self):
        self.gate.limit(12,0);self.now=1;self.metrics(500000)
        self.assertEqual(self.gate.limit(12,8),12)
        self.now=1.1;self.metrics(700000)
        self.assertEqual(self.gate.limit(12,8),12)
        self.assertEqual(self.gate.snapshot['cpu_fraction'],.25)

    def test_sub_sample_poll_cannot_turn_short_quiet_period_into_headroom(self):
        self.gate.limit(12,0);self.now=1;self.metrics(1900000)
        self.assertEqual(self.gate.limit(12,8),8)
        self.now=1.1;self.metrics(1900000)
        self.assertEqual(self.gate.limit(12,8),8)

    def test_sustained_pressure_still_blocks_and_then_clears(self):
        self.gate.limit(12,0)
        for tick in range(1,13):
            self.now=tick*.25;self.metrics(tick*500000)
            self.assertEqual(self.gate.limit(12,7),7)
            self.assertLessEqual(self.gate.snapshot['cpu_window_seconds'],2)
        self.now=5;self.metrics(6000000)
        self.assertEqual(self.gate.limit(12,7),12)

    def test_long_observation_gap_requires_fresh_headroom(self):
        self.gate.limit(12,0);self.now=1;self.metrics(500000)
        self.assertEqual(self.gate.limit(12,8),12)
        self.now=5;self.metrics(600000)
        self.assertEqual(self.gate.limit(12,8),8)
        self.assertEqual(self.gate.snapshot['reason'],'cpu_warmup')

    def test_memory_is_checked_even_between_cpu_samples(self):
        self.gate.limit(12,0);self.now=1;self.metrics(500000)
        self.gate.limit(12,8)
        self.now=1.1;self.metrics(600000,memory=3_400_000_000)
        self.assertEqual(self.gate.limit(12,8),8)
        self.assertEqual(self.gate.snapshot['reason'],'memory_headroom')

    def test_missing_metrics_cannot_reuse_previous_headroom(self):
        self.gate.limit(12,0);self.now=1;self.metrics(500000)
        self.gate.limit(12,8)
        (self.root/'cpu.stat').unlink();self.gate.limit(12,8)
        self.now=1.1;self.metrics(600000)
        self.assertEqual(self.gate.limit(12,8),8)


class ObservationTests(unittest.TestCase):
    def test_seconds_are_partitioned_without_changing_admission(self):
        window=AdmissionWindow(0)
        window.observe('cpu_pressure',1,True)
        window.observe('claim_transaction',3,True)
        window.observe('no_eligible_job',4,True)
        data=window.snapshot(5)
        self.assertEqual(data['seconds_by_reason'],{'starting':1,'cpu_pressure':2,'claim_transaction':1,'no_eligible_job':1})
        self.assertEqual(sum(data['seconds_by_reason'].values()),data['window_seconds'])
        self.assertTrue(window.had_work)

    def test_reset_does_not_duplicate_previous_intervals(self):
        window=AdmissionWindow(0);window.observe('launch_pacing',1,True)
        self.assertEqual(window.snapshot(3)['window_seconds'],3)
        window.reset(3)
        self.assertFalse(window.had_work)
        self.assertEqual(window.snapshot(5)['seconds_by_reason'],{'launch_pacing':2})

    def test_failed_persistence_can_retake_snapshot_without_losing_data(self):
        window=AdmissionWindow(0);window.observe('memory_headroom',1,True)
        window.snapshot(3)
        self.assertEqual(window.snapshot(5)['seconds_by_reason']['memory_headroom'],4)


if __name__=='__main__':unittest.main(verbosity=2)
