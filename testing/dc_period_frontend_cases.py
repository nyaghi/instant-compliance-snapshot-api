"""Actual backend outputs for modeled, separately scoped frontend workflows."""
import base64,copy,io,json,re,tempfile
from PIL import Image,ImageDraw
from pathlib import Path
from deployment import dc_boss_evidence as b,desktop_source_evidence as d,state_snapshots as s
from testing import test_dc_period_reconciliation as fixture

def cases():
    contexts=json.loads((Path(__file__).parent/'fixtures/dc-period-contexts.json').read_text())
    output=[]
    with tempfile.TemporaryDirectory()as folder:
        store=s.SQLiteStore(str(Path(folder)/'source.db'))
        for index,org in enumerate(contexts):
            case=fixture.PeriodReconciliation();case.setUp()
            try:
                result=copy.deepcopy(case.result);result.pop('_worker_desktop_evidence')
                number=str(400215000000+index);name=org['name'];ein=s.digits(org['ein'])
                result.update(ein=ein,organization_name=name,matched_registry_name=name,matched_registry_identifier=number,
                    comments='MODELED prior extract expires2026-10-31; identity already corroborated in fixture.')
                case.run.ein=ein;case.run.run_id=format(index+1,'032x')
                case.run.dc_boss_selected.update(name=name,identifier=number)
                request=b.retained_request(case.run,result);result['_worker_desktop_evidence']=request
                source_name=(re.sub(r'^THE\s+','',name,flags=re.I)+' (THE)'if re.match(r'^THE\s+',name,re.I)else'THE '+name)
                fields={**case.fields,'Licensee':source_name,'License Number':number}
                image=Image.new('RGB',(1000,650),'white');ImageDraw.Draw(image).text((20,20),'LOCAL MODELED FIXTURE\n'+fixture.text(fields),fill='black')
                out=io.BytesIO();image.save(out,format='PNG')
                payload={**case.payload,'request':request,'source_fields':fields,'public_text':fixture.text(fields),
                    'image':base64.b64encode(out.getvalue()).decode(),'captured_at':request['issued_at']+.001}
                update=d.persist_completion(result,payload,store)
                public={k:v for k,v in result.items()if not k.startswith('_worker_')}
                public.update(desktop_evidence_request=request,evidence_url='',confirmation_required=False,execution_version='fixture-MV')
                output.append({'base':public,'update':update})
            finally:case.doCleanups()
    return output

if __name__=='__main__':print(json.dumps(cases()))
