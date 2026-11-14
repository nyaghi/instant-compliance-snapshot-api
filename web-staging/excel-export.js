/* A real, formatted XLSX download. No network calls or lookup-path work. */
(() => {
  'use strict';
  const enc = new TextEncoder();
  const xml = value => String(value ?? '').replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F]/g, '').slice(0,32767)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&apos;');
  const declaration = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>';
  const ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main';
  const relns = 'http://schemas.openxmlformats.org/package/2006/relationships';
  const office = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/';
  const col = n => {let s='';for(n++;n;n=Math.floor((n-1)/26))s=String.fromCharCode(65+(n-1)%26)+s;return s;};
  const crcTable = Array.from({length:256},(_,n)=>{for(let k=0;k<8;k++)n=n&1?0xedb88320^(n>>>1):n>>>1;return n>>>0;});
  const crc = bytes => {let n=0xffffffff;for(const b of bytes)n=crcTable[(n^b)&255]^(n>>>8);return(n^0xffffffff)>>>0;};
  function zip(files) {
    const chunks=[],directory=[];let offset=0,size=0;
    const header=(length,fields)=>{const b=new Uint8Array(length),v=new DataView(b.buffer);for(const [at,width,value] of fields)v[width===4?'setUint32':'setUint16'](at,value,true);return b;};
    for(const [name,value] of Object.entries(files)) {
      const path=enc.encode(name),bytes=enc.encode(value),sum=crc(bytes);
      const local=header(30,[[0,4,0x04034b50],[4,2,20],[6,2,0x800],[12,2,33],[14,4,sum],[18,4,bytes.length],[22,4,bytes.length],[26,2,path.length]]);
      const central=header(46,[[0,4,0x02014b50],[4,2,20],[6,2,20],[8,2,0x800],[14,2,33],[16,4,sum],[20,4,bytes.length],[24,4,bytes.length],[28,2,path.length],[42,4,offset]]);
      chunks.push(local,path,bytes);directory.push(central,path);offset+=local.length+path.length+bytes.length;size+=central.length+path.length;
    }
    const count=Object.keys(files).length;
    return new Blob([...chunks,...directory,header(22,[[0,4,0x06054b50],[8,2,count],[10,2,count],[12,4,size],[16,4,offset]])],{type:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'});
  }
  function sheet(headers, rows, widths, links=[]) {
    const cell=(value,c,r,style)=>`<c r="${col(c)}${r}" s="${style}" t="inlineStr"><is><t xml:space="preserve">${xml(value)}</t></is></c>`;
    const row=(values,r)=>{
      const lines=Math.max(...values.map((v,c)=>String(v??'').split('\n').reduce((n,s)=>n+Math.max(1,Math.ceil(s.length/Math.max(4,widths[c]-3))),0)));
      const height=r===1?32:Math.min(409,Math.max(32,lines*16+10));
      return `<row r="${r}" ht="${height}" customHeight="1">${values.map((v,c)=>cell(v,c,r,r===1?1:r%2?3:2)).join('')}</row>`;
    };
    const hyperlinks=links.length?`<hyperlinks>${links.map((x,i)=>`<hyperlink ref="${x.cell}" r:id="rId${i+1}"/>`).join("")}</hyperlinks>`:'';
    return declaration+`<worksheet xmlns="${ns}" xmlns:r="${office.slice(0,-1)}"><dimension ref="A1:${col(headers.length-1)}${rows.length+1}"/><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><sheetFormatPr defaultRowHeight="18"/><cols>${widths.map((w,i)=>`<col min="${i+1}" max="${i+1}" width="${w}" customWidth="1"/>`).join('')}</cols><sheetData>${row(headers,1)}${rows.map((v,i)=>row(v,i+2)).join('')}</sheetData><autoFilter ref="A1:${col(headers.length-1)}${rows.length+1}"/>${hyperlinks}<printOptions horizontalCentered="1"/><pageMargins left="0.25" right="0.25" top="0.5" bottom="0.5" header="0.2" footer="0.2"/><pageSetup orientation="landscape" paperSize="9" fitToWidth="1" fitToHeight="0"/><headerFooter><oddHeader>&amp;LCompliance Express | CharityClarity</oddHeader><oddFooter>&amp;RPage &amp;P of &amp;N</oddFooter></headerFooter></worksheet>`;
  }
  const styles=declaration+`<styleSheet xmlns="${ns}"><fonts count="2"><font><sz val="11"/><name val="Calibri"/><color rgb="FF243447"/></font><font><b/><sz val="11"/><name val="Calibri"/><color rgb="FFFFFFFF"/></font></fonts><fills count="4"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF16324F"/><bgColor indexed="64"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFF1F5F9"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="4"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf applyNumberFormat="1" numFmtId="49" fontId="1" fillId="2" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf><xf applyNumberFormat="1" numFmtId="49" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf><xf applyNumberFormat="1" numFmtId="49" fontId="0" fillId="3" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>`;
  function hyperlinkRelationships(links) {
    return declaration + `<Relationships xmlns="${relns}">${links.map((link, i) =>
      `<Relationship Id="rId${i+1}" Type="${office}hyperlink" Target="${xml(link.url)}" TargetMode="External"/>`
    ).join('')}</Relationships>`;
  }

  function build(results, options={}) {
    const label=r=>window.CCIdentityReview?.statusLabel(r)||(r.status==='Closed / Withdrawn / Canceled'?'Closed / Withdrawn / Canceled / Inactive':r.status||'Unknown');
    const ein=v=>{const s=String(v||'').replace(/\D/g,'');return s.length===9?s.slice(0,2)+'-'+s.slice(2):String(v||'');};
    const rows=results.map(r=>[r.organization_name,ein(r.ein),r.state,label(r),r.registration_date,r.renewal_filing_value||r.renewal_date,r.matched_registry_name,r.matched_registry_identifier,options.comments?.(r)||r.comments||r.source_note||'']);
    const candidateRows = [];
    const snapshotPath = /^\/state-snapshots\/[a-f0-9]{64}\.pdf$/;
    const evidence=results.map(r=>{
      const history=/^\/state-evidence\/([a-f0-9]{64})\/search-history\.pdf$/.exec(r.search_history_url||'');
      const completedNegative=r.success===true&&(r.status==='Not Registered'||r.state==='IL'&&r.status==='Not Registered / Non-Compliant');
      const validHistory=history&&(!r.evidence_bundle_url||r.evidence_bundle_url===`/state-evidence/${history[1]}/evidence.zip`);
      const incompleteAttempts=r.success===false&&(r.state==='AR'&&r.status_reason==='AR_REQUIRED_SEARCH_INCOMPLETE'
        ||r.state==='NC'&&r.status_reason==='NY_CONNECTOR_NC_RATE_LIMITED');
      const historyOnly = window.CCIdentityReview?.usesSearchHistoryOnly?.(r)
        ?? (completedNegative && r.state !== 'CA');
      const historyPath = validHistory && (historyOnly || completedNegative || incompleteAttempts
        || r.identity_review_evidence_final === true) ? history[0] : '';
      const original = snapshotPath.test(r.evidence_url || '') ? r.evidence_url : '';
      const candidates = historyOnly ? [] : (r.identity_review?.candidates || [])
        .filter(candidate => candidate.decision !== 'reject' && snapshotPath.test(candidate.evidence_url || ''));
      for (const candidate of candidates) {
        candidateRows.push([r.state, candidate.name, candidate.identifier,
          candidate.decision === 'accept' ? 'Identity accepted' : 'Awaiting identity confirmation',
          new URL(candidate.evidence_url, location.origin).href]);
      }
      const path = historyOnly ? historyPath : original || historyPath
        || (candidates.length === 1 ? candidates[0].evidence_url : '');
      const evidenceType = !path ? '' : path === historyPath
        ? (incompleteAttempts ? 'Search attempts' : 'Search history')
        : path === original ? 'State snapshot' : 'Candidate snapshot';
      const evidenceLabel = historyOnly ? 'Names searched unavailable'
        : candidates.length > 1 ? 'See Candidate Evidence tab' : 'Snapshot unavailable';
      return [r.state,label(r),path?new URL(path,location.origin).href:evidenceLabel,r.source_url||'',r.registration_date_source_label||'',r.registration_date_note||'',r.renewal_filing_label||r.renewal_date_source_label||'',r.renewal_filing_note||r.renewal_date_note||'',evidenceType];
    });
    const evidenceLinks = evidence.flatMap((row, i) => row[8] ? [{cell: `C${i+2}`, url: row[2]}] : []);
    const candidateLinks = candidateRows.map((row, i) => ({cell: `E${i+2}`, url: row[4]}));
    const files={
      '[Content_Types].xml':declaration+'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Default Extension="json" ContentType="application/json"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>',
      '_rels/.rels':declaration+`<Relationships xmlns="${relns}"><Relationship Id="rId1" Type="${office}officeDocument" Target="xl/workbook.xml"/></Relationships>`,
      'xl/workbook.xml':declaration+`<workbook xmlns="${ns}" xmlns:r="${office.slice(0,-1)}"><sheets><sheet name="State Results" sheetId="1" r:id="rId1"/><sheet name="Sources and Dates" sheetId="2" r:id="rId2"/></sheets></workbook>`,
      'xl/_rels/workbook.xml.rels':declaration+`<Relationships xmlns="${relns}"><Relationship Id="rId1" Type="${office}worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="${office}worksheet" Target="worksheets/sheet2.xml"/><Relationship Id="rId3" Type="${office}styles" Target="styles.xml"/></Relationships>`,
      'xl/styles.xml':styles,
      'xl/worksheets/sheet1.xml':sheet(['Organization','EIN','State','Status','Initial registration','Latest renewal / filing','Registry name','Registry ID','Comments'],rows,[32,14,9,29,20,22,32,20,70]),
      'xl/worksheets/sheet2.xml':sheet(['State','Status','State evidence','Official registry','Initial date label','Initial date explanation','Latest filing label','Latest filing explanation','Evidence type'],evidence,[9,29,60,60,25,55,25,55,22],evidenceLinks)
    };
    if (evidenceLinks.length) files['xl/worksheets/_rels/sheet2.xml.rels'] = hyperlinkRelationships(evidenceLinks);
    if (candidateRows.length) {
      files['[Content_Types].xml'] = files['[Content_Types].xml'].replace('</Types>',
        '<Override PartName="/xl/worksheets/sheet3.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>');
      files['xl/workbook.xml'] = files['xl/workbook.xml'].replace('</sheets>',
        '<sheet name="Candidate Evidence" sheetId="3" r:id="rId4"/></sheets>');
      files['xl/_rels/workbook.xml.rels'] = files['xl/_rels/workbook.xml.rels'].replace('</Relationships>',
        `<Relationship Id="rId4" Type="${office}worksheet" Target="worksheets/sheet3.xml"/></Relationships>`);
      files['xl/worksheets/sheet3.xml'] = sheet(
        ['State', 'Candidate name', 'Registry ID', 'Identity decision', 'Candidate evidence'],
        candidateRows, [10, 44, 22, 36, 62], candidateLinks);
      files['xl/worksheets/_rels/sheet3.xml.rels'] = hyperlinkRelationships(candidateLinks);
    }
    // Staging diagnostics remain a separate non-display part of the ZIP. They
    // never become worksheet cells, formulas, macros or customer-facing text.
    if(options.diagnostics)files['cc-diagnostics.json']=JSON.stringify({...options.diagnostics,exporter_version:'29.2PQ-evidence.1'});
    return zip(files);
  }
  function buildAlerts(rows) {
    const headers=['Organization','EIN','State','Previous status','New status','Change','Checked (UTC)','Review','Evidence'];
    const links=rows.flatMap((r,i)=>/^https?:\/\/[^\s]+\/api\/alerts\/evidence\/[1-9]\d*$/.test(r[8])?[{row:i+2,url:r[8]}]:[]);
    const files={
      '[Content_Types].xml':declaration+'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>',
      '_rels/.rels':declaration+`<Relationships xmlns="${relns}"><Relationship Id="rId1" Type="${office}officeDocument" Target="xl/workbook.xml"/></Relationships>`,
      'xl/workbook.xml':declaration+`<workbook xmlns="${ns}" xmlns:r="${office.slice(0,-1)}"><sheets><sheet name="Alerts" sheetId="1" r:id="rId1"/></sheets></workbook>`,
      'xl/_rels/workbook.xml.rels':declaration+`<Relationships xmlns="${relns}"><Relationship Id="rId1" Type="${office}worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="${office}styles" Target="styles.xml"/></Relationships>`,
      'xl/styles.xml':styles,
      'xl/worksheets/sheet1.xml':sheet(headers,rows,[42,15,9,26,26,22,27,14,55],links)
    };
    if (links.length) files['xl/worksheets/_rels/sheet1.xml.rels'] = hyperlinkRelationships(links);
    return zip(files);
  }
  window.CCExcelExport=Object.freeze({build,buildAlerts});
})();
