"""Crop original publisher pixels to header, complete selected row and footer.

No source text is drawn or changed. Unknown/ambiguous layouts return no excerpt
so the caller can retain the already validated full original page.
"""
import io,math,re,time

HEADERS={
 'KY':['ID','Name','DBA','Contributions','Revenue','Yr Last Filed','Address 1','Address 2','City','State','Zip'],
 'NH':['Reg. No.','Charity Name','Address','City/Town','State','Zip Code','Status','Report Due'],
}
def normalized(value):return re.sub(r'[^a-z0-9]','',str(value).lower())

def row_regions(page,state,identifier,name):
 if state not in HEADERS or not re.fullmatch(r'\d+',str(identifier)) or not name:return None
 tables=page.find_tables();matches=[]
 for table in tables:
  rows=table.extract()
  if not rows or [re.sub(r'\s+',' ',v or '').strip() for v in rows[0]]!=HEADERS[state]:continue
  for index,row in enumerate(rows[1:],1):
   if str(row[0] or '').strip()!=str(identifier):continue
   parts=str(name).split(' | DBA: ') if state=='KY' else [str(name)]
   name_cells=' '.join(str(v or '') for v in row[1:3] if v is not None) if state=='KY' else str(row[1] or '')
   if not all(normalized(p) and normalized(p) in normalized(name_cells) for p in parts):continue
   header=table.rows[0].bbox;box=table.rows[index].bbox
   # Full row borders retain wrapped name/address fields. Do not guess when
   # source grid geometry changes or neighboring rows overlap.
   if box[1]<header[3]-.1 or box[3]>table.bbox[3]+.1 or box[3]<=box[1]:continue
   matches.append({'row':row,'identifier':identifier,'header_bottom':header[3],
                   'row_top':box[1],'row_bottom':box[3],'table_bottom':table.bbox[3]})
 return matches[0] if len(matches)==1 else None

def original_row_excerpt(raw,state,identifier,name,deadline=float('inf')):
 if state not in HEADERS or time.monotonic()+1>=deadline:return None
 import pdfplumber
 from PIL import Image
 from reportlab.pdfgen.canvas import Canvas
 from reportlab.lib.utils import ImageReader
 plans=[];images=[];start=time.perf_counter()
 with pdfplumber.open(io.BytesIO(raw)) as pdf:
  if not 1<=len(pdf.pages)<=3:return None
  for page in pdf.pages:
   if time.monotonic()+1>=deadline:return None
   plan=row_regions(page,state,str(identifier),name)
   if plan is None:return None
   if page.width*page.height*4>20_000_000:return None
   source=page.to_image(resolution=144,antialias=True).original.convert('RGB')
   scale=source.height/page.height
   bounds=[(0,math.ceil(plan['header_bottom']*scale)),
           (math.floor(plan['row_top']*scale),math.ceil(plan['row_bottom']*scale)),
           (math.floor(plan['table_bottom']*scale),source.height)]
   strips=[source.crop((0,max(0,a),source.width,min(source.height,b))) for a,b in bounds]
   output=Image.new('RGB',(source.width,sum(im.height for im in strips)),'white')
   top=0
   for strip in strips:output.paste(strip,(0,top));top+=strip.height
   images.append(output);plans.append({**plan,'source_pixel_size':source.size,'source_strip_bounds':bounds,'output_pixel_size':output.size})
 if time.monotonic()+.5>=deadline:return None
 result=io.BytesIO();canvas=Canvas(result,pageCompression=1)
 canvas.setTitle('Original state record excerpt')
 for image in images:
  width,height=image.size;canvas.setPageSize((width/2,height/2));canvas.drawImage(ImageReader(image),0,0,width=width/2,height=height/2);canvas.showPage()
 canvas.save()
 return result.getvalue(),{'state':state,'identifier':str(identifier),'pages':plans,'processing_seconds':round(time.perf_counter()-start,6),'method':'Unchanged original header, complete matched row and source footer pixels; no text reconstruction.'}
