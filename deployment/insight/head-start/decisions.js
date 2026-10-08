import {QUESTIONS,ELIGIBILITY_AMOUNTS} from './eligibility.js?v=0.18.0.3';
import {NO_GENERAL_STATES,STATES} from './rules.js?v=0.18.0.3';

// Present initial organization registration without changing the engine.
// Keep exemption-based relief distinct from no requirement or no reported activity.
// This is a presentation projection; raw classifications are never changed.
const supportedExemption=r=>r.status==='exemption'&&!r.discretionaryRequest||r.status==='none'&&r.ruleIds.some(id=>/\.(501c3|grant-only-qualified|return-not-required)$/.test(id));
export function registrationTable(assessment,profile,options={}){
 const groups={notRequired:[],potentialExemption:[],mayRequired:[],notAssessed:[]};
 for(const r of assessment.results){
  const last=r.ruleIds.at(-1)||'';
  let group='mayRequired',exemptionEvidence=supportedExemption(r)?'answers':null;
  if(r.status==='outside'||r.deferred){
   const mode=STATES.find(s=>s.code===r.code)?.mode;
   const ordinaryArizona=r.code==='AZ'&&!['veterans','other','unknown'].includes(profile.type)&&profile.specialCategory!=='yes';
   // Source-supported general-program findings do not require invented appeals.
   // Keep special-purpose and trust routes outside this general conclusion.
   const general=NO_GENERAL_STATES.includes(r.code)&&!(r.code==='IA'&&profile.type==='privateFoundation')||mode==='utah'||ordinaryArizona;
   group=options.includeGeneralFramework&&general&&!r.deferred?'notRequired':'notAssessed';
  }
  else if(r.status==='none')group=exemptionEvidence?'potentialExemption':'notRequired';
  // In no-general-program states, this engine warning concerns separate
  // professional provider/campaign filings, excluded from the table's scope.
  else if(NO_GENERAL_STATES.includes(r.code)&&/\.paid-fundraising$/.test(last))group='notRequired';
  else if(r.status==='exemption')group='potentialExemption';
  else if(r.status==='review'&&!r.nexusPending&&r.registrationTrigger!==null&&(
   /\.(small-missing-facts|institution-missing-facts|religious-missing-facts|grant-missing-facts|unautomated-small-route|small-procedure-review)$/.test(last)||
   /\.category-review$/.test(last)&&r.label==='Verify institutional exemption'&&!['unknown','other','privateFoundation'].includes(profile.type)
  ))group='potentialExemption';
  groups[group].push(exemptionEvidence?{...r,exemptionEvidence}:r);
 }
 for(const rows of Object.values(groups))rows.sort((a,b)=>a.name.localeCompare(b.name,'en'));
 return groups;
}

// Short explanations reflect the actual result, never a fictional campaign.
export function stateExplanation(r,p){
 const mode=STATES.find(s=>s.code===r.code)?.mode;
 const last=r.ruleIds.at(-1)||'';
 if(NO_GENERAL_STATES.includes(r.code)&&!r.ruleIds.some(id=>/trust/.test(id)))return `${r.name} has no general charitable solicitation registration requirement. Separate entity, tax or professional fundraiser duties can still apply.`;
 if(r.code==='UT')return 'Utah no longer requires a separate charity solicitation license. Entity and other reporting duties are separate.';
 if(r.code==='MO'&&r.status!=='outside'&&!r.deferred)return 'Missouri does not require recognized 501(c)(3) organizations to register with its charity program. An agency confirmation letter is optional.';
 if(r.code==='AZ'&&!['veterans','other','unknown'].includes(p.type)&&p.specialCategory!=='yes')return 'Arizona has no general charity solicitation registration program. Fundraising for veterans organizations has separate rules.';
 if(r.code==='CA'){
  if(r.status==='exemption'&&['none','optional'].includes(r.filing))return 'Your answers support a potential institutional exemption. Qualifying institutions are exempt by law; Head Start has not verified your documents or state approval. A written state review is available if needed.';
  if(r.status==='outside'&&p.online==='yes'&&p.base!=='CA')return 'A donation button alone does not trigger registration for an out-of-state charity. California activity or substantial ongoing donations can change the result.';
  if(p.type==='religious')return 'California excludes qualifying primary religious institutions by law. An outside gift does not automatically remove that exclusion; confirm the organization’s category.';
  if(r.nexusPending)return 'An outside gift is not a universal $25,000 registration threshold. California’s rules depend on the actual fundraising, business or charitable assets connection.';
 }
 if(r.status==='outside'||r.deferred)return `You haven’t reported fundraising, donor gifts or operations in ${r.name}. Select ${r.name} to add or change these details; this is not clearance for future activity.`;
 if(r.code==='PA'&&p.type==='religious'){
  if(last==='PA.religious-exclusion')return 'Your answers support a potential religious exemption. No solicitation registration is indicated while you qualify; agency confirmation is optional. Head Start has not verified your documents or state approval.';
  if(last==='PA.religious-missing-facts')return 'Religious institutions can be excluded. Confirm the primary support sources and that net income does not benefit private individuals.';
 }
 if(r.nexusPending&&r.status!=='exemption')return 'A gift or online contact was reported, but a registration trigger has not been established. Confirm the relevant state connection and any exclusion.';
 if(r.status==='exemption'){
  if(r.discretionaryRequest)return 'You can request a discretionary waiver. Registration relief depends on the agency approving it.';
  if(r.approvalRequired)return 'Your answers support an exemption application. Agency approval is required before you rely on it; Head Start has not verified that approval.';
  if(r.filing==='verify')return 'Your answers support potential exemption eligibility. The category-specific filing procedure still needs confirmation; do not assume no filing or a mandatory claim.';
  if(['none','optional'].includes(r.filing))return `Your answers support a potential exemption with no registration indicated while you qualify.${r.filing==='optional'?' Agency confirmation is optional.':' Keep evidence of eligibility.'} Head Start has not verified your documents or state approval.`;
  return `Your answers support an exemption filing route. ${r.filing==='annual'?'An annual exemption filing is indicated.':'Complete the required exemption claim before relying on it.'}`;
 }
 if(r.status==='none')return 'No registration requirement is indicated for the activity you reported. Reassess if fundraising, gifts or other state connections change.';
 if(r.status==='required')return 'The reported state activity indicates registration, and your answers do not establish applicable relief. Confirm the filing with the state or a compliance service provider.';
 if(/small-missing-facts/.test(last))return 'A small-organization route may apply. The amount, required year or compensation facts still need confirmation.';
 if(/institution-missing-facts|religious-missing-facts/.test(last))return 'Your nonprofit category has a possible exclusion. Confirm the relevant eligibility facts; this is not an instruction to apply automatically.';
 if(mode==='louisiana')return 'Louisiana’s charity program depends on professional solicitation. Confirm whether an outside paid solicitor is involved and any applicable exclusion.';
 return 'An applicable registration condition or exclusion still needs confirmation. Review the state-specific facts before deciding which filing is needed.';
}

// Present the engine's decision without upgrading its certainty or changing a rule.
const amounts={
 fiscalActual:'Most recent fiscal year nationwide contributions',
 fiscalExpected:'Current fiscal year expected nationwide contributions',
 fiscalPrior:'Nationwide contributions one fiscal year earlier',
 fiscalPriorTwo:'Nationwide contributions two fiscal years earlier',
 calendarPrevious:'Previous calendar year nationwide contributions',
 calendarActual:'Current calendar year contributions received',
 calendarExpected:'Expected full calendar year contributions',
 coFiscalGross:'Adjusted gross revenue received this fiscal year',
 coExpectedGross:'Expected full fiscal year adjusted gross revenue',
 nyFiscalActual:'New York contributions received this fiscal year',
 nyFiscalExpected:'Expected full fiscal year New York contributions'
};
for(const [key,[label]]of Object.entries(ELIGIBILITY_AMOUNTS))amounts[key]=label;
const conditions={
 allUnpaid:['allUnpaid'],noPrivateBenefit:['privateBenefit'],
 noSolicitor:['solicitor'],noProfessional:['solicitor','consultant'],
 noExternal:['solicitor','consultant','coVenturer'],
 noPaidSolicitation:['paidStaff','solicitor'],unpaidFundraising:['paidStaff','solicitor']
};
const factLabels={
 allUnpaid:'Whether all organization functions are performed without compensation',
 privateBenefit:'Whether officers or members receive income from charitable funds',
 solicitor:'Whether a professional solicitor is hired',
 consultant:'Whether fundraising counsel or a consultant is hired',
 coVenturer:'Whether a commercial co-venturer is used',
 paidStaff:'Whether paid employees solicit contributions'
};
export function describeDecision(r,p){
 const last=r.ruleIds.at(-1)||'';
 let missing=[];
 if(/missing-facts$/.test(last)){
  missing=[...(r.questions||[])];
  for(const input of r.inputs||[]){
   if(amounts[input]){
    if(p[input]===undefined||p[input]===null||p[input]==='')missing.push(amounts[input]);
   }else for(const key of conditions[input]||[input]){
    if(!['yes','no'].includes(p[key])&&(factLabels[key]||QUESTIONS[key]))missing.push(factLabels[key]||QUESTIONS[key][0]);
   }
  }
 }
 missing=[...new Set(missing)];
 const registration=r.discretionaryRequest?'A waiver request is available. Registration relief depends on the Director’s decision.':r.status==='review'&&r.registrationTrigger===true&&/small-missing-facts|institution-missing-facts|grant-missing-facts|condition-not-established|unautomated-small-route/.test(last)?'A registration trigger applies. Confirm the possible exemption below before deciding which filing to make.':
  r.status==='required'?'Yes — registration is indicated by the supplied facts.':
  r.status==='none'?'No registration is indicated for the stated activity.':
  r.status==='outside'?'Not assessed — no registration conclusion.':
  r.status==='exemption'&&['none','optional'].includes(r.filing)?'No registration indicated while this exemption applies.':
  r.status==='exemption'&&['application','annual','simplified'].includes(r.filing)?'An exemption filing route is available. Complete that filing before relying on it.':
  r.status==='exemption'?'Potential exemption — filing requirements still need confirmation.':'Not determined yet — see the specific reason below.';
 const exemption=r.discretionaryRequest?'You can request a discretionary waiver; approval has not been established.':r.status==='required'&&r.partialExemptions?.length?r.partialExemptions.join(' '):r.status==='exemption'?({
  none:'Eligibility supported by your answers; no exemption filing indicated.',
  optional:'Eligibility supported by your answers; agency confirmation is optional.',
  application:'Eligibility supported by your answers; submit the exemption claim.',
  annual:'Eligibility supported by your answers; submit an exemption application each year.',
  simplified:'Eligibility supported by your answers; annual small charity paperwork is required.',
  verify:'Potential eligibility identified; the filing procedure is not verified.'
 }[r.filing]||'Confirm the applicable filing procedure.'):
  r.status==='review'?'Eligibility or filing duties remain unresolved.':
  r.status==='outside'?'Not assessed.':
  r.status==='required'?'No qualifying exemption has been established by this screening.':
  r.filing==='optional'?'Agency confirmation is optional.':'No exemption filing is indicated by this result.';
 let blocker='';
 if(r.status==='review'){
  if(/missing-facts$/.test(last))blocker='Missing answers';
  else if(/category-review/.test(last)&&(['unknown','other','privateFoundation'].includes(p.type)||p.specialCategory==='yes'))blocker='Organization category needs clarification';
  else if(/research-gap|unautomated-small-route|category-review/.test(last))blocker='Rule coverage needs verification';
  else if(/existing-registration/.test(last))blocker='Existing registration or withdrawal duties';
  else if(/nexus-review/.test(last))blocker='Fundraising connection is unresolved';
  else if(/condition-not-established/.test(last))blocker='Exemption conditions were not established';
  else blocker='State-specific interpretation or filing review';
 }else if(r.status==='exemption'&&r.filing==='verify')blocker='Exemption filing procedure needs verification';
 return {registration,exemption,blocker,missing};
}
