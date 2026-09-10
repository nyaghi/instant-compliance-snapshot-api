"""Column/row fidelity and conservative failure tests for downloadable PDFs."""
import io,json,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from reportlab.pdfgen import canvas
from reportlab.platypus import Table,TableStyle,Paragraph
from reportlab.lib.styles import getSampleStyleSheet
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c
import refresh_downloadable_state_data as refresh

HEADER=['Reg. No.','Charity Name','Address','City/Town','State','Zip Code','Status','Report Due']
def pdf_bytes(rows,header=HEADER):
    out=io.BytesIO();page=canvas.Canvas(out,pagesize=(1008,612))
    page.drawString(16,585,'Registered Charities List')
    page.drawString(16,20,'Updated: September 10, 2026')
    table=Table([header]+rows,colWidths=[60,260,260,100,40,70,40,80])
    table.setStyle(TableStyle([('GRID',(0,0),(-1,-1),0.5,'black'),('VALIGN',(0,0),(-1,-1),'BOTTOM')]))
    _,height=table.wrap(950,520);table.drawOn(page,16,550-height);page.save();return out.getvalue()

class PdfGuardrails(unittest.TestCase):
    def rows(self):
        style=getSampleStyleSheet()['Normal']
        return [['1752','Before Relief','10 Main St','Concord','NH','03301','X','5/15/2025'],
                ['35537','Opportunity@Work, Inc.',Paragraph('1100 Connecticut Avenue NW<br/>Ste 430',style),'Washington','DC','20036','G','11/15/2027'],
                ['1100',Paragraph('After Relief Organization<br/>International, Inc.',style),'35537 Main Street','Boston','MA','02101','S','6/15/2028']]

    def test_real_table_keeps_name_due_date_and_neighbors_together(self):
        rows,label=c.nh_parse_pdf_table_records(pdf_bytes(self.rows()))
        self.assertEqual(label,'September 10, 2026')
        self.assertEqual([(r['registry_id'],r['registry_name'],r['status_code'],r['due_raw']) for r in rows],
                         [('1752','Before Relief','X','5/15/2025'),('35537','Opportunity@Work, Inc.','G','11/15/2027'),('1100','After Relief Organization International, Inc.','S','6/15/2028')])

    def test_blank_source_identifier_keeps_named_row(self):
        rows=self.rows();rows[1][0]=''
        records,_=c.nh_parse_pdf_table_records(pdf_bytes(rows))
        self.assertEqual(records[1]['registry_name'],'Opportunity@Work, Inc.')
        self.assertEqual(records[1]['registry_id'],'')

    def test_unreadable_name_or_date_is_not_silently_dropped(self):
        for index,value in [(1,''),(7,'not a date')]:
            rows=self.rows();rows[1][index]=value
            with self.subTest(index=index),self.assertRaises(ValueError):c.nh_parse_pdf_table_records(pdf_bytes(rows))

    def test_changed_column_headers_are_rejected(self):
        with self.assertRaises(ValueError):c.nh_parse_pdf_table_records(pdf_bytes(self.rows(),HEADER[:-1]+['Different Date']))

    def test_missing_table_is_rejected(self):
        out=io.BytesIO();page=canvas.Canvas(out);page.drawString(20,500,'Registry temporarily unavailable');page.save()
        with self.assertRaises(ValueError):c.nh_parse_pdf_table_records(out.getvalue())

    def test_source_column_detects_a_dropped_record(self):
        import pdfplumber.table
        original=pdfplumber.table.Table.extract
        def lose_row(table,*args,**kwargs):
            rows=original(table,*args,**kwargs);return rows[:2]+rows[3:]
        with patch.object(pdfplumber.table.Table,'extract',lose_row),self.assertRaisesRegex(ValueError,'reconciliation'):
            c.nh_parse_pdf_table_records(pdf_bytes(self.rows()))

    def test_extraction_failure_cannot_return_not_registered(self):
        with patch.object(c,'nh_live_pdf_records',side_effect=ValueError('registration-column reconciliation failed')):
            result=c.search_nh_live_pdf(c.checker.Organization('Opportunity@Work, Inc.','813214432'))
        self.assertFalse(result.success);self.assertNotEqual(result.status,'Not Registered')
        self.assertIn('reconciliation',result.raw_status_text)

    def test_existing_status_interpretation_remains(self):
        records,_=c.nh_parse_pdf_table_records(pdf_bytes(self.rows()))
        for name,expected in [('Before Relief','Delinquent'),('Opportunity@Work, Inc.','Current'),('After Relief Organization International, Inc.','Suspended')]:
            with self.subTest(name=name),patch.object(c,'nh_live_pdf_records',return_value=(records,'September 10, 2026')):
                self.assertEqual(c.search_nh_live_pdf(c.checker.Organization(name,'123456789')).status,expected)

    def test_snapshot_must_reference_exact_pdf(self):
        with tempfile.TemporaryDirectory() as folder:
            snapshot=Path(folder)/'rows.json';pdf=Path(folder)/'source.pdf';pdf.write_bytes(b'changed')
            snapshot.write_text(json.dumps({'source_sha256':'wrong','records':[]}),encoding='utf-8')
            with patch.object(c,'weekly_asset',side_effect=lambda state,name:snapshot if name.endswith('.json') else pdf):
                with self.assertRaisesRegex(ValueError,'verified source PDF'):c.nh_download_live_pdf_records()

    def test_fresh_snapshot_avoids_pdf_parsing_and_network(self):
        with patch.object(c,'nh_parse_pdf_table_records',side_effect=AssertionError('Unexpected cold PDF parse')),patch.object(c.urllib.request,'urlopen',side_effect=AssertionError('Unexpected network')):
            rows,_=c.nh_download_live_pdf_records()
        hit=[r for r in rows if r['registry_id']=='35537']
        self.assertEqual(len(hit),1);self.assertEqual(hit[0]['registry_name'],'Opportunity@Work, Inc.')

    def ky_pdf(self,missing_year=False):
        out=io.BytesIO();page=canvas.Canvas(out,pagesize=(1200,700));style=getSampleStyleSheet()['Normal']
        header=['ID','Name','DBA','Contributions','Revenue','Yr Last Filed','Address 1','Address 2','City','State','Zip']
        data=[header]
        for id_,name,year,address in [('10484','FoodChain','2024','501 W Sixth St<br/>105'),('8507','FoodCorps, Inc.','2024','1140 SE 7th Ave<br/>110'),('17696','Opportunity@work','2024','1100 Connecticut Ave<br/>430'),('11198','Good Sports, Inc.','2025','1515 Washington St'),('9892','Zamir Choral Foundation, Inc.','2024','475 Riverside Dr<br/>1948'),('14503','ZEARN Inc.','2024','2093 Philadelphia Pike<br/>2282')]:
            data.append([id_,name,'','$100','$200','' if missing_year and id_=='8507' else year,Paragraph(address,style),'','City','MA','02101'])
        data.append(['54321','Legal Relief','Known Relief','$100','$200','2024','10 Main St','','City','MA','02101'])
        table=Table(data,colWidths=[45,190,85,85,85,80,150,80,80,45,55]);table.setStyle(TableStyle([('GRID',(0,0),(-1,-1),0.5,'black'),('VALIGN',(0,0),(-1,-1),'BOTTOM')]))
        _,height=table.wrap(1150,600);table.drawOn(page,16,650-height);page.save();return out.getvalue()

    def test_ky_real_columns_preserve_one_word_names_at_names_years_and_neighbors(self):
        rows=c.ky_parse_pdf_table_records(self.ky_pdf())
        self.assertEqual([(r[0],r[1],r[2]) for r in rows],[('10484','FoodChain','2024'),('8507','FoodCorps, Inc.','2024'),('17696','Opportunity@work','2024'),('11198','Good Sports, Inc.','2025'),('9892','Zamir Choral Foundation, Inc.','2024'),('14503','ZEARN Inc.','2024'),('54321','Legal Relief Known Relief','2024')])

    def test_ky_missing_year_cannot_silently_become_current(self):
        with self.assertRaises(ValueError):c.ky_parse_pdf_table_records(self.ky_pdf(missing_year=True))

    def test_ky_source_column_detects_a_dropped_row(self):
        import pdfplumber.table
        original=pdfplumber.table.Table.extract
        with patch.object(pdfplumber.table.Table,'extract',lambda table,*a,**kw:original(table,*a,**kw)[:-1]):
            with self.assertRaisesRegex(ValueError,'reconciliation'):c.ky_parse_pdf_table_records(self.ky_pdf())

    def test_ky_source_date_is_recorded(self):
        out=io.BytesIO();page=canvas.Canvas(out);page.drawString(30,500,'Updated: 9/7/2026');page.save()
        self.assertEqual(refresh.pdf_updated_label(out.getvalue()),'9/7/2026')

if __name__=='__main__':unittest.main(verbosity=2)
