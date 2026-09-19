"""Optional native cleanup must not alter lookup values or exceptions."""
import sys, unittest
from pathlib import Path
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c


class NativeMemoryTests(unittest.TestCase):
    def tearDown(self):
        c.native_heap_trimmer.cache_clear()

    def test_cleanup_after_return_keeps_exact_result_and_arguments(self):
        result = {'status': 'Current'}
        operation, trim = Mock(return_value=result), Mock()
        with patch.object(c, 'native_heap_trimmer', return_value=trim):
            wrapped = c.release_native_memory_after(operation)
            self.assertIs(wrapped('name', ein='123456789'), result)
        operation.assert_called_once_with('name', ein='123456789')
        trim.assert_called_once_with(0)

    def test_cleanup_failure_never_replaces_lookup_exception(self):
        error = TimeoutError('registry timeout')
        with patch.object(c, 'native_heap_trimmer', side_effect=OSError('unavailable')):
            with self.assertRaises(TimeoutError) as actual:
                c.release_native_memory_after(Mock(side_effect=error))()
        self.assertIs(actual.exception, error)

    def test_cleanup_failure_never_replaces_success(self):
        for trim in [None, Mock(side_effect=OSError('unsupported'))]:
            with patch.object(c, 'native_heap_trimmer', return_value=trim):
                self.assertEqual(c.release_native_memory_after(lambda: ('Current', None))(), ('Current', None))

    def test_non_linux_does_not_load_library(self):
        with patch.object(c.sys, 'platform', 'win32'), patch('ctypes.CDLL') as load:
            self.assertIsNone(c.native_heap_trimmer())
            load.assert_not_called()

    def test_missing_glibc_function_is_optional(self):
        with patch.object(c.sys, 'platform', 'linux'), patch('ctypes.CDLL', side_effect=OSError):
            self.assertIsNone(c.native_heap_trimmer())

    def test_linux_function_loaded_once_and_declared(self):
        import ctypes
        library = Mock()
        with patch.object(c.sys, 'platform', 'linux'), patch('ctypes.CDLL', return_value=library) as load:
            self.assertIs(c.native_heap_trimmer(), library.malloc_trim)
            self.assertIs(c.native_heap_trimmer(), library.malloc_trim)
            load.assert_called_once_with(None)
        self.assertEqual(library.malloc_trim.argtypes, [ctypes.c_size_t])
        self.assertIs(library.malloc_trim.restype, ctypes.c_int)

    def test_only_three_ocr_entrypoints_wrap_unchanged_implementations(self):
        for name in ['irs_scanned_header_period', 'ma_read_legacy_form_pc', 'ok_certificate_expiration']:
            method = getattr(c, name)
            self.assertEqual(method.__name__, name)
            self.assertTrue(hasattr(method, '__wrapped__'))


if __name__ == '__main__':
    unittest.main()
