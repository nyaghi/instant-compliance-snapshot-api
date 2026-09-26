"""Pure source parsing reuse: preserve first-row rules, freshness and copies."""
import ast,csv,io,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import registry_snapshot_server as m

ROOT=Path(m.__file__).parent
FUNCTIONS=('fiscal_period_for_ein','organization_name_for_ein','or_snapshot_row_for_ein')

class OregonSourceIndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source=subprocess.check_output(['git','show','bd13982:registry_snapshot_server.py'],cwd=ROOT).decode('utf-8')
        nodes=[n for n in ast.parse(source).body if getattr(n,'name','') in FUNCTIONS]
        cls.previous=dict(m.__dict__)
        exec(compile(ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[])),'original OR readers','exec'),cls.previous)

    def setUp(self):
        m.or_snapshot_index_from_bytes.cache_clear()
        self.addCleanup(m.or_snapshot_index_from_bytes.cache_clear)

    def fixture(self,rows):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        path=Path(folder.name)/'source.txt';out=io.StringIO(newline='')
        writer=csv.writer(out,delimiter='\t');writer.writerows(rows)
        path.write_bytes(out.getvalue().encode('utf-8'));return path

    def row(self,ein,name,begin='01/01/2024',end='12/31/2024'):
        row=['']*16;row[4]=ein;row[6]=name;row[14]=begin;row[15]=end;return row

    def compare(self,path,eins):
        with patch.object(m,'weekly_asset',return_value=path):
            # Function globals must use the same controlled source path.
            for fn in FUNCTIONS:self.previous[fn].__globals__['weekly_asset']=m.weekly_asset
            for ein in eins:
                for fn in FUNCTIONS:
                    with self.subTest(ein=ein,fn=fn):
                        self.assertEqual(getattr(m,fn)(ein),self.previous[fn](ein))

    def test_duplicate_short_and_complete_rows_preserve_individual_first_match(self):
        short=self.row('12-3456789','Earlier name-only record')[:7]
        path=self.fixture([['column']*16,short,self.row('123456789','First period'),
            self.row('123456789','Later period','01/01/2025','12/31/2025'),self.row('987654321','Quoted\tName')])
        self.compare(path,['123456789','12-3456789','987654321','000000001','','123'])
        with patch.object(m,'weekly_asset',return_value=path):
            self.assertEqual(m.organization_name_for_ein('123456789'),'Earlier name-only record')
            self.assertEqual(m.or_snapshot_row_for_ein('123456789')[6],'First period')

    def test_real_current_extract_matches_old_readers_for_distributed_records(self):
        path=m.weekly_asset('OR','Charity_OR.txt');self.assertIsNotNone(path)
        with path.open(encoding='utf-8',newline='') as source:
            rows=list(csv.reader(source,delimiter='\t'))
        eins=[m.canonical_ein_digits(r[4]) for r in rows[1::max(1,len(rows)//30)] if len(r)>=16]
        self.compare(path,eins+['000000001'])

    def test_missing_or_stale_source_cannot_use_a_warm_index(self):
        path=self.fixture([self.row('123456789','Original')])
        with patch.object(m,'weekly_asset',return_value=path):self.assertEqual(m.organization_name_for_ein('123456789'),'Original')
        with patch.object(m,'weekly_asset',return_value=None):
            self.assertEqual(m.organization_name_for_ein('123456789'),'')
            self.assertEqual(m.fiscal_period_for_ein('123456789'),(None,None))
            self.assertIsNone(m.or_snapshot_row_for_ein('123456789'))

    def test_changed_bytes_invalidate_even_when_length_and_timestamp_unchanged(self):
        import os
        path=self.fixture([self.row('123456789','Original')]);stat=path.stat()
        with patch.object(m,'weekly_asset',return_value=path):
            self.assertEqual(m.organization_name_for_ein('123456789'),'Original')
            path.write_bytes(path.read_bytes().replace(b'Original',b'Replaced'))
            os.utime(path,ns=(stat.st_atime_ns,stat.st_mtime_ns))
            self.assertEqual(m.organization_name_for_ein('123456789'),'Replaced')
            self.assertEqual(m.or_snapshot_index_from_bytes.cache_info().misses,2)

    def test_returned_rows_are_copies_and_index_values_immutable(self):
        path=self.fixture([self.row('123456789','Original')])
        with patch.object(m,'weekly_asset',return_value=path):
            m.or_snapshot_row_for_ein('123456789')[6]='mutated'
            self.assertEqual(m.or_snapshot_row_for_ein('123456789')[6],'Original')
            _,names,periods=m.validated_or_snapshot_index()
            with self.assertRaises(TypeError):names['123456789']=()
            with self.assertRaises(TypeError):periods['123456789'][6]='mutated'
            self.assertEqual(m.or_snapshot_index_from_bytes.cache_info().misses,1)

    def test_other_matching_status_date_and_source_rules_unchanged(self):
        from testing.capacity_lab.parsing_scope import strip_or_snapshot_index_optimization
        old=ast.parse(subprocess.check_output(['git','show','bd13982:registry_snapshot_server.py'],cwd=ROOT).decode('utf-8'))
        new=ast.parse(Path(m.__file__).read_text(encoding='utf-8'));strip_or_snapshot_index_optimization(new)
        self.assertEqual(ast.dump(old),ast.dump(new))

if __name__=='__main__':unittest.main()
