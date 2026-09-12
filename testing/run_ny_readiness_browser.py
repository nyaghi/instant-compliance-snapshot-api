"""Actual extension transport with delayed readiness replies in a test-only copy."""
import json,shutil,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from run_ny_connector_browser import BrowserIntegration,WORK,c,ROW

class Readiness(BrowserIntegration):
    @classmethod
    def setUpClass(cls):
        cls.copy=tempfile.TemporaryDirectory(prefix='cc-readiness-fixture-')
        cls.extension_path=Path(cls.copy.name)/'extension'
        shutil.copytree(WORK/'browser-connector',cls.extension_path)
        bridge=cls.extension_path/'staging-bridge.js';source=bridge.read_text(encoding='utf-8')
        needle='if (m.action === "ping") {'
        assert source.count(needle)==1
        source=source.replace(needle,needle+'\n      await new Promise(resolve => setTimeout(resolve, Number(new URL(location.href).searchParams.get("pingDelay") || 0)));')
        bridge.write_text(source,encoding='utf-8')
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass();cls.copy.cleanup()

    def lookup_with_delay(self,delay):
        cls=type(self);cls.mode='empty';cls.accepted=True;cls.trace=[];cls.failure='';cls.verifies=0
        cls.verification_responses=[];cls.search_responses=[]
        page=self.context.new_page();page.goto(c.NY_CONNECTOR_ORIGIN+'/connector-test?pingDelay='+str(delay))
        page.wait_for_function('!!window.CCNYConnector')
        start=time.monotonic()
        try:
            with patch.object(c,'public_profile_for_ein',return_value={}),patch.object(c,'build_search_queries',return_value=[ROW['orgName']]):
                result=page.evaluate('args=>window.CCNYConnector.lookup(args)',{'organization_name':ROW['orgName'],'ein':ROW['ein'],'email':'browser-test@compliance-express.com','admin_passcode':c.ADMIN_PASSCODE,'device_id':'readiness-fixture'})
            return result,time.monotonic()-start
        finally:page.close()

    def test_slow_valid_connector_is_allowed_to_complete_search(self):
        result,elapsed=self.lookup_with_delay(2200)
        self.assertEqual(result['status'],'Not Registered',result)
        self.assertEqual(len(type(self).trace),2,'EIN and name searches must both complete before a negative')

    def test_unresponsive_connector_remains_bounded_and_inconclusive(self):
        result,elapsed=self.lookup_with_delay(30000)
        self.assertEqual(result['status'],'Unable to Confirm',result)
        self.assertEqual(result['status_reason'],'NY_CONNECTOR_UNAVAILABLE')
        self.assertEqual(type(self).trace,[])
        self.assertLess(elapsed,12,'Readiness must remain bounded')

if __name__=='__main__':
    suite=unittest.TestSuite(Readiness(name) for name in ['test_slow_valid_connector_is_allowed_to_complete_search','test_unresponsive_connector_remains_bounded_and_inconclusive'])
    sys.exit(not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful())
