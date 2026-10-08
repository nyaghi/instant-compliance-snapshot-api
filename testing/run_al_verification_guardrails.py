"""Fresh verification continuation, identity and fixed-budget controls."""
import base64
import io
import time
import types
import unittest
from unittest.mock import patch, Mock
from PIL import Image
import registry_snapshot_server as cc
from testing.run_final_four_continuation_guardrails import ContinuationControls


class AlabamaVerificationControls(ContinuationControls):
    def evidence(self, response):
        return {'state':'AL','query':response['query'],'complete':False,'verification_pending':True,
                'verification_image':'data:image/png;base64,fixture','verification_id':'fixture-image-12345678'}

    def test_fresh_verification_is_not_a_completed_search_and_retains_deadline(self):
        _, first=self.start('AL')
        original=cc.ny_connector_unpack(first['check_token'],self.auth['email'],self.auth['device_id'])
        with patch.object(cc,'al_read_verification_image',return_value='ABC123'):
            code, second=self.advance(first,self.evidence(first))
        self.assertEqual(code,200);self.assertEqual(second['phase'],'search')
        self.assertEqual(second['query']['verification']['code'],'ABC123')
        record=cc.ny_connector_unpack(second['check_token'],self.auth['email'],self.auth['device_id'])
        self.assertEqual(record['completed'],[]);self.assertEqual(record['expires'],original['expires'])
        self.assertEqual(record['alternate_names'],original['alternate_names'])
        self.assertNotIn('ABC123',str(record));self.assertNotIn('verification_image',str(record))
        self.assertNotEqual(first['query_id'],second['query_id'])
        self.assertEqual(self.advance(second,self.provider(original['pending']['query']))[1]['phase'],'complete')

    def test_rejected_code_can_be_reread_once_but_never_loop_forever(self):
        _, response=self.start('AL')
        for attempt in range(3):
            evidence=self.evidence(response);evidence['query']={k:v for k,v in response['query'].items() if k!='verification'}
            with patch.object(cc,'al_read_verification_image',return_value='ABC123') as reader:
                _, response=self.advance(response,evidence)
            if attempt<2:self.assertEqual(response['phase'],'search')
            else:
                self.assertEqual(response['phase'],'complete');reader.assert_not_called()
                self.assertEqual(response['result']['status'],'Unable to Confirm')
                self.assertEqual(response['result']['lab_diagnostic']['verification_attempts'],2)
                self.assertIn('two bounded code submissions',response['result']['comments'])

    def test_ocr_failure_never_establishes_negative_registration(self):
        for error in [ValueError('uncertain'),TimeoutError('busy'),ImportError('missing'),RuntimeError('native runtime failed')]:
            _, response=self.start('AL')
            with patch.object(cc,'al_read_verification_image',side_effect=error):
                _, result=self.advance(response,self.evidence(response))
            self.assertEqual(result['result']['status'],'Unable to Confirm')

    def test_reader_failure_reports_safe_stage_without_changing_status(self):
        cases = [
            (ValueError('Alabama verification image is uncertain'), 'NY_CONNECTOR_AL_IMAGE_UNCERTAIN'),
            (TimeoutError('Alabama verification reader busy'), 'NY_CONNECTOR_AL_READER_UNAVAILABLE'),
        ]
        for error, reason in cases:
            _, response = self.start('AL')
            with patch.object(cc, 'al_read_verification_image', side_effect=error):
                _, result = self.advance(response, self.evidence(response))
            self.assertEqual(result['result']['status'], 'Unable to Confirm')
            self.assertEqual(result['result']['status_reason'], reason)
            self.assertEqual(result['result']['lab_diagnostic']['verification_attempts'],0)
            self.assertNotIn('fixture-image', str(result['result']))

    def test_foreign_state_mismatched_query_and_wrong_device_do_not_enter_ocr(self):
        for state in ['NC','NV','TN']:
            _, response=self.start(state)
            with patch.object(cc,'al_read_verification_image',side_effect=AssertionError('Must not read')) as reader:
                _, result=self.advance(response,self.evidence(response))
                reader.assert_not_called()
            self.assertEqual(result['phase'],'complete')
            self.assertNotEqual(result['result']['status'],'Not Registered')
        _, response=self.start('AL');evidence=self.evidence(response);evidence['query']={**response['query'],'name':'Wrong'}
        with patch.object(cc,'al_read_verification_image',side_effect=AssertionError('Must not read')) as reader:
            self.assertEqual(self.advance(response,evidence)[1]['phase'],'complete')
            self.assertEqual(self.advance(response,self.evidence(response),device_id='wrong-device')[0],410)
            reader.assert_not_called()

    def test_image_loader_refuses_url_oversize_and_blank_without_calling_ocr(self):
        for value in ['https://example.com/image.png','data:image/png;base64,'+'a'*180001,'data:image/png;base64,!']:
            with self.assertRaises((ValueError,OSError)):
                cc.al_read_verification_image(value,time.monotonic()+1)
        buffer=io.BytesIO();Image.new('RGB',(601,80)).save(buffer,format='PNG')
        with self.assertRaises(ValueError):
            cc.al_read_verification_image('data:image/png;base64,'+base64.b64encode(buffer.getvalue()).decode(),time.monotonic()+1)

    def test_reader_requires_two_confident_whole_line_agreeing_reads(self):
        buffer=io.BytesIO(); image=Image.new('RGB',(125,80),'white')
        image.paste('black',(10,30,110,45));image.save(buffer,format='PNG')
        pixels='data:image/png;base64,'+base64.b64encode(buffer.getvalue()).decode()
        for answers,expected in [([['ABC123',.99],['ABC123',.96]],'ABC123'),
                                 ([['ABC12',.76],['ABC12',.74]],'ABC12'),
                                 ([['ABC123',.99],['ABC124',.99]],None),
                                 ([['ABC123',.60],['ABC123',.99]],None),
                                 ([['ABC1',.99],['ABC1',.99]],None)]:
            reader=Mock(side_effect=[([answer],[.01]) for answer in answers])
            with patch.dict('sys.modules',{'rapidocr_onnxruntime':types.SimpleNamespace(RapidOCR=Mock())}), \
                    patch.object(cc,'_AL_VERIFICATION_OCR',reader):
                if expected:
                    self.assertEqual(cc.al_read_verification_image(pixels,time.monotonic()+3),expected)
                else:
                    with self.assertRaises(ValueError):cc.al_read_verification_image(pixels,time.monotonic()+3)
            self.assertTrue(all(c.kwargs=={'use_det':False,'use_cls':False} for c in reader.call_args_list))
            self.assertTrue(cc._AL_VERIFICATION_OCR_LOCK.acquire(blocking=False))
            cc._AL_VERIFICATION_OCR_LOCK.release()

    def test_visible_revision_does_not_change_protected_version_or_trial_identity(self):
        import ast
        from pathlib import Path
        from deployment.lab_identity import TRIAL_VERSION,TRIAL_RELEASE_LABEL
        tree=ast.parse(Path(cc.__file__).read_text(encoding='utf-8'))
        assignments=[n for n in ast.walk(tree) if isinstance(n,ast.Assign)
                     and any(isinstance(t,ast.Name) and t.id=='APP_VERSION' for t in n.targets)]
        self.assertEqual(len(assignments),1)
        for value in ['approved-baseline',TRIAL_VERSION]:
            scope={'os':types.SimpleNamespace(environ={'CE_APP_VERSION':value})}
            exec(compile(ast.Module(body=assignments,type_ignores=[]),'version-control','exec'),scope)
            self.assertEqual(scope['APP_VERSION'],value)
        validation=(Path(cc.__file__).parent/'deployment/final-four-validation.html').read_text(encoding='utf-8')
        self.assertIn("const VERSION='"+TRIAL_VERSION+"'",validation)
        self.assertEqual(TRIAL_VERSION,'2026.09.29.2-performance-lab')
        self.assertEqual(TRIAL_RELEASE_LABEL,'29.2DF')


if __name__=='__main__':unittest.main()
