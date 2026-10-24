"""Observe existing Kansas matcher inputs without changing source assets."""
from functools import wraps
import re
from deployment.state_snapshots import CURRENT
from deployment.search_history import SourceQueryReceipt

def observe_ks_matcher(call,module,kind):
    @wraps(call)
    def observed(records,value,*args,**kwargs):
        run=CURRENT.get();receipt=None;rows=None
        if run is not None and run.state=='KS' and isinstance(records,(list,tuple)):
            try:
                if kind=='ein':
                    target=re.sub(r'\D','',value or '')
                    if target:
                        receipt=SourceQueryReceipt(run,{'state':'KS','operation':'search','ein':value,
                            'source_kind':'official_dataset','url':module.SNAPSHOT_SOURCE_URL,
                            'filter_label':'Exact EIN in downloaded state workbook'})
                        selected=[r for r in records if re.sub(r'\D','',r.ein or '')==target]
                else:
                    receipt=SourceQueryReceipt(run,{'state':'KS','operation':'search','name':value,
                        'source_kind':'official_dataset','url':module.SNAPSHOT_SOURCE_URL,
                        'filter_label':'Exact normalized name or legal name in downloaded state workbook'})
                    target=module.normalize_name(value);legal=module.normalize_legal_name(value)
                    selected=[r for r in records if module.normalize_name(r.name)==target
                              or legal and module.normalize_legal_name(r.name)==legal]
                if receipt:
                    rows=[{'Name':r.name,'Registration Number':r.contact_number,'Status':r.status,
                           'Expiration Date':r.expire_date,'City':r.city,'State':r.state,'ZIP':r.zip_code} for r in selected]
            except Exception:rows=None
        try:result=call(records,value,*args,**kwargs)
        except BaseException:
            if receipt:receipt.incomplete()
            raise
        if receipt:
            try:receipt.complete(len(rows),rows=rows) if rows is not None else receipt.incomplete()
            except Exception:pass
        return result
    return observed
