"""Observed October 31 NH header-border omission; source columns stay mandatory."""
import io,unittest
from unittest.mock import patch
from reportlab.pdfgen import canvas
from reportlab.platypus import Table,TableStyle
from testing.run_ky_nh_pdf_guardrails import PdfGuardrails
import registry_snapshot_server as cc
HEADER=['Reg. No.','Charity Name','Address','City','State','Zip','Status','Report Due']
def source(header=None, trailing=None):
 out=io.BytesIO();page=canvas.Canvas(out,pagesize=(1008,612));page.drawString(16,20,'Updated: October 31, 2026')
 rows=PdfGuardrails().rows()
 if trailing is not None:rows.append(trailing)
 table=Table([header or HEADER]+rows,colWidths=[60,260,260,100,40,70,40,80])
 table.setStyle(TableStyle([('INNERGRID',(0,0),(-1,-1),.5,'black'),('LINEABOVE',(0,0),(-1,0),.5,'black'),('LINEBELOW',(0,-1),(-1,-1),.5,'black'),('LINEAFTER',(-1,0),(-1,-1),.5,'black'),('LINEBEFORE',(0,1),(0,-1),.5,'black'),('VALIGN',(0,0),(-1,-1),'BOTTOM')]))
 _,height=table.wrap(950,520);table.drawOn(page,16,550-height);page.save();return out.getvalue()
class MissingHeaderBoundary(unittest.TestCase):
 def test_literal_header_and_all_neighbor_rows_recovered(self):
  import pdfplumber
  raw=source()
  with pdfplumber.open(io.BytesIO(raw)) as pdf:self.assertIsNone(pdf.pages[0].find_tables()[0].extract()[0][0])
  rows,label=cc.nh_parse_pdf_table_records(raw)
  self.assertEqual(label,'October 31, 2026');self.assertEqual([r['registry_id'] for r in rows],['1752','35537','1100'])
  self.assertEqual(rows[1]['registry_name'],'Opportunity@Work, Inc.');self.assertEqual(rows[1]['due_raw'],'11/15/2027')
 def test_completely_empty_trailing_row_is_spacing(self):
  rows,_=cc.nh_parse_pdf_table_records(source(trailing=['']*8));self.assertEqual(len(rows),3)
 def test_partially_populated_trailing_row_is_not_silently_dropped(self):
  with self.assertRaises(ValueError):cc.nh_parse_pdf_table_records(source(trailing=['999','','','','','','','']))
 def test_changed_literal_registration_header_not_invented(self):
  with self.assertRaises(ValueError):cc.nh_parse_pdf_table_records(source(['Different ID']+HEADER[1:]))
 def test_other_column_changes_still_rejected(self):
  with self.assertRaises(ValueError):cc.nh_parse_pdf_table_records(source(HEADER[:-1]+['Different Date']))
 def test_lost_row_still_fails_id_reconciliation(self):
  import pdfplumber.table
  extract=pdfplumber.table.Table.extract
  def drop(table,*args,**kwargs):
   rows=extract(table,*args,**kwargs);return rows[:2]+rows[3:]
  with patch.object(pdfplumber.table.Table,'extract',drop),self.assertRaisesRegex(ValueError,'reconciliation'):cc.nh_parse_pdf_table_records(source())
if __name__=='__main__':unittest.main(verbosity=2)
