import {STATES,REVIEW_DATE} from './rules.js?v=0.19.0';
import {assess,validate,onlineGiftSignal} from './engine.js?v=0.19.0';
import {registrationTable,stateExplanation} from './decisions.js?v=0.19.0';
import {QUESTIONS,ELIGIBILITY_AMOUNTS} from './eligibility.js?v=0.19.0';
const $=id=>document.getElementById(id);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const clientText=v=>String(v??'').replace('this version has not verified every eligibility condition and exemption filing procedure for this state','the exact eligibility conditions and exemption filing procedure need confirmation').replace('This exemption is not automated in the prototype.','The exact eligibility conditions and filing procedure need confirmation.').replace(/prototype’s/g,'state’s').replace(/in this prototype/g,'for this result');
const TYPES=[['charity','Public charity / community nonprofit'],['religious','House of worship / religious organization'],['school','Elementary or secondary school'],['university','College / university'],['hospital','Nonprofit hospital'],['educationalFoundation','Educational foundation'],['hospitalFoundation','Hospital foundation'],['foundation','Other institutional foundation'],['privateFoundation','Private foundation'],['veterans','Veterans organization'],['membership','Membership organization'],['other','Other nonprofit'],['unknown','Not sure']];
const REACH=[['home','My home state'],['selected','Specific states'],['national','Nationwide'],['none','We do not ask for donations'],['grants','Grant applications only']];
const initial=()=>({type:'',base:'',reach:'',online:'',target:[],donorStates:[],operations:[],incorporation:'',solicitor:'unknown',fiscalActual:'',outsideGifts:'unknown',receipts:{},answers:{},grantSources:[],onlineMethod:'unknown',thirdPartyAppeal:'unknown'});
let profile=initial(),report=null,groups=null,editor=null,editingState='',stateEditMode=false;
const option=(v,t,current)=>`<option value="${esc(v)}" ${v===current?'selected':''}>${esc(t)}</option>`;
function stateSelect(key,label,p,blank){return `<div class="field"><label for="${key}">${label}</label><select id="${key}" name="${key}"><option value="">${blank}</option>${STATES.map(s=>option(s.code,s.name,p[key])).join('')}</select></div>`;}
function choices(key,label,items,p,hint=''){
 return `<fieldset class="choice-field"><legend>${label}</legend>${hint?`<p class="hint">${hint}</p>`:''}<div class="choices">${items.map(([v,t])=>`<label class="choice"><input type="radio" name="${key}" value="${v}" ${p[key]===v?'checked':''}><span>${t}</span></label>`).join('')}</div></fieldset>`;
}
function picker(key,label,p,hint){return `<fieldset class="picker"><legend>${label}</legend><p class="hint">${hint}</p><div class="picker-actions"><button type="button" class="textbtn" data-bulk-state="${key}" data-state-action="all">Select all</button><button type="button" class="textbtn" data-bulk-state="${key}" data-state-action="clear">Clear all</button><span data-state-selection-count="${key}" role="status" aria-live="polite">${(p[key]||[]).length} of ${STATES.length} selected</span></div><div class="state-grid">${STATES.map(s=>`<label class="state-check"><input type="checkbox" data-state-key="${key}" value="${s.code}" ${(p[key]||[]).includes(s.code)?'checked':''}>${s.name}</label>`).join('')}</div></fieldset>`;}
const YES_NO=[['yes','Yes'],['no','No'],['unknown','Not sure']];
const GIFT_NUMBERS=['amount','count','donors','intended','nationalTotal'];
function validNumericText(value){
 if(value===undefined||value===null||value==='')return true;
 if(typeof value==='number')return Number.isFinite(value);
 if(typeof value!=='string')return false;
 const text=value.trim().replace(/^\$/,'');
 return text===''||/^-?(?:\d+(?:\.\d*)?|\.\d+|\d{1,3}(?:,\d{3})+(?:\.\d*)?)$/.test(text);
}
function normalizeNumeric(value){
 if(typeof value!=='string')return value;
 const text=value.trim().replace(/^\$/,'');
 return validNumericText(value)?text.replace(/,/g,''):value;
}
function formatNumeric(value){
 if(value===undefined||value===null||value==='')return '';
 if(!validNumericText(value))return String(value);
 const text=String(normalizeNumeric(value));if(!text)return '';
 if(/[eE]/.test(text))return Number(text).toLocaleString('en-US',{maximumFractionDigits:20});
 const [whole,fraction]=text.split('.'),integer=(whole||'0').replace(/^(-?)0+(?=\d)/,'$1');
 return integer.replace(/\B(?=(\d{3})+(?!\d))/g,',')+(fraction!==undefined&&fraction!==''?'.'+fraction:'');
}
function money(key,label,value,hint='',attrs=''){
 return `<div class="field"><label for="${key}">${esc(label)}</label><input id="${key}" name="${key}" type="text" inputmode="decimal" data-numeric autocomplete="off" value="${esc(formatNumeric(value))}" ${attrs}>${hint?`<span class="hint">${esc(hint)}</span>`:''}</div>`;
}
function giftMarkup(p){
 if(!p.donorStates.length)return '';
 return p.donorStates.map(code=>{
  const name=STATES.find(s=>s.code===code)?.name,row=p.receipts[code]||{};
  const field=(key,label,hint='')=>money(`gift-${code}-${key}`,label,row[key],hint,`data-gift-state="${code}" data-gift-key="${key}"`);
  const select=(key,label,values)=>`<div class="field"><label for="gift-${code}-${key}">${esc(label)}</label><select id="gift-${code}-${key}" data-gift-state="${code}" data-gift-key="${key}">${values.map(([v,t])=>option(v,t,row[key]||'unknown')).join('')}</select></div>`;
  return `<section class="gift-entry"><h3>${esc(name)} gifts</h3><p class="hint">Leave unknown amounts blank. A gift alone is not being treated as a directed appeal.</p>${field('amount',`Total ${name} gifts ($)`,'Record the amount here. Confirm the period and source below for any state-specific donation test.')}<details class="gift-details" ${['CO','WI','MS','TN'].includes(code)?'open':''}><summary>Donation period and source</summary>${select('period','Period for these gifts',[['unknown','Not sure'],['completedFiscal','Same completed fiscal year as the total above'],['current','Current year']])}${select('origin','How did these gifts arrive?',[['unknown','Not sure'],['website','Through our online donation page'],['unsolicited','Unsolicited gifts'],['grants','Grants'],['mixed','More than one of these']])}${select('repeated','Are these isolated gifts or ongoing support?',[['unknown','Not sure'],['no','Isolated gifts'],['yes','Repeated or ongoing support']])}${['CO','WI','TN'].includes(code)?field('count','Number of online contributions (not donors)','Use the same period as the state total.'):''}${code==='CO'?field('nationalTotal','All-state contributions for this same period ($)','Needed for Colorado’s percentage test. Do not use a different year’s total.'):''}${code==='MS'?field('donors','Number of distinct resident donors')+field('intended','State contributions you intend to receive ($)'):''}</details></section>`;
 }).join('');
}
function solicitorMarkup(p){return (p.base==='LA'||p.reach==='national'||p.target.includes('LA'))&&!['none','grants'].includes(p.reach)?choices('solicitor','Do you use a professional solicitor?',[['yes','Yes'],['no','No'],['unknown','Not sure']],p,'An outside person or business paid to ask for donations. A payment processor alone is not a professional solicitor. This affects Louisiana’s registration requirement.'):'';}
function formMarkup(p){
 const asks=!['none','grants'].includes(p.reach);
 return `<div class="grid2"><div class="field"><label for="type">1. What kind of nonprofit are you?</label><select id="type" name="type"><option value="">Choose a category</option>${TYPES.map(([v,t])=>option(v,t,p.type)).join('')}</select><span class="hint">Choose the entity itself. A school or hospital foundation is assessed separately.</span></div>${stateSelect('base','2. Where is your principal office?',p,'Choose your home state')}</div>
 ${choices('reach','3. Where do you direct requests for donations?',REACH,p,'Include emails, ads, events and direct appeals. A public donation page alone does not mean you target every state.')}
 ${p.reach==='selected'?picker('target','Which states do you target?',p,'Select where you direct appeals or hold fundraising events. Your home state is included automatically.'):''}
 ${p.reach==='grants'?picker('target','Where are the grantmakers you apply to?',p,'Your home state is included. Grant applications can count as solicitation; grant-only exclusions differ by state.'):''}
 ${asks?choices('online','4. Do you ask for donations online?',[['yes','Yes'],['no','No'],['unknown','Not sure']],p,'Include donation requests on your website, social media or crowdfunding.'):''}
 ${money('fiscalActual','5. Contributions in your last completed fiscal year, from all states ($)',p.fiscalActual,'Use actual records, or leave blank if not known. Some exemptions require other years or different definitions; we ask only when relevant.')}
 ${choices('outsideGifts','6. Have you received gifts from outside your home state?',YES_NO,p,'Include gifts through your donation page. Receiving a gift does not automatically mean registration is required.')}
 ${p.outsideGifts==='yes'||p.donorStates.length?picker('donorStates','Which states did those gifts come from?',p,'Select known donor states. Include gifts even if you did not ask donors there.')+`<div id="giftFields">${giftMarkup(p)}</div>`:''}
 <details class="connections"><summary>Offices, programs, property or incorporation elsewhere (optional)</summary><p class="hint">Include where you are incorporated or have offices, programs or charitable property.</p>${stateSelect('incorporation','State of incorporation',p,'Not sure / not applicable')}${picker('operations','Additional offices, programs or charitable assets',p,'Select states outside your home state where you operate or hold charitable property.')}</details>
 <div id="solicitorQuestions">${solicitorMarkup(p)}</div>`;
}
function prepareProfile(p){
 const asks=!['none','grants'].includes(p.reach),national=p.reach==='national';
 const receipts=Object.fromEntries(p.donorStates.map(code=>{
  const row=p.receipts[code]||{};
  // Unknown periods can establish a connection, but cannot clear a state using
  // a fiscal-year website threshold. Current-year totals stay distinct.
  const measured=Object.fromEntries(Object.entries(row).map(([k,v])=>[k,GIFT_NUMBERS.includes(k)?normalizeNumeric(v):v]));
  if((row.period!=='completedFiscal'&&['CO','WI'].includes(code)||!['current','completedFiscal'].includes(row.period)&&['TN','MS'].includes(code))){delete measured.amount;delete measured.count;delete measured.donors;delete measured.intended;delete measured.nationalTotal;}
  return [code,measured];
 }));
 const answers=Object.fromEntries(Object.entries(p.answers).map(([k,v])=>[k,MONEY_FACTS[k]?normalizeNumeric(v):v]));
 return {...answers,taxStatus:'recognized501c3',screeningMode:'activity',type:p.type,base:p.base,fiscalActual:normalizeNumeric(p.fiscalActual),
  // Unanswered jurisdiction facts stay unknown; domicile is not incorporation.
  incorporation:p.incorporation,operations:[...p.operations],donorStates:[...p.donorStates],registered:[],bankStates:p.answers.msBank==='yes'?['MS']:[],receipts,
  homeOnly:p.reach==='none'?'none':p.reach==='grants'?'grants':p.reach==='home'&&!p.donorStates.some(c=>c!==p.base)?'yes':'no',
  target:asks&&national?STATES.map(s=>s.code):p.reach==='none'?[]:p.reach==='home'?[p.base]:[...p.target],
  online:asks?p.online:'no',onlineReach:national?'nationwide':p.reach==='selected'?'selected':'public',onlineNationwide:national?'yes':'no',
  // Do not convert unasked compensation or category facts into a No answer.
  solicitor:p.answers.solicitor||p.solicitor,consultant:p.answers.consultant||'unknown',paidStaff:p.answers.paidStaff||'unknown',allUnpaid:p.answers.allUnpaid||'unknown',specialCategory:p.answers.specialCategory||'unknown',grantsOnly:p.reach==='grants'?'yes':'unknown',grantSources:p.grantSources||[],onlineMethod:p.onlineMethod||'unknown',thirdPartyAppeal:p.thirdPartyAppeal||'unknown'};
}
function inputErrors(p){
 const errors=validate(prepareProfile(p));
 const values=[p.fiscalActual,...Object.entries(p.answers).filter(([k])=>MONEY_FACTS[k]).map(([,v])=>v),...Object.values(p.receipts).flatMap(row=>GIFT_NUMBERS.map(k=>row[k]))];
 if(values.some(v=>!validNumericText(v)))errors.push('Use numbers with commas in groups of three, such as 100,000,000.');
 if(!REACH.some(([v])=>v===p.reach))errors.push('Choose where you ask for donations.');
 if(p.incorporation&&!STATES.some(s=>s.code===p.incorporation))errors.push('Choose a valid state of incorporation.');
 if(!['yes','no','unknown'].includes(p.solicitor))errors.push('Choose Yes, No or Not sure for professional solicitation.');
 if(!['none','grants'].includes(p.reach)&&!['yes','no','unknown'].includes(p.online))errors.push('Answer the online fundraising question.');
 if(p.reach==='selected'&&!p.target.length)errors.push('Select at least one state you target.');
 if(!['yes','no','unknown'].includes(p.outsideGifts))errors.push('Answer the outside gifts question.');
 if(p.outsideGifts==='yes'&&!p.donorStates.length)errors.push('Select at least one known donor state, or choose Not sure.');
 if(p.outsideGifts==='yes'&&p.donorStates.length&&!p.donorStates.some(c=>c!==p.base))errors.push('Choose a donor state outside your home state, or update the outside gifts answer.');
 if(p.outsideGifts==='no'&&p.donorStates.some(c=>c!==p.base))errors.push('Outside donor states conflict with No outside gifts.');
 for(const row of Object.values(p.receipts))for(const k of GIFT_NUMBERS)if(row[k]!==undefined&&row[k]!==''&&(!Number.isFinite(Number(normalizeNumeric(row[k])))||Number(normalizeNumeric(row[k]))<0||['count','donors'].includes(k)&&!Number.isInteger(Number(normalizeNumeric(row[k])))))errors.push('Gift amounts must be nonnegative; contribution and donor counts must be whole numbers.');
 return errors;
}
function render(){ $('formPanel').innerHTML=formMarkup(profile); }
function showErrors(id,errors){$(id).textContent=errors.join(' ');$(id).hidden=false;$(id).focus();}
function createReport(){
 const errors=inputErrors(profile);if(errors.length){showErrors('error',errors);return false;}
 hideStateTip();
 const facts=prepareProfile(profile);
 report=assess(facts);groups=registrationTable(report,facts,{includeGeneralFramework:true});
 $('error').hidden=true;$('assessment').hidden=true;$('formPanel').innerHTML='';$('report').hidden=false;renderReport();
 $('reportTitle').focus();return true;
}
const COLUMN_TITLES=['States where registration may not be required','States where potential exemptions may apply','States where registration may be required'];
const stateName=r=>`<button type="button" class="state-tip-trigger" data-explain-state="${r.code}" data-edit-state="${r.code}" aria-haspopup="dialog" aria-controls="editDialog" aria-label="${esc(r.name)}: update activity or donations">${esc(r.name)}</button>`;
function giftBadge(r){
 const row=profile.receipts[r.code];if(!row)return '';
 const amount=row.amount!==undefined&&row.amount!==''?Number(normalizeNumeric(row.amount)):null;
 const signal=onlineGiftSignal(r.code,prepareProfile(profile));
 const excluded=r.status==='exemption'&&!r.discretionaryRequest&&['none','optional'].includes(r.filing);
 const text=[amount>0?`$${amount.toLocaleString('en-US')} reported`:'',signal?.text||'',signal&&excluded?'Exclusion supported':''].filter(Boolean).join(' · ');
 return text?`<span class="gift-badge${signal&&!excluded?' gift-alert':''}" ${signal?'data-gift-signal="threshold"':''}>${esc(text)}</span>`:'';
}
// Eligibility and filing are separate; never label answers as verified approval.
function exemptionMarkup(r){
 if(r.discretionaryRequest)return '<span class="requirement-label">Waiver request available</span><span class="requirement-label">Apply for state approval</span>';
 if(r.exemptionEvidence!=='answers')return '<span class="requirement-label">Potential exemption</span><span class="requirement-label">Eligibility to confirm</span>';
 const next=r.approvalRequired?'Apply for state approval':({none:'No exemption filing indicated',optional:'State confirmation optional',application:'Submit an exemption claim',annual:'Annual exemption filing required',simplified:'Annual small charity paperwork required',verify:'Confirm the filing procedure'}[r.filing]||'Confirm the filing procedure');
 return `<span class="requirement-label">Eligibility supported by your answers</span><span class="requirement-label">${next}</span>`;
}
function renderReport(){
 const scope='Based on where you ask for donations, receive gifts and operate';
 // User-authorized presentation: no-activity states share the first column,
 // explicitly scoped to current answers; their engine status stays undetermined.
 const columns=[[...groups.notRequired,...groups.notAssessed].sort((a,b)=>a.name.localeCompare(b.name,'en')),groups.potentialExemption,groups.mayRequired];
 const list=(rows,column)=>rows.length?`<ul class="state-list">${rows.map(r=>`<li data-state="${r.code}">${stateName(r)}${giftBadge(r)}${column===2?` <span class="requirement-label">${r.status==='required'?'Registration indicated':r.nexusPending?'Donation activity needs review':'Confirm requirement'}</span>`:''}${column===1?exemptionMarkup(r):''}</li>`).join('')}</ul>`:'<p class="no-states">None indicated</p>';
 $('report').innerHTML=`<div class="report-head"><div><span class="eyebrow">YOUR HEAD START</span><h2 id="reportTitle" tabindex="-1">Your nationwide registration overview</h2><p>${esc(TYPES.find(([v])=>v===profile.type)?.[1])} · ${esc(STATES.find(s=>s.code===profile.base)?.name)} principal office<br>${esc(scope)}</p></div><div class="report-actions"><button class="secondary" id="editBtn">Change answers</button><button class="textbtn" id="printBtn">Print / save PDF</button></div></div>
 <p class="result-note guide-note">All 50 states and DC, based on your current answers. A public donation page alone is not treated as nationwide fundraising.</p>
 <table class="registration-table"><caption class="sr-only">Initial charitable organization registration overview based on actual reported activity</caption><thead><tr>${COLUMN_TITLES.map((title,i)=>`<th scope="col"><span>${title}</span>${i===0?'<small>Based on your current answers</small>':''}<small>${columns[i].length} ${columns[i].length===1?'jurisdiction':'jurisdictions'}</small></th>`).join('')}</tr></thead><tbody><tr>${columns.map((rows,i)=>`<td data-column="${i}" data-heading="${COLUMN_TITLES[i]}">${list(rows,i)}</td>`).join('')}</tr></tbody></table>
 <p class="state-tip-hint">Hover or focus for an explanation. Select a state to change its donations or activity.</p>
 <p class="result-note">The first column includes states where you haven’t reported fundraising, gifts or operations. It is based on those answers, not clearance for future activity. State donation tests differ; $25,000 is not a universal cutoff.</p>
 <p class="result-note">The exemption column includes both possible exemptions and eligibility supported by your answers. Head Start does not confirm state approval. An exemption may require no filing, optional confirmation or a required exemption claim; hover or select the state for guidance.</p>
 <p class="result-note"><strong>Your reported activity:</strong> ${esc(REACH.find(([v])=>v===profile.reach)?.[1])}${profile.fiscalActual!==''?` · $${Number(normalizeNumeric(profile.fiscalActual)).toLocaleString('en-US')} in all-state contributions last completed fiscal year`:''}${profile.donorStates.length?` · Gifts reported: ${esc(profile.donorStates.map(c=>STATES.find(s=>s.code===c)?.name).join(', '))}`:''}.</p>
 ${profile.outsideGifts==='unknown'?'<p class="result-note">Outside gifts are not yet confirmed. Add known donor states and amounts before relying on the geographic scope.</p>':''}
 ${profile.reach==='home'&&profile.online==='yes'?'<p class="result-note">A public donation page alone does not establish a filing task in every state. Reassess for targeted appeals or repeated or substantial outside support; there is no universal donation amount that clears every state.</p>':''}
 <div class="provider-note"><strong>Check your actual registration status</strong><p>Continue to Aurora with these answers, then combine the findings in your Insight report.</p><button type="button" class="primary" id="continueAurora">Continue to Aurora →</button></div>
 <div class="provider-note"><strong>Need guidance specific to your organization?</strong><p>Contact a compliance service provider to confirm eligibility and what needs to be filed.</p><a href="mailto:info@compliance-express.com">Contact Compliance Express →</a></div>
 <p class="scope-note">This table covers initial charitable organization registration, including separate charitable trust requirements where relevant. Entity, tax and professional fundraiser filings are separate. It does not verify current registration status or authorize stopping existing filings.</p>
 <p id="reportNotice" role="status" aria-live="polite"></p>`;
 $('editBtn').onclick=openEditor;$('printBtn').onclick=()=>window.print();
 $('continueAurora').onclick=()=>{$('handoffError').hidden=true;$('handoffName').value=profile.organizationName||'';$('handoffEin').value=profile.ein||'';$('auroraDialog').showModal();};
}
function headStartPacket(name,ein){
 const eligibility=new Map(groups.potentialExemption.map(r=>[r.code,r]));
 return {schema_version:'cc.head-start/1',assessment_id:crypto.randomUUID(),organization_name:name,ein,
  assessed_at:report.assessedAt,engine_version:report.version,ui_version:'0.19.0',rules_reviewed_at:report.reviewDate,
  profile:structuredClone(prepareProfile(profile)),requirements:report.results.map(r=>({...structuredClone(r),
   exemption_evidence:eligibility.get(r.code)?.exemptionEvidence||null,possible_exemption:eligibility.has(r.code),
   approvalRequired:!!r.approvalRequired,discretionaryRequest:!!r.discretionaryRequest,deferred:!!r.deferred,nexusPending:!!r.nexusPending}))};
}
function connectAurora(e){
 e.preventDefault();const name=$('handoffName').value.trim(),ein=$('handoffEin').value.replace(/\D/g,'');
 if(!name||name.length>250||!/^\d{9}$/.test(ein)||ein==='000000000'){showErrors('handoffError',['Enter the organization name and a nine-digit EIN.']);return;}
 profile.organizationName=name;profile.ein=ein.slice(0,2)+'-'+ein.slice(2);
 const packet=headStartPacket(name,ein),nonce=crypto.randomUUID();
 const labOrigin='https://charityclarity-final-four-29-2.onrender.com';
 const destination=new URL('/instant-compliance-snapshot',labOrigin);
 destination.hash=new URLSearchParams({hs_sender:location.origin,hs_nonce:nonce}).toString();
 const child=window.open(destination.href,'_blank');
 if(!child){showErrors('handoffError',['Allow this page to open Aurora, then continue again. Your answers are retained.']);return;}
 let timeout;
 const receive=event=>{
  if(event.source!==child||event.origin!==destination.origin||event.data?.nonce!==nonce)return;
  if(event.data.type==='cc.headstart.ready')child.postMessage({type:'cc.headstart.assessment',nonce,assessment:packet},destination.origin);
  if(event.data.type==='cc.headstart.accepted'){clearTimeout(timeout);window.removeEventListener('message',receive);$('reportNotice').textContent='Your assessment is connected. Check registration status in Aurora, then choose Connect to Insight.';}
 };
 window.addEventListener('message',receive);
 timeout=setTimeout(()=>{window.removeEventListener('message',receive);$('reportNotice').textContent='Your Head Start answers are retained. If Aurora did not connect, return here and continue again.';},300000);
 $('auroraDialog').close();
}
const MONEY_FACTS={
 fiscalExpected:['Expected contributions this fiscal year, from all states ($)','An actual previous-year total cannot substitute for this estimate.'],fiscalPrior:['All-state contributions one fiscal year before the most recent ($)','Use actual completed-year records.'],fiscalPriorTwo:['All-state contributions two fiscal years before the most recent ($)','Use actual completed-year records.'],calendarPrevious:['Previous calendar year all-state contributions ($)','Do not substitute a fiscal-year amount.'],calendarActual:['Current calendar year contributions received so far ($)','Use the state’s contribution definition.'],calendarExpected:['Expected full calendar year all-state contributions ($)','Do not substitute a fiscal-year amount.'],coFiscalGross:['Current fiscal year adjusted worldwide gross revenue ($)','Colorado excludes government and 501(c)(3) grants; this is not simply donations.'],coExpectedGross:['Expected full fiscal year adjusted worldwide gross revenue ($)','Use Colorado’s revenue definition.'],nyFiscalActual:['New York contributions received this fiscal year ($)','New York’s small solicitation test uses New York contributions, not the all-state figure.'],nyFiscalExpected:['Expected New York contributions this fiscal year ($)','Separate charitable trust duties can still apply.'],...ELIGIBILITY_AMOUNTS};
const ROLE_FACTS={solicitor:['Do you hire an outside professional solicitor?','A payment processor alone is not a solicitor.'],consultant:['Do you hire fundraising counsel or a consultant?','Different from an outside business that asks donors directly.'],paidStaff:['Are employees paid to ask for donations?','Paid program staff who do not solicit are a separate fact.'],coVenturer:['Do you use a commercial co-venturer?','For example, a business promoting donations tied to sales.'],allUnpaid:['Are all organization functions performed without compensation?','This is broader than volunteer fundraising alone.'],privateBenefit:['Do officers or members receive income from charitable funds?','Confirm this separately from ordinary program costs.'],msBank:['Do you have a Mississippi bank account or mailing address?','Mississippi considers these contacts separately from donor counts.']};
const CONDITIONS={noSolicitor:['solicitor'],noProfessional:['solicitor','consultant'],noExternal:['solicitor','consultant','coVenturer'],noPaidSolicitation:['paidStaff','solicitor'],unpaidFundraising:['paidStaff','solicitor'],noPrivateBenefit:['privateBenefit']};
const OPTIONAL_FACTS=new Set(['nvRelatedOnly','nvNamedBeneficiary','nvAlumniOnly','ksCommunityFoundation','ksLicensedCenter','kyMemberOnly','kyStudentPta','vaMembersOnly','vaRegisteredAffiliate','vaLocalOnly','vaLocalCosts']);
function followUpKeys(p,code){
 let a;try{a=assess(prepareProfile(p));}catch{return [];}
 const rows=a.results.filter(r=>r.status!=='outside'&&!r.deferred&&(!code||r.code===code));
 const keys=rows.flatMap(r=>r.inputs||[]).flatMap(k=>CONDITIONS[k]||[k]);
 if(rows.some(r=>r.nexusPending&&['CO','WI','MS','TN'].includes(r.code)))keys.push(...rows.filter(r=>r.code==='MS').map(()=> 'msBank'));
 if(code==='MS'&&p.online==='yes')keys.push('msBank');
 if(code==='TX')keys.push('specialCategory');
 return [...new Set(keys)].filter(k=>k!=='fiscalActual'&&!OPTIONAL_FACTS.has(k)&&(QUESTIONS[k]||ROLE_FACTS[k]||MONEY_FACTS[k]));
}
function followUps(p){
 const keys=followUpKeys(p,editingState);
 if(!keys.length)return '';
 const title=editingState?`${STATES.find(s=>s.code===editingState)?.name}: facts that affect your result`:'Only where relevant: eligibility and filing facts';
 return `<section class="eligibility-fields"><h3>${esc(title)}</h3><p class="hint">Answer what you know. We do not treat blanks as zero or Not sure as No.</p>${keys.map(k=>{
  let meta=MONEY_FACTS[k]||QUESTIONS[k]||ROLE_FACTS[k];const value=p.answers[k]??(k==='solicitor'?p.solicitor:'unknown');
  if(k==='caPrimaryInstitution'&&p.type==='religious')meta=['Is this legal entity primarily a religious institution?','Confirm the entity itself. A separate supporting charity or foundation is assessed on its own facts.'];
  if(k==='caPrimaryInstitution'&&p.type==='hospital')meta=['Is this legal entity primarily a nonprofit hospital?','Confirm the hospital itself, rather than a separate fundraising foundation.'];
  if(MONEY_FACTS[k])return money(`answer-${k}`,meta[0],p.answers[k],meta[1],`data-answer-key="${k}"`);
  return choices(`answer-${k}`,esc(meta[0]),YES_NO,{[`answer-${k}`]:value},esc(meta[1]));
 }).join('')}</section>`;
}
function stateActivityMarkup(p){
 const code=editingState,name=STATES.find(s=>s.code===code)?.name;
 const direct=p.reach==='national'||p.reach==='home'&&code===p.base||p.reach==='selected'&&p.target.includes(code);
 const check=(key,label,checked)=>`<label class="activity-choice"><input type="checkbox" data-activity-key="${key}" ${checked?'checked':''}><span>${esc(label)}</span></label>`;
 return `<section class="state-activity"><p>Update only what applies in ${esc(name)}.</p>${code===p.base?'<p class="hint">Your principal office and home-state fundraising are set in your main answers below.</p>':check('appeals',`We direct requests for donations to people in ${name}`,direct)}${check('gifts',`We receive gifts from donors in ${name}`,p.donorStates.includes(code))}${code===p.base?'':check('operations',`We have an office, program or charitable property in ${name}`,p.operations.includes(code))}${p.donorStates.includes(code)?`<div id="giftFields">${giftMarkup({...p,donorStates:[code]})}</div>`:''}${['none','grants'].includes(profile.reach)&&direct?choices('online','Do you now request donations online?',YES_NO,p,'Update this if your fundraising activity has changed.'):''}${code==='LA'?solicitorMarkup(p):''}</section>`;
}
function changeStateActivity(p,key,checked){
 const code=editingState,update=(list)=>checked?[...new Set([...list,code])]:list.filter(c=>c!==code);
 if(key==='gifts'){
  p.donorStates=update(p.donorStates);if(!checked)delete p.receipts[code];
  p.outsideGifts=p.donorStates.some(c=>c!==p.base)?'yes':profile.outsideGifts==='no'?'no':'unknown';
 }
 if(key==='operations')p.operations=update(p.operations);
 if(key==='appeals'){
  if(p.reach==='national'&&!checked)p.target=STATES.map(s=>s.code).filter(c=>c!==code);
  else p.target=update(p.target);
  if(checked){if(['none','grants'].includes(p.reach))p.online='unknown';p.reach=p.reach==='national'?'national':'selected';}
  else if(p.target.some(c=>c!==p.base))p.reach='selected';
  else{p.reach=['none','grants'].includes(profile.reach)?profile.reach:'home';if(['none','grants'].includes(p.reach))p.online=profile.online;}
 }
}
function editorMarkup(p){
 if(!editingState)return formMarkup(p)+followUps(p);
 const name=STATES.find(s=>s.code===editingState)?.name;
 const facts=assess(prepareProfile(p)).results.find(r=>r.code===editingState);
 return `<p class="hint">${esc(TYPES.find(([v])=>v===p.type)?.[1])} · ${esc(STATES.find(s=>s.code===p.base)?.name)} principal office</p>${stateEditMode?stateActivityMarkup(p):''}${facts?.inputs.includes('fiscalActual')?money('fiscalActual','Most recent completed fiscal year contributions, all states ($)',p.fiscalActual,'Use actual records; leave unknown values blank.'):''}${!stateEditMode&&p.donorStates.includes(editingState)?`<details class="connections"><summary>Review ${esc(name)} gift details</summary><div id="giftFields">${giftMarkup({...p,donorStates:[editingState]})}</div></details>`:''}${followUps(p)}${stateDetails(p,facts)}<button type="button" class="textbtn" data-edit-all>Change organization or fundraising answers</button>`;
}
function stateDetails(p,r){
 if(!r)return '';
 const grantKinds=[['government','Government'],['charity','501(c)(3) public charities'],['other501c','Other 501(c) organizations'],['privateFoundation','Private foundations'],['corporate','For-profit corporations'],['other','Other / not sure']];
 const grant=p.reach==='grants'?`<fieldset class="choice-field"><legend>Which types of grantmakers do you apply to?</legend><p class="hint">Select every type. These are your organization’s grant requests; state exclusions differ.</p>${grantKinds.map(([v,t])=>`<label class="choice"><input type="checkbox" data-grant-kind="${v}" ${(p.grantSources||[]).includes(v)?'checked':''}><span>${t}</span></label>`).join('')}</fieldset>`:'';
 const extra=r.code==='AK'&&p.type!=='religious'?['akGamingPermit']:r.code==='NV'&&p.type!=='religious'?['nvRelatedOnly','nvNamedBeneficiary','nvAlumniOnly']:r.code==='KS'?['ksCommunityFoundation','ksLicensedCenter']:r.code==='KY'?['kyMemberOnly','kyStudentPta']:r.code==='VA'?['vaMembersOnly','vaRegisteredAffiliate','vaLocalOnly','vaLocalCosts']:r.code==='PA'&&(p.base==='PA'||p.operations.includes('PA'))?['paTaxExemption',...(p.type==='religious'?['religion990']:[])]:[];
 const optional=extra.map(k=>choices(`answer-${k}`,QUESTIONS[k][0],YES_NO,{[`answer-${k}`]:p.answers[k]||'unknown'},QUESTIONS[k][1])).join('')+(r.code==='PA'&&p.answers.paTaxExemption==='yes'&&p.type!=='religious'?money('answer-paProgramRevenue',MONEY_FACTS.paProgramRevenue[0],p.answers.paProgramRevenue,MONEY_FACTS.paProgramRevenue[1],'data-answer-key="paProgramRevenue"'):'');
 const online=p.online==='yes'?`<div class="field"><label for="onlineMethod">How can donors complete gifts online?</label><select id="onlineMethod" name="onlineMethod">${[['unknown','Not sure'],['checkout','Donation checkout or linked payment page'],['offline','Website asks donors to mail a gift or call'],['daf','A separate DAF charity receives the gift'],['platform','Fundraising platform or crowdfunding']].map(([v,t])=>option(v,t,p.onlineMethod||'unknown')).join('')}</select><p class="hint">A payment processor does not take over your registration duties. This describes your online method; direct appeals remain separate.</p></div><div class="field"><label for="thirdPartyAppeal">Who authorized outside online appeals?</label><select id="thirdPartyAppeal" name="thirdPartyAppeal">${[['unknown','Not sure / not applicable'],['authorized','Our organization authorized them'],['independent','Independent appeals without our involvement'],['no','No outside appeals']].map(([v,t])=>option(v,t,p.thirdPartyAppeal||'unknown')).join('')}</select></div>`:'';
 const advice=clientText(r.status==='outside'?stateExplanation(r,prepareProfile(p)):r.why);
 const relevantSteps=(r.nextSteps||[]).filter(step=>!/Public documents|Prepare the initial filing|Wait for required/.test(step.title));
 return `<details class="connections"><summary>Why this result and what to do</summary><p>${esc(advice)}</p><p>${esc(r.status==='outside'?'Add actual activity above to assess an exemption or registration route here.':r.action)}</p>${relevantSteps.map(step=>`<p><strong>${esc(step.title)}.</strong> ${esc(step.text)}</p>`).join('')}<a class="source-link" href="${esc(r.sources.at(-1)?.url||r.sources[0]?.url)}" target="_blank" rel="noopener noreferrer">Official ${esc(r.name)} guidance ↗</a></details>${grant||optional||online?`<details class="connections"><summary>Other fundraising or exemption details (optional)</summary>${grant}${optional}${online}</details>`:''}`;
}
function openEditor(code=''){stateEditMode=false;editingState=typeof code==='string'?code:'';editor=structuredClone(profile);$('editTitle').textContent='Change your answers';$('editError').hidden=true;$('editFields').innerHTML=editorMarkup(editor);$('editDialog').showModal();if(editingState)$('editFields').querySelector('.eligibility-fields input')?.focus();}
function openStateEditor(code){if(!STATES.some(s=>s.code===code))return;hideStateTip();editingState=code;stateEditMode=true;editor=structuredClone(profile);$('editTitle').textContent=`Update ${STATES.find(s=>s.code===code).name}`;$('editError').hidden=true;$('editFields').innerHTML=editorMarkup(editor);$('editDialog').showModal();}
function closeEditor(){const code=editingState;$('editDialog').close();editor=null;editingState='';stateEditMode=false;const anchor=$('report').querySelector(`[data-edit-state="${code}"]`);(anchor||$('editBtn')).focus();}
function applyEditor(){
 const errors=inputErrors(editor);if(errors.length){showErrors('editError',errors);return;}
 profile=editor;$('editDialog').close();editor=null;editingState='';stateEditMode=false;createReport();$('reportNotice').textContent='Results updated from your answers.';
}
function sync(e){
 const el=e.target,p=editor||profile;
 const value=el.dataset.numeric!==undefined||el.type==='number'?normalizeNumeric(el.value):el.value;
 if(el.dataset.grantKind){p.grantSources??=[];p.grantSources=el.checked?[...new Set([...p.grantSources,el.dataset.grantKind])]:p.grantSources.filter(k=>k!==el.dataset.grantKind);return;}
 if(editor&&el.dataset.activityKey){changeStateActivity(p,el.dataset.activityKey,el.checked);$('editFields').innerHTML=editorMarkup(p);$('editFields').querySelector(`[data-activity-key="${el.dataset.activityKey}"]`)?.focus();return;}
 if(el.dataset.giftState){p.receipts[el.dataset.giftState]??={};p.receipts[el.dataset.giftState][el.dataset.giftKey]=value;return;}
 if(el.dataset.answerKey||el.name?.startsWith('answer-')){const key=el.dataset.answerKey||el.name.slice(7);p.answers[key]=value;if(key==='solicitor')p.solicitor=value;return;}
 if(el.dataset.stateKey){const key=el.dataset.stateKey;if(el.checked){if(!p[key].includes(el.value))p[key].push(el.value);}else p[key]=p[key].filter(c=>c!==el.value);const count=(editor?$('editFields'):$('formPanel')).querySelector(`[data-state-selection-count="${key}"]`);if(count)count.textContent=`${p[key].length} of ${STATES.length} selected`;if(key==='donorStates'){if(!el.checked)delete p.receipts[el.value];$('giftFields').innerHTML=giftMarkup(p);}if(key==='target'&&el.value==='LA')$('solicitorQuestions').innerHTML=solicitorMarkup(p);return;}
 if(!el.name)return;
 p[el.name]=value;
 if(el.name==='solicitor')delete p.answers.solicitor;
 if(el.name==='type')p.answers={};
 if(el.name==='outsideGifts'&&el.value==='no'){p.donorStates=p.donorStates.filter(c=>c===p.base);p.receipts=Object.fromEntries(Object.entries(p.receipts).filter(([c])=>c===p.base));}
 if(el.name==='reach'){
  if(el.value==='none'){p.target=[];p.online='no';}
  if(el.value==='grants')p.online='no';
 }
 // Rebuild only when the visible questions change, not for ordinary typing.
 if(['reach','base','outsideGifts','type'].includes(el.name)){
  const open=(editor?$('editFields'):$('formPanel')).querySelector('.connections')?.open;
  (editor?$('editFields'):$('formPanel')).innerHTML=editor?editorMarkup(p):formMarkup(p);
  if(open)(editor?$('editFields'):$('formPanel')).querySelector('.connections').open=true;
  (editor?$('editFields'):$('formPanel')).querySelector(`[name="${el.name}"]${el.type==='radio'?`:checked`:''}`)?.focus();
 }
}
document.addEventListener('change',sync);
// Capture numeric edits immediately, including an Update click before blur.
document.addEventListener('input',e=>{if(e.target.type==='number'||e.target.dataset.numeric!==undefined)sync(e);});
document.addEventListener('focusout',e=>{if(e.target.dataset?.numeric!==undefined){e.target.value=formatNumeric(e.target.value);sync(e);}});
function bulkStates(key,action){
 if(!['target','donorStates','operations'].includes(key)||!['all','clear'].includes(action))return;
 const p=editor||profile,root=editor?$('editFields'):$('formPanel'),open=root.querySelector('.connections')?.open;
 p[key]=action==='all'?STATES.map(s=>s.code):[];
 if(key==='donorStates'){if(action==='clear')p.receipts={};else if(p.donorStates.some(c=>c!==p.base))p.outsideGifts='yes';}
 root.innerHTML=editor?editorMarkup(p):formMarkup(p);
 if(open)root.querySelector('.connections').open=true;
 root.querySelector(`[data-bulk-state="${key}"][data-state-action="${action}"]`)?.focus();
}
document.addEventListener('click',e=>{const button=e.target.closest?.('[data-bulk-state]');if(button?.dataset.bulkState)bulkStates(button.dataset.bulkState,button.dataset.stateAction);});
document.addEventListener('click',e=>{const edit=e.target.closest?.('[data-edit-state]')?.dataset.editState;if(edit)openStateEditor(edit);const code=e.target.closest?.('[data-review-state]')?.dataset.reviewState;if(code)openEditor(code);if(editor&&e.target.closest?.('[data-edit-all]')){editingState='';stateEditMode=false;$('editTitle').textContent='Change your answers';$('editFields').innerHTML=editorMarkup(editor);$('editFields').querySelector('[name="type"]')?.focus();}});
let tooltipAnchor=null,tooltipPinned=false;
function hideStateTip(){if(tooltipAnchor)tooltipAnchor.removeAttribute('aria-describedby');tooltipAnchor=null;tooltipPinned=false;$('stateTooltip').hidden=true;}
function showStateTip(anchor,pinned=false){
 if(editor)return;
 const r=report?.results.find(r=>r.code===anchor.dataset.explainState);if(!r)return;
 hideStateTip();tooltipAnchor=anchor;tooltipPinned=pinned;
 const facts=prepareProfile(profile),signal=onlineGiftSignal(r.code,facts);
 const excluded=r.status==='exemption'&&!r.discretionaryRequest&&['none','optional'].includes(r.filing);
 const tip=$('stateTooltip'),explanation=signal?`${signal.why} ${excluded?'Your answers support an exclusion; the test alone does not require registration.':'A qualifying exemption can still apply.'}`:stateExplanation(r,facts);tip.textContent=explanation.startsWith(r.name)?explanation:`${r.name}: ${explanation}`;tip.hidden=false;anchor.setAttribute('aria-describedby','stateTooltip');
 const rect=anchor.getBoundingClientRect(),width=tip.getBoundingClientRect().width,height=tip.getBoundingClientRect().height;
 tip.style.left=`${Math.max(10,Math.min(rect.left,window.innerWidth-width-10))}px`;
 tip.style.top=`${rect.bottom+height+10<window.innerHeight?rect.bottom+8:Math.max(10,rect.top-height-8)}px`;
}
// Touch must reach the button's native click without creating a hover overlay.
const canHover=()=>!window.matchMedia||window.matchMedia('(hover: hover) and (pointer: fine)').matches;
document.addEventListener('pointerover',e=>{if(e.pointerType==='touch'||!canHover())return;const anchor=e.target.closest?.('[data-explain-state]');if(anchor&&!tooltipPinned)showStateTip(anchor);});
document.addEventListener('pointerout',e=>{if(!tooltipPinned&&tooltipAnchor&&!tooltipAnchor.contains(e.relatedTarget)&&!$('stateTooltip').contains(e.relatedTarget))hideStateTip();});
document.addEventListener('focusin',e=>{if(!canHover())return;const anchor=e.target.closest?.('[data-explain-state]');if(anchor)showStateTip(anchor);});
document.addEventListener('focusout',()=>{if(!tooltipPinned)hideStateTip();});
document.addEventListener('click',e=>{const anchor=e.target.closest?.('[data-explain-state]');if(anchor&&!editor){if(tooltipPinned&&tooltipAnchor===anchor)hideStateTip();else showStateTip(anchor,true);}else hideStateTip();});
document.addEventListener('keydown',e=>{if(e.key==='Escape')hideStateTip();});
document.addEventListener('scroll',hideStateTip,true);
$('assessment').addEventListener('submit',e=>{e.preventDefault();createReport();});
$('editAssessment').addEventListener('submit',e=>{e.preventDefault();applyEditor();});
$('cancelEdit').onclick=closeEditor;
 $('auroraHandoff').addEventListener('submit',connectAurora);
 $('cancelHandoff').onclick=()=>$('auroraDialog').close();
$('editDialog').addEventListener('cancel',e=>{e.preventDefault();closeEditor();});
function showSource(){const s=STATES.find(s=>s.code===$('sourceState').value);$('sourceList').innerHTML=s?`<div class="source-entry"><strong>${esc(s.name)}</strong>${s.sources.map(source=>`<a class="source-link" href="${esc(source.url)}" target="_blank" rel="noopener noreferrer">${esc(source.title)} ↗</a>`).join('')}<p class="hint">Reviewed ${esc(s.reviewed)}. Requirements can change.</p></div>`:'';}
$('sourcesBtn').onclick=()=>{$('sourceState').innerHTML=STATES.map(s=>option(s.code,s.name,profile.base||'AL')).join('');showSource();$('sourcesDialog').showModal();};
$('sourceState').onchange=showSource;$('closeDialog').onclick=()=>$('sourcesDialog').close();
// Uses only the same essential answers as the visible questionnaire.
if(document.modelContext?.registerTool){
 document.modelContext.registerTool({name:'assess_charity_requirements',description:'Show initial 501(c)(3) registration screening from actual reported activity. All states remain visible; no hypothetical nationwide appeals are invented. No filings are submitted.',inputSchema:{type:'object',properties:{profile:{type:'object',properties:{type:{type:'string'},base:{type:'string'},grantSources:{type:'array',items:{enum:['government','charity','other501c','privateFoundation','corporate','other']}},onlineMethod:{enum:['unknown','checkout','offline','daf','platform']},thirdPartyAppeal:{enum:['unknown','authorized','independent','no']},reach:{enum:['home','selected','national','none','grants']},online:{enum:['yes','no','unknown']},target:{type:'array',items:{type:'string'}},operations:{type:'array',items:{type:'string'}},donorStates:{type:'array',items:{type:'string'}},incorporation:{type:'string'},solicitor:{enum:['yes','no','unknown']},outsideGifts:{enum:['yes','no','unknown']},fiscalActual:{type:['string','number']},receipts:{type:'object',additionalProperties:{type:'object',properties:{amount:{type:['string','number']},count:{type:['string','number']},donors:{type:['string','number']},intended:{type:['string','number']},nationalTotal:{type:['string','number']},origin:{enum:['unknown','website','unsolicited','grants','mixed']},period:{enum:['unknown','completedFiscal','current']},repeated:{enum:['unknown','yes','no']}},additionalProperties:false}},answers:{type:'object',properties:Object.fromEntries([...new Set([...Object.keys(QUESTIONS),...Object.keys(ROLE_FACTS),...Object.keys(MONEY_FACTS)])].map(k=>[k,MONEY_FACTS[k]?{type:['string','number']}:{enum:['yes','no','unknown']}])),additionalProperties:false}},additionalProperties:false}},required:['profile']},execute:async({profile:next})=>{
  if(editor)return {content:[{type:'text',text:'Finish or cancel the answer editor first.'}],isError:true};
  const candidate={...initial()};for(const k of Object.keys(candidate))if(Object.hasOwn(next,k))candidate[k]=next[k];
  let errors;try{errors=inputErrors(candidate);}catch{return {content:[{type:'text',text:'Use the answers and state lists from the questionnaire.'}],isError:true};}
  if(errors.length)return {content:[{type:'text',text:errors.join(' ')}],isError:true};
  profile=candidate;createReport();return {content:[{type:'text',text:JSON.stringify({scope:'Current answers; unreported activity is shown in the first column without granting statutory clearance',displayedCounts:{noRegistrationIndicated:groups.notRequired.length+groups.notAssessed.length,potentialExemption:groups.potentialExemption.length,mayRequired:groups.mayRequired.length},classificationCounts:Object.fromEntries(Object.entries(groups).map(([k,v])=>[k,v.length])),reviewDate:REVIEW_DATE})}]};
 }});
}
render();

