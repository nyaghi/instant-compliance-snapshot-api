"""Maintenance-only gate: publish lookup bytes and original evidence together."""
import hashlib
import importlib.util
import json
from pathlib import Path

def validate_source_evidence(root, state):
    root=Path(root)
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    if state in {'KS','LA'}:
        data=root/'downloadable-data'
        index=json.loads((data/f'{state}-original-row-images.json').read_text())
        if index.get('schema')!=state.lower()+'-original-row-images-v1':
            raise ValueError(f'{state}: unknown original-row evidence schema')
        if state=='KS':
            spec=importlib.util.spec_from_file_location('ks_evidence_publication',root/'KS_weekly_checker.py')
            module=importlib.util.module_from_spec(spec)
            import sys
            sys.modules[spec.name]=module;spec.loader.exec_module(module)
            source=hashlib.sha256(module.load_embedded_workbook_bytes()).hexdigest()
            if source!=module.SNAPSHOT_CHECKSUM or module.SNAPSHOT_SOURCE_URL!=index.get('source_url'):
                raise ValueError('KS: lookup source metadata does not match original evidence')
        else:
            source=digest(data/'LA.xlsx')
            if index.get('source_url')!='https://www.ag.state.la.us/Charity/Registration/Listing':
                raise ValueError('LA: unexpected original source')
        if source!=index.get('source_sha256') or digest(data/f'{state}-original-row-images.zip')!=index.get('archive_sha256'):
            raise ValueError(f'{state}: regenerate original-row images for this workbook before publishing; previous paired dataset retained')
        return {'state':state,'source_sha256':source,'rows':len(index['rows'])}
    if state in {'KY','NH'}:
        index=json.loads((root/'deployment/source-page-indexes.json').read_text())[state]
        expected='downloadable-data/KY.pdf' if state=='KY' else 'registered-charities.pdf'
        if index.get('asset')!=expected or index.get('source_sha256')!=digest(root/expected):
            raise ValueError(f'{state}: PDF lookup and evidence page index differ')
        return {'state':state,'source_sha256':index['source_sha256'],'rows':len(index['record_names'])}
    if state=='OR':
        return {'state':state,'source_sha256':digest(root/'Charity_OR.txt'),'evidence':'Live original detail bound by selected registration and EIN'}
    raise ValueError('Unsupported downloadable state')
