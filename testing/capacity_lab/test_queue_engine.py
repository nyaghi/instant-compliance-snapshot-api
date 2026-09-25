"""Master adapter integration. Network disabled, only registry execution stubbed."""
import socket
import os
import unittest
from unittest.mock import patch


def blocked(*args,**kwargs):raise AssertionError('No network in engine regression controls')
socket.getaddrinfo=blocked
import registry_snapshot_server as master
from deployment.queue_engine import execute


class EngineTests(unittest.TestCase):
    def job(self,**changes):
        return {'state':'CO','version':master.APP_VERSION,'payload':{'ein':'123456789','organization_name':'Legal Name','alternate_names':['Verified DBA']},**changes}

    def test_preserves_normalization_alias_context_and_all_result_fields(self):
        expected={'ein':'12-3456789','state':'CO','app_version':master.APP_VERSION,'status':'Current',
            'registration_date':'2000-01-01','last_renewal_date':'2025-06-30','matched_registry_identifier':'ABC',
            'matched_registry_name':'Verified DBA','identity_anchor':{'locations':['Oakland, CA','Concord, CA']}}
        def registry(name,ein,state):
            self.assertEqual(name,'Legal Name');self.assertEqual(state,'CO')
            self.assertEqual(master.known_names_for_ein(ein),['Verified DBA'])
            return expected
        with patch.object(master,'run_single_state_lookup_reliably',side_effect=registry):
            self.assertEqual(execute(master,self.job()),expected)

    def test_discovery_is_same_master_function(self):
        expected={'ein':'12-3456789','names':[{'name':'Verified DBA','evidence':[{'source':'CO'}]}]}
        with patch.object(master,'discover_organization_names',return_value=expected) as call:
            self.assertEqual(execute(master,self.job(state='@discovery')),expected)
            call.assert_called_once_with('Legal Name','123456789')

    def test_wrong_release_and_ny_refused_before_execution(self):
        with patch.dict(os.environ,{'CE_LAB_NY_BROWSER':'0'}):
            for change in ({'state':'NY'},{'state':'XX'},{'version':'wrong'}):
                with self.subTest(change=change),self.assertRaises(ValueError):execute(master,self.job(**change))

    def test_enabled_ny_uses_same_master_routing_and_reviewed_names(self):
        result={'ein':'123456789','state':'NY','status':'Current','app_version':master.APP_VERSION}
        with patch.dict(os.environ,{'CE_LAB_NY_BROWSER':'1'}),patch.object(master,'run_single_state_lookup_reliably',return_value=result) as call:
            self.assertEqual(execute(master,self.job(state='NY')),result)
            call.assert_called_once_with('Legal Name','12-3456789','NY')


if __name__=='__main__':unittest.main(verbosity=2)
