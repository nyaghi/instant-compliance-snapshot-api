"""Held-out distinct EIN/detail controls through the real shared repair queue."""
import sys,unittest
from run_ny_queue_browser import QueueIntegration
class IdentityQueue(QueueIntegration):
    def test_15_distinct_organizations_retain_identity_after_shared_repair(self):
        self.run_bursts([15],repair=True,distinct=True)
if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite([IdentityQueue('test_15_distinct_organizations_retain_identity_after_shared_repair')]))
    sys.exit(not result.wasSuccessful())
