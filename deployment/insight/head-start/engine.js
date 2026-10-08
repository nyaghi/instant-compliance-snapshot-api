import {STATES,SMALL,LABELS,VERSION,REVIEW_DATE} from './rules.js?v=0.18.0.3';
import {institutionRoute,QUESTIONS,FILING_LABELS,SMALL_FILINGS,ELIGIBILITY_AMOUNTS,VERIFIED_CATEGORY_STATES} from './eligibility.js?v=0.18.0.3';
import {nextSteps} from './guidance.js?v=0.18.0.3';
export const number=(v)=> v===null||v===undefined||v===''?null:(Number.isFinite(Number(v))&&Number(v)>=0?Number(v):null);
const yes=v=>v==='yes';
const codes=new Set(STATES.map(s=>s.code));
export function validate(p){
 const errors=[];
 if(!p||typeof p!=='object')return ['An organization profile is required.'];
 if(!['charity','religious','school','university','hospital','foundation','educationalFoundation','hospitalFoundation','privateFoundation','veterans','membership','other','unknown'].includes(p.type))errors.push('Choose an organization type.');
 if(!codes.has(p.base))errors.push('Choose the principal office state.');
 if(p.taxStatus!==undefined&&p.taxStatus!=='recognized501c3')errors.push('Head Start is for recognized 501(c)(3) nonprofits only.');
 if(p.homeOnly!==undefined&&!['yes','no','incidental','unknown','none','grants'].includes(p.homeOnly))errors.push('Choose a valid fundraising activity.');
 if(p.onlineMethod!==undefined&&!['unknown','checkout','offline','daf','platform'].includes(p.onlineMethod))errors.push('Choose a valid online donation method.');
 const grantKinds=['government','charity','other501c','privateFoundation','corporate','other'];
 if(p.grantSources!==undefined&&(!Array.isArray(p.grantSources)||p.grantSources.some(k=>!grantKinds.includes(k))))errors.push('Choose valid grantmaker types.');
 if(p.type==='privateFoundation'&&p.ksCommunityFoundation==='yes')errors.push('A private foundation conflicts with the publicly supported Kansas community-foundation category. Confirm the entity type.');
 if(['none','grants'].includes(p.homeOnly)&&p.online==='yes')errors.push('A public online donation request conflicts with no appeals or grant applications only. Update your fundraising activity.');
 if(p.grantsOnly==='yes'&&p.online==='yes')errors.push('Grant applications only conflicts with a public online donation request. Update that answer.');
 if(p.homeOnly==='none'&&(p.target||[]).length)errors.push('No donation requests conflicts with targeted appeals. Clear those states or update your activity.');
 if(p.homeOnly==='none'&&Object.values(p.receipts||{}).some(row=>row.emailAppeals==='yes'))errors.push('No donation requests conflicts with follow-up fundraising emails. Update your activity.');
 if(p.thirdPartyAppeal!==undefined&&!['unknown','authorized','independent','no'].includes(p.thirdPartyAppeal))errors.push('Choose a valid third-party fundraising answer.');
 for(const key of ['fiscalYearEnd','firstAppealDate','firstAssetDate'])if(p[key]!==undefined&&p[key]!==''&&(!/^\d{4}-\d{2}-\d{2}$/.test(p[key])||!Number.isFinite(Date.parse(p[key]))||new Date(p[key]).toISOString().slice(0,10)!==p[key]))errors.push('Use valid calendar dates for filing and activity dates.');
 for(const key of ['target','donorStates','operations','registered','bankStates'])if(p[key]!==undefined&&(!Array.isArray(p[key])||p[key].some(c=>!codes.has(c))))errors.push(`Invalid states in ${key}.`);
 for(const key of ['annualEstimate','fiscalActual','fiscalExpected','fiscalPrior','fiscalPriorTwo','nyFiscalActual','nyFiscalExpected','coFiscalGross','coExpectedGross','calendarPrevious','calendarActual','calendarExpected','grantAmount',...Object.keys(ELIGIBILITY_AMOUNTS)])if(p[key]!==undefined&&p[key]!==''&&p[key]!==null&&(number(p[key])===null||(/Donors|Persons/.test(key)&&!Number.isInteger(Number(p[key])))))errors.push('Use nonnegative amounts and whole person counts, or leave unknown values blank.');
 for(const [code,row]of Object.entries(p.receipts||{})){if(!codes.has(code)){errors.push('Invalid receipt state.');continue;}if(!row||typeof row!=='object'){errors.push(`${code}: receipt details must be an object.`);continue;}if(row.origin!==undefined&&!['unknown','website','unsolicited','grants','mixed'].includes(row.origin))errors.push(`${code}: choose a valid gift source.`);for(const key of ['emailAppeals','locationKnown','repeated'])if(row[key]!==undefined&&!['unknown','yes','no'].includes(row[key]))errors.push(`${code}: choose Yes, No or Not sure for contact facts.`);for(const key of ['amount','count','donors','intended']){const v=row[key];if(v!==undefined&&v!==''&&v!==null&&(number(v)===null||(['count','donors'].includes(key)&&!Number.isInteger(Number(v)))))errors.push(`${code}: use nonnegative amounts and whole contribution or donor counts.`);}}
 if(p.allUnpaid==='yes'&&['paidStaff','solicitor','consultant','coVenturer'].some(k=>p[k]==='yes'))errors.push('All functions unpaid conflicts with a paid fundraising role.');
 const national=number(p.fiscalActual);
 if(national!==null){const onlineTotal=Object.values(p.receipts||{}).filter(row=>row.period===undefined||row.period==='completedFiscal').reduce((sum,row)=>sum+(number(row.amount)||0),0);if(onlineTotal>national)errors.push('Known state online receipts exceed the national fiscal contribution total. Use matching periods and contribution definitions.');}
 if(p.onlineReach!==undefined&&!['unknown','local','public','incidental','selected','nationwide'].includes(p.onlineReach))errors.push('Choose a valid online fundraising reach.');
 if(p.homeOnly==='incidental'&&(p.target||[]).some(c=>c!==p.base))errors.push('Occasional outside gifts conflict with targeted fundraising in another state. Choose active fundraising in other states.');
 if(p.homeOnly==='yes'){
  if(p.online==='yes'&&(p.onlineNationwide==='yes'||['incidental','selected','nationwide'].includes(p.onlineReach)))errors.push('Online fundraising outside your home state conflicts with your local fundraising answer. Update the fundraising reach answer.');
  if((p.donorStates||[]).some(c=>c!==p.base))errors.push('Fundraising limited to the home state conflicts with donors in another state.');
  if((p.target||[]).some(c=>c!==p.base))errors.push('Fundraising limited to the home state conflicts with an out of state targeted appeal.');
  if(Object.entries(p.receipts||{}).some(([c,r])=>c!==p.base&&['amount','count','donors','intended'].some(k=>number(r[k])>0)))errors.push('Fundraising limited to the home state conflicts with out of state receipts or intended receipts.');
 }
 return errors;
}
function conditions(p){
 const notPaid=(key)=>p[key]==='no'?true:p[key]==='yes'?false:null;
 const combine=a=>a.includes(false)?false:a.includes(null)?null:true;
 return {
 allUnpaid:p.allUnpaid==='yes'?true:p.allUnpaid==='no'?false:null,
 noPrivateBenefit:p.privateBenefit==='no'?true:p.privateBenefit==='yes'?false:null,
 noSolicitor:notPaid('solicitor'),
 noProfessional:combine(['solicitor','consultant'].map(notPaid)),
 scCompensationLimit:p.scCompensationLimit==='yes'?true:p.scCompensationLimit==='no'?false:null,
 noExternal:combine(['solicitor','consultant','coVenturer'].map(notPaid)),
 noPaidSolicitation:combine(['paidStaff','solicitor'].map(notPaid)),
 unpaidFundraising:combine(['paidStaff','solicitor'].map(notPaid))
 };
}
function totals(p,period,customFields){
 const fields=customFields|| (period==='coGross'?['coFiscalGross','coExpectedGross']:['threeFiscal','threeFiscalAverage'].includes(period)?['fiscalActual','fiscalPrior','fiscalPriorTwo']:period==='nyFiscal'?['nyFiscalActual','nyFiscalExpected']:period==='lastFiscal'?['fiscalActual']:period==='calendarCurrent'?['calendarActual','calendarExpected']:period==='calendar'?['calendarPrevious','calendarActual','calendarExpected']:['fiscalActual','fiscalExpected']);
 const vals=fields.map(k=>number(p[k]));
 return {unknown:vals.includes(null),max:period==='threeFiscalAverage'?vals.reduce((sum,v)=>sum+(v||0),0)/3:Math.max(...vals.filter(x=>x!==null),0),vals,fields};
}
function screenSmall(s,p,paid,r,set,physical,ops,nexus){
    const rule=SMALL[s.code],youngCT=s.code==='CT'&&p.ctYoungOrganization==='yes',t=totals(p,rule.period,youngCT?['ctAssessmentYearOne','ctAssessmentYearTwo','ctAssessmentYearThree']:rule.fields),within=rule.period==='threeFiscal'?t.vals.filter(v=>v!==null&&v<rule.amount).length>=2:rule.inclusive?t.max<=rule.amount:t.max<rule.amount;
    const vals=rule.conditions.map(k=>Object.hasOwn(paid,k)?paid[k]:p[k]==='yes'?true:p[k]==='no'?false:k==='ctNoPrimaryPaidSolicitation'&&paid.noPaidSolicitation===true?true:null);
    r.inputs.push(...t.fields);
    if(s.code==='SC'&&t.unknown){set('review','Enter fiscal worldwide gross revenue to choose between South Carolina’s $10,000 route and its $25,000 route. Compensation questions are needed only for the higher route.','Enter the two gross revenue figures below.','SC.small-missing-facts');return;}
    if(s.code!=='SC'||t.max>10000&&t.max<=25000)r.inputs.push(...rule.conditions);
    if(s.code==='CT'&&(t.unknown||p.ctYoungOrganization==='yes')){
     r.inputs.push('ctYoungOrganization');
     if(p.ctYoungOrganization==='yes'){r.inputs.push('ctGoodFaithEstimates');vals.push(p.ctGoodFaithEstimates==='yes'?true:p.ctGoodFaithEstimates==='no'?false:null);r.notes.push('For years without history, Connecticut permits documented good-faith annual estimates. Keep completed-year actuals separate from projected years; estimates still require a CPC-54 claim.');}
    }
    if(s.code==='SC'&&!t.unknown&&t.max<=10000){
     set('exemption','Fiscal gross revenue is no more than $10,000. South Carolina’s section 33-56-50(B)(2) route applies regardless of professional fundraising.','Submit the annual exemption application; professional providers have their own duties.','SC.small-10000');r.filing='annual';r.filingLabel=FILING_LABELS.annual;r.label=r.filingLabel;return;
    }
    if(within&&!t.unknown&&!vals.includes(false)&&!vals.includes(null)){
     set('exemption',`The supplied ${['calendar','calendarCurrent'].includes(rule.period)?'calendar year':'fiscal year'} national contribution totals and compensation facts satisfy the prototype’s small organization screening criteria.`,rule.action,`${s.code}.small-candidate`);
     r.filing=SMALL_FILINGS[s.code]||'verify';r.filingLabel=FILING_LABELS[r.filing];r.label=r.filingLabel;
     if(rule.approvalRequired)r.approvalRequired=true;
     if(rule.period==='threeFiscal')r.why='Worldwide contributions are below $50,000 in at least two of the last three fiscal years, and the stated compensation conditions support Connecticut’s small organization route.';
     if(youngCT)r.why='Two of the supplied three worldwide annual figures are below $50,000. You confirmed that years without history use documented good-faith estimates, and the compensation facts support Connecticut’s small route. Claim it using CPC-54.';
     if(rule.period==='threeFiscalAverage')r.why='The supplied three year average national contributions are below $25,000 and the paid fundraising facts support Hawaii’s small organization route, subject to its contribution definition.';
     if(s.code==='CO')r.why='The supplied actual and intended nationwide adjusted gross revenue is no more than $25,000, supporting Colorado’s small organization route. This is a revenue test, not a test of Colorado donations alone.';
     if(rule.fields)r.why=`The supplied ${s.code==='SC'?'fiscal worldwide gross revenue':s.code==='MI'?'adjusted nationwide contributions for any 12-month period':s.code==='OH'?'adjusted nationwide gross revenue for the immediately preceding fiscal year':['MD','NJ'].includes(s.code)?'state-defined nationwide fiscal contributions':'three preceding calendar years and current calendar-year contributions'} and eligibility facts meet ${s.name}’s small solicitation route.`;
     if(s.code==='NY'){
      r.why='The supplied New York contribution totals are below $25,000 and no professional fundraiser or fundraising counsel is reported. This screens Article 7-A only, not New York’s separate charitable assets regime.';
      r.filing='optional';r.filingLabel=FILING_LABELS.optional;r.label=r.filingLabel;r.action='No Article 7-A registration is indicated while contributions remain below $25,000 and no fundraising professional is used. Schedule E confirmation is optional unless the Attorney General sends a failure-to-register notice. EPTL duties remain separate.';
      if(physical||ops.has('NY')){set('review','New York charitable assets or operations can require EPTL registration even when the solicitation dollar route may apply.','Review EPTL and Article 7-A separately before deciding that no filing is required.','NY.small-versus-assets');}
     }
     if(s.code==='FL')r.notes.push('If current fiscal year contributions reach $50,000, register within 30 days; the annual small charity application is not permanent clearance.');
     if(nexus.trigger===null)r.notes.push('A potential small organization route is shown, but online nexus still requires review.');
    }else if(s.code==='NY'&&t.max===25000){
     set('required','Exactly $25,000 does not satisfy Article 7-A’s less-than-$25,000 exemption. The statute and Attorney General’s section 91.3(b)(2) agree on this boundary.','Register for covered solicitation unless a different exemption applies. Assess EPTL separately.','NY.small-boundary-resolved');
    }else if((within||t.unknown)&&(t.unknown||vals.includes(null))&&!vals.includes(false)&&((rule.period==='threeFiscal')||t.max<rule.amount||within)){
     set('review','A small organization route may be available, but contribution periods or compensation facts are incomplete.','Complete the contribution totals and eligibility facts; then confirm the statutory definition and filing route.',`${s.code}.small-missing-facts`);
    }
    else if(nexus.trigger===true&&r.ruleIds.some(id=>/condition-not-established/.test(id))){set('required','A covered registration trigger applies, and the supplied facts establish neither the institutional route nor the small organization alternative.','Follow the linked registration process unless another documented statutory exemption applies.',`${s.code}.exemption-not-established`);r.filing=null;r.filingLabel=null;r.label=LABELS.required;}
}
function screenLimited(s,p,paid,r,set){
 const code=s.code;
 if(code==='NV'){
  r.inputs.push('nvPersonsSolicited','nvRelatedOnly','nvNamedBeneficiary','nvAlumniOnly');
  const persons=number(p.nvPersonsSolicited);
  if(persons!==null&&persons<15||['nvRelatedOnly','nvNamedBeneficiary','nvAlumniOnly'].some(k=>p[k]==='yes')){
   set('exemption','The supplied all-solicitation audience facts support an NRS 82A.110 route. People solicited are counted, not gifts or donors.','File Nevada’s declaration of exemption before solicitation and annually thereafter. Reassess if any other public appeal occurs.','NV.limited-solicitation');r.filing='annual';r.filingLabel=FILING_LABELS.annual;r.label=r.filingLabel;return true;
  }
  return false;
 }
 if(code==='CO'){
  r.inputs.push('coPersonsActual','noSolicitor');
  const persons=number(p.coPersonsActual);
  if(persons!==null&&persons<=10&&paid.noSolicitor===true){set('exemption','No more than ten persons contributed worldwide this fiscal year, and no contracted paid solicitor is reported. Colorado’s separate person-count exemption applies.','Retain the full worldwide contributor list and reassess as the count changes. This is not a Colorado online receipt safe harbor.','CO.limited-persons');r.filing='none';r.filingLabel=FILING_LABELS.none;r.label=r.filingLabel;return true;}
  return false;
 }
 if(code==='KS'){
  const fields=['ksPersonsActual','ksPersonsExpected'];
  const v=fields.map(k=>number(p[k]));
  if(v.some(x=>x!==null&&x<=100)&&!v.some(x=>x>100)){r.inputs.push(...fields);set('exemption','The supplied actual OR intended solicitation/receipt person count supports Kansas’s no-more-than-100-person route under section 17-1762(s). This is not an internet nexus threshold.','Retain the person-count evidence and reassess as activity changes. You may ask the Attorney General for confirmation.','KS.limited-persons');r.filing='optional';r.filingLabel=FILING_LABELS.optional;r.label=r.filingLabel;return true;}
  if(v.some(x=>x!==null&&x<=100)&&v.some(x=>x>100)){
   const t=totals(p,'fiscal');
   if(!t.unknown&&t.max<=10000&&paid.unpaidFundraising===true)return false;
   r.inputs.push(...fields);set('review','Actual and intended person counts fall on different sides of Kansas’s 100-person limit. The statute uses OR, so this mixed-period application needs interpretation.','Confirm the period and how the Attorney General applies section 17-1762(s) to these differing counts, or establish a separate dollar exemption.','KS.limited-persons-review');return true;
  }
  return false;
 }
 if(!['AK','ME'].includes(code))return false;
 const prefix=code.toLowerCase(),fields=[prefix+'Actual',prefix+'Expected',prefix+'DonorsActual',prefix+'DonorsExpected'];
 const [actual,intended,donors,expectedDonors]=fields.map(k=>number(p[k]));
 const ceiling=code==='AK'?5000:35000,count=code==='AK'?10:35;
 const conditionKeys=code==='AK'?['akNoPaidEmployeesBoard','noSolicitor']:['noSolicitor','noPrivateBenefit'];
 const values=conditionKeys.map(k=>Object.hasOwn(paid,k)?paid[k]:p[k]==='yes'?true:p[k]==='no'?false:null);
 r.inputs.push(...fields,...conditionKeys);
 if(values.includes(false)||code==='AK'&&(actual>ceiling||donors>count)||code==='ME'&&actual>ceiling&&donors>count){
  set('required','Actual contributions or contributor count exceed the statutory conversion limit, or the required compensation condition fails. The small exemption has not been established.','Use the linked registration process unless another documented statutory exemption applies.',`${code}.small-not-qualified`);r.filing=null;r.filingLabel=null;r.label=LABELS.required;return true;
 }
 if(code==='ME'&&(actual>=ceiling||donors>=count||intended>=ceiling||expectedDonors>=count)){
  set('review','Maine’s OR eligibility language and reaching/exceeding conversion clause need reconciliation at a boundary or when only one amount/count limb exceeds its limit.','Ask Maine’s licensing office about this specific amount/count transition. Do not assume registration or clearance from the other limb alone.','ME.small-boundary-review');return true;
 }
 if(actual!==null&&donors!==null&&!values.includes(null)&&((intended!==null&&intended<=ceiling)||(expectedDonors!==null&&expectedDonors<=count))){
  set('exemption',`Actual totals remain below the conversion limits and the intended dollar OR person-count test supports ${s.name}’s small route. This does not clear targeted appeals in other states.`,code==='AK'?'Alaska offers a one-time exemption notice. Retain the eligibility evidence; either actual limit being exceeded requires a new registration assessment.':'Retain the eligibility evidence. Maine repealed its exemption claim procedure; no exemption application is indicated. Reassess before actual totals reach a conversion boundary.',`${code}.small-candidate`);r.filing=code==='AK'?'optional':'none';r.filingLabel=FILING_LABELS[r.filing];r.label=r.filingLabel;
 }else{set('review','The small route needs the state-defined actual totals, intended dollars or persons, and compensation facts.','Answer the specific fields below; blank is not zero.',`${code}.small-missing-facts`);}
 return true;
}
function trustRemainder(code,p,r,set,physical,ops,regime){
 if(!regime)return;
 const key=code==='NY'?'nyEducationTrust':code==='IL'?'ilOperatesSchool':code==='OH'&&['school','university'].includes(p.type)?'ohEducationTrust':null;
 const trustClear=reason=>{r.regimes={solicitation:'exempt',charitableTrust:'not-indicated',reason};r.notes.push(reason);r.action=r.action.replace('The separate trust regime is evaluated below.','').trim()+' '+reason;};
 if(key){r.inputs.push(key);if(p[key]==='yes'){trustClear('The supplied institutional facts also support the separate charitable trust exemption. Keep that eligibility evidence.');return;}}
 const foreignKey=code==='MI'?'miForeignNoAssets':code==='OH'?'ohNoTrustContact':code==='IL'?'ilTrustNotApplicable':null;
 if(foreignKey){r.inputs.push(foreignKey);if(p[foreignKey]==='yes'){trustClear('The supplied foreign-entity and trust-scope facts support no separate charitable trust registration. Keep the supporting evidence.');return;}}
 if(code==='NY'&&!physical&&!ops.has(code)&&p.incorporation!==code){trustClear('No separate New York charitable trust activity was reported. Reassess if the entity is formed or begins activities there.');return;}
 r.partialExemptions=[...(r.partialExemptions||[]),`${sName(code)} solicitation relief does not itself remove the separate charitable trust registration.`];r.notes.push(r.partialExemptions.at(-1));
 if(code==='IL'){r.inputs.push('ilTrustCovered');if(p.ilTrustCovered==='no'){trustClear('You confirmed that the separate Illinois charitable trust property scope does not apply. Keep that evidence.');return;}}
 if((physical||ops.has(code)||p.incorporation===code)&&(!key||p[key]==='no')&&(code!=='IL'||p.ilTrustCovered==='yes')){
  const exemptionAction=r.action;set('required','The supplied facts support solicitation relief, but local charitable operations, assets or organization still indicate the separate trust registration.','Complete the applicable charitable trust registration. '+exemptionAction,`${code}.trust-registration`);r.label='Trust registration indicated';
  r.regimes={solicitation:'exempt',charitableTrust:'required'};
 }else{set('review','Solicitation eligibility is supported. The separate trust exemption or foreign-organization exclusion still needs confirmation.','Answer the trust question below so this result can distinguish exempt solicitation from trust registration.',`${code}.trust-missing-facts`);r.label='Confirm the separate trust requirement';}
}
const sName=code=>STATES.find(s=>s.code===code).name;
function onlineNexus(s,p){
 if(s.code===p.base)return {trigger:true,why:'The principal office is in this state and the organization solicits online.'};
 if(s.code==='MS'&&(p.msBank==='yes'||(p.bankStates||[]).includes('MS')||(p.operations||[]).includes('MS')))return {trigger:true,why:'A Mississippi address or bank account is a contact under Rule 2.08.'};
 const row=p.receipts?.[s.code]||{};
 if(['CO','WI','TN'].includes(s.code)&&(['unsolicited','grants','mixed'].includes(row.origin)||['offline','daf'].includes(p.onlineMethod)))return {trigger:null,why:'These gifts were not identified as contributions through an interactive fundraising website. The website receipt test cannot be applied to unrelated grants, unsolicited gifts or an off-site donation process. Review the actual appeal and receipt channel.'};
 const amount=number(row.amount),count=number(row.count),donors=number(row.donors),intended=number(row.intended);
 if(s.code==='CO'){
  const total=Object.hasOwn(row,'nationalTotal')?number(row.nationalTotal):number(p.fiscalActual);
  const amountMet=amount!==null&&total!==null&&amount>0&&amount>=Math.min(25000,total*.01);
  if((count!==null&&count>=50)||amountMet)return {trigger:true,why:'Colorado Rule 10 is met: 50 online contributions OR receipts at least the lesser of $25,000 or 1% of total contributions.'};
  if(amount===null||count===null||total===null)return {trigger:null,why:'Colorado needs the fiscal year online contribution count, state amount and total national contributions.'};
  return {trigger:false,why:'The supplied Colorado online receipts are below both Rule 10 thresholds, with no targeting or other stated contact.'};
 }
 if(s.code==='WI'){
  if(count!==null&&amount!==null)return {trigger:count>=50&&amount>25000,why:count>=50&&amount>25000?'Wisconsin internet criteria are met: at least 50 contributions AND more than $25,000.':'The supplied receipts do not meet both Wisconsin internet criteria; no other stated Wisconsin contact was found.'};
  return {trigger:null,why:'Wisconsin needs both fiscal year online contribution count and resident contribution amount. The tests are joined by AND.'};
 }
 if(s.code==='MS'){
  if((amount!==null&&amount>=25000)||(intended!==null&&intended>=25000)||(donors!==null&&donors>=25))return {trigger:true,why:'Mississippi Rule 2.08 is met by receipts or intended receipts of at least $25,000, OR at least 25 distinct resident donors.'};
  if(amount===null||intended===null||donors===null)return {trigger:null,why:'Mississippi needs actual and intended resident receipts plus distinct resident donor count; transactions are not donor count.'};
  if(p.msBank!=='no')return {trigger:null,why:'The receipts are below the Mississippi numeric tests, but a Mississippi bank account or mailing address has not been ruled out.'};
  return {trigger:false,why:'The supplied Mississippi receipts, intended receipts and distinct donors are below Rule 2.08 thresholds; no local bank, address or targeting was stated.'};
 }
 if(s.code==='NH'){
  if(row.repeated==='yes')return {trigger:true,why:'Repeated, ongoing or substantial New Hampshire receipts establish a reasonable contacts screening trigger under Jus 401.30.'};
  return {trigger:null,why:'New Hampshire uses a qualitative reasonable contacts test. Obtain a Trusts Unit review; there is no numeric safe harbor in this prototype.'};
 }
 if(s.code==='TN'){
  if((count!==null&&count>=100)||(amount!==null&&amount>=25000))return {trigger:true,why:'Tennessee’s internet test is met: at least 100 online contributions OR at least $25,000 from residents in a year. Targeting is an independent trigger.'};
  if(count===null||amount===null)return {trigger:null,why:'Tennessee needs the resident online contribution count and amount for the relevant year. The tests are joined by OR; blank is not zero.'};
  return {trigger:false,why:'The supplied Tennessee online receipts are below both internet thresholds, with no targeting or other stated Tennessee contact.'};
 }
 if(s.code==='FL')return {trigger:null,why:'Florida regulates solicitation in or from the state and has no verified numeric internet safe harbor in this assessment. A public donation page needs a Florida scope and exemption check; it is not cleared by a low donor count.'};
 return {trigger:null,why:'A public online appeal requires state specific nexus review. This profile has no verified numeric internet safe harbor; it does not assume all states require registration.'};
}
// Presentation can flag an existing website test without duplicating its law.
export function onlineGiftSignal(code,p){
 const s=STATES.find(s=>s.code===code),row=p.receipts?.[code];
 if(!s||!row||code===p.base||p.online!=='yes'||row.origin!=='website'||!['CO','WI','MS','TN'].includes(code))return null;
 const nexus=onlineNexus(s,p);
 return nexus.trigger===true?{kind:'threshold',text:'State online-giving test met',why:nexus.why}:null;
}
export function assess(p){
 const errors=validate(p);if(errors.length)throw new Error(errors.join(' '));
 const paid=conditions(p),target=new Set(p.target||[]),ops=new Set(p.operations||[]),registered=new Set(p.registered||[]),donorStates=new Set(p.donorStates||[]);
 const activityMode=p.screeningMode==='activity';
 const focused=p.screeningMode==='focused'||activityMode,nationwide=focused?p.homeOnly==='no'&&p.online==='yes'&&(p.onlineNationwide==='yes'||p.onlineReach==='nationwide'):p.homeOnly!=='yes';
 const noAppeals=p.homeOnly==='none',grantOnly=p.homeOnly==='grants'||p.grantsOnly==='yes';
 if(focused&&!noAppeals)target.add(p.base);
 for(const [code,row]of Object.entries(p.receipts||{}))if(row.emailAppeals==='yes'&&row.locationKnown==='yes')target.add(code);
 const incidentalGifts=focused&&p.homeOnly==='incidental',scopeQuestions=[];
 if(focused&&!['yes','no','incidental','none','grants'].includes(p.homeOnly))scopeQuestions.push('Do you seek or receive donations outside your home state? Confirm this before relying on the geographic scope.');
 if(focused&&p.online==='yes'&&!['local','public','incidental','selected','nationwide'].includes(p.onlineReach)&&!['yes','no'].includes(p.onlineNationwide))scopeQuestions.push('Does your online fundraising reach your local community, donors in specific states or donors nationwide? Confirm its reach before treating the scope as settled.');
 if(focused&&p.homeOnly==='no'&&p.online==='unknown')scopeQuestions.push('Confirm whether you make public online fundraising appeals and whom they reach.');
 if(focused&&p.homeOnly==='no'&&![...(p.target||[]),...(p.donorStates||[])].some(c=>c!==p.base)&&!nationwide)scopeQuestions.push('You reported donations outside your home state. Identify those states to extend this assessment.');
 const online=!noAppeals&&!grantOnly&&p.online!=='no',special=p.specialCategory!=='no';
 const result=STATES.map(s=>{
  const direct=!noAppeals&&(target.has(s.code)||(p.homeOnly==='yes'&&s.code===p.base)),physical=ops.has(s.code)||s.code===p.base,existing=registered.has(s.code);
  const onlineHere=online&&(nationwide||s.code===p.base);
  const receiptHere=donorStates.has(s.code)||Object.entries(p.receipts?.[s.code]||{}).some(([key,v])=>['amount','count','donors','intended'].includes(key)?number(v)>0:['emailAppeals','repeated'].includes(key)&&v==='yes');
 const relevant=direct||physical||existing||onlineHere||receiptHere||(['NH','NY','MI','OH','IL'].includes(s.code)&&p.incorporation===s.code)||(p.bankStates||[]).includes(s.code)||(s.code==='MS'&&p.msBank==='yes'&&online);
  const r={connectionConfirmed:direct||physical||existing||receiptHere||(s.code==='NH'&&p.incorporation==='NH')||(p.bankStates||[]).includes(s.code),code:s.code,name:s.name,status:'outside',why:p.homeOnly==='yes'?'You stated that fundraising is limited to your principal office state, with no out of state appeals or receipts. No other activity was stated here.':'No solicitation, online appeal, operations or existing registration was stated for this state.',action:'Reassess before adding activities or fundraising in this state.',sources:s.sources.map(x=>({...x})),coverage:s.coverage,reviewed:s.reviewed,notes:[s.note,s.nuance],ruleIds:[],inputs:[]};
  const set=(status,why,action,id)=>{r.status=status;r.why=why;r.action=action;if(id)r.ruleIds.push(id);};
  const donorOnly=incidentalGifts&&p.receipts?.[s.code]?.emailAppeals!=='yes'&&!['veterans','privateFoundation','unknown','other'].includes(p.type)&&p.specialCategory!=='yes'&&s.code!==p.base&&receiptHere&&!direct&&!physical&&!existing&&!(p.bankStates||[]).includes(s.code)&&!(s.code==='NH'&&p.incorporation==='NH');
  if(donorOnly&&!activityMode){
   const measured=['CO','WI','MS','NH','TN'].includes(s.code)&&online&&p.receipts?.[s.code]?onlineNexus(s,p):null;
   if(measured?.trigger===true)r.incidentalTrigger=measured;
   if(measured?.trigger!==true){r.deferred=true;r.label='Occasional gifts · not assessed';r.why='You reported occasional donor gifts without directed appeals or other stated activity here. This focused result does not determine this state’s filing duties.';r.action='Retain donor records. Request a state-specific review before targeted appeals or if support becomes regular or substantial. There is no universal 50-donor exemption.';r.ruleIds.push(`${s.code}.incidental-intake-deferred`);return r;}
  }
  if(!relevant){if(focused&&p.homeOnly==='no'){r.why='No specific activity was entered for this state. It is not included in this focused screening; reassess if your appeals, donors or operations reach it.';}if(focused&&scopeQuestions.length){r.label='Not assessed · reach uncertain';r.why='Fundraising reach has not been confirmed for this state. This is not a finding that registration is unnecessary.';r.action='Clarify fundraising reach and identify activity here before relying on a state result.';}return r;}
  if(s.mode==='pending'){set('review',s.note,'Verify the current state framework and applicable exclusions with the linked agency or statute.',`${s.code}.research-gap`);return r;}
  if(s.mode==='exempt501'){set('none','Recognized 501(c)(3) organizations are not required to register under Missouri’s current Attorney General FAQ.','Keep your IRS determination letter. If you need an agency exemption letter, request it at registrations@ago.mo.gov and attach the IRS letter; the current guidance describes this confirmation as available when needed.','MO.501c3');r.filing='optional';return r;}
  if(['none','paidOnly','veterans','texas','louisiana','utah'].includes(s.mode)&&!(s.mode==='louisiana'&&yes(p.solicitor)&&institutionRoute(s.code,p.type,p)&&!noAppeals)){
   const paidUnknown=['solicitor','consultant','paidStaff'].some(k=>!['yes','no'].includes(p[k]));
   const anyPaid=['solicitor','consultant','paidStaff'].some(k=>yes(p[k]));
   if(s.mode==='utah'){set('none','Utah no longer requires a separate charity solicitation license. Nonprofit entity registration and federal-return submission duties are separate.','No separate charity solicitation license is indicated. Use CC Aurora for any applicable entity or ongoing filing duties.','UT.no-separate-charity-license');r.sources.push({title:'Utah current charity framework',url:'https://commerce.utah.gov/dcp/for-businesses/charities/'});r.reviewed='2026-10-06';return r;}
   if(s.mode==='veterans'&&(p.type==='veterans'||p.specialCategory==='yes'||['unknown','other'].includes(p.type))){set('review','Arizona’s filing program concerns solicitation in the name of or for veterans organizations. Confirm whether the reported category or special activity includes that fundraising.','Check the veterans registration criteria before solicitation.','AZ.veterans');return r;}
   if(s.mode==='texas'&&(special||['veterans','privateFoundation'].includes(p.type))){r.inputs.push('specialCategory');set('review','Texas has special purpose and private foundation filing provisions.','Check veterans, public safety, law enforcement telephone appeals and foundation filings as applicable.','TX.special');return r;}
   if(s.mode==='louisiana'&&yes(p.solicitor)){set('required','A professional solicitor is used for Louisiana fundraising.','Confirm the contract definition and register annually at least ten days before the covered solicitation campaign.','LA.professional-solicitor');return r;}
   if(s.mode==='louisiana'&&p.solicitor==='no'){set('none','No outside compensated professional solicitor was reported. Louisiana’s ordinary charity-registration trigger is not indicated.','Review any provider contracts separately; a payment processor or salaried program employee alone is not a professional solicitor.','LA.no-professional-solicitor');return r;}
   if(['paidOnly','louisiana'].includes(s.mode)&&(anyPaid||paidUnknown)){set('review','Paid fundraising roles need review under this state’s solicitor and campaign rules.','Confirm who solicits, who is compensated, and any campaign or contract filings.',`${s.code}.paid-fundraising`);return r;}
   if(s.code==='IA'&&(ops.has('IA')||p.type==='privateFoundation')){set('review','Iowa charitable trust or foundation duties may apply apart from solicitation.','Review trust and foundation requirements.', 'IA.trust');return r;}
   set('none',`${s.name} has no general charitable solicitation registration requirement for this profile.`,'No general charitable solicitation registration is required here. Keep entity and tax filings separate; reassess before fundraising in another state.',`${s.code}.general-framework`);return r;
  }
  if(s.mode==='kentucky'&&direct&&(!institutionRoute('KY',p.type,p)||institutionRoute('KY',p.type,p).checks.some(k=>p[k]==='no'))){
   r.inputs.push('kyFederalReturnRequired','kyNewOrganization');if(p.kyFederalReturnRequired==='no')r.inputs.push('kyNoFederalFiling');r.sources.push({title:'Kentucky initial return and notice framework',url:'https://www.ag.ky.gov/Resources/Consumer-Resources/charity/Pages/registration.aspx'});r.reviewed='2026-10-06';
   if(noAppeals&&!existing)set('none','No Kentucky solicitation was reported. Kentucky’s solicitation return framework does not create an appeal from an information-only website.','Reassess before making covered requests for contributions.','KY.no-solicitation');
   else if(p.kyNewOrganization==='yes')set('required','A newly formed organization making covered Kentucky appeals must file its initial notice of intent before solicitation.','Submit Kentucky’s notice of intent with the agency’s initial supporting documents; this is distinct from a conventional charity license.','KY.initial-notice');
   else if(p.kyFederalReturnRequired==='yes')set('required','Covered Kentucky appeals by an organization required to file a federal annual return trigger the state return submission requirement.','Submit the most recent required federal return and initial supporting documents to Kentucky before covered solicitation. Use CC Aurora for subsequent filing management.','KY.initial-return');
   else if(p.kyFederalReturnRequired==='no'&&p.kyNoFederalFiling==='yes'&&p.kyNewOrganization==='no')set('none','You confirmed an exclusion from every federal annual return and 990-N notice, and no newly formed organization condition. The section 367.657 initial return trigger is not indicated.','Keep the federal exclusion evidence and reassess before changing the facts.','KY.return-not-required');
   else{set('review','Kentucky needs the actual federal filing obligation and newly formed organization facts. Filing a 990-N is a filing obligation, not a filing-free exemption.','Answer the initial-filing questions below. Kentucky accepts 990-N under its official checklist.','KY.return-missing-facts');}
   return r;
  }
  let nexus;
  if(direct)nexus={trigger:true,why:'You stated direct or targeted solicitation in this state. Receipts need not occur before solicitation rules apply.'};
  else if(s.code==='NY'&&p.type==='hospital'&&p.hospitalLicense==='yes'&&physical)nexus={trigger:false,why:'The licensed hospital supports the EPTL hospital exclusion. No solicitation connection was stated; Article 7-A must be reviewed separately if appeals begin.'};
  else if(noAppeals&&((s.code==='NY'&&['school','university'].includes(p.type)&&p.nyEducationTrust==='yes')||(s.code==='OH'&&['school','university'].includes(p.type)&&p.ohEducationTrust==='yes')||(s.code==='IL'&&p.ilOperatesSchool==='yes')))nexus={trigger:false,why:'No solicitation was reported and the supplied school facts support the separate charitable trust exclusion. Keep that institutional evidence; reassess before appeals begin.'};
  else if((s.mode==='assets'||s.code==='MI')&&(physical||(['NH','NY','MI','OH','IL'].includes(s.code)&&p.incorporation===s.code)))nexus={trigger:true,why:'The stated local operations, charitable assets or domestic organization create a separate registration screening trigger.'};
  else if(s.code==='MS'&&(p.msBank==='yes'||(p.bankStates||[]).includes('MS')||ops.has('MS'))&&online)nexus={trigger:true,why:'The online campaign has a Mississippi bank account or physical address contact.'};
  else if(r.incidentalTrigger)nexus=r.incidentalTrigger;
  else if(p.receipts?.[s.code]?.emailAppeals==='yes'){
   const measured=online&&['CO','WI','MS','NH','TN'].includes(s.code)?onlineNexus(s,p):null;
   nexus=measured?.trigger===true?measured:{trigger:null,why:'Fundraising emails were reported, but recipients’ state was not confirmed. Review known or reasonably available billing addresses and ZIP codes before deciding whether these were directed appeals.'};
  }
  else if(online&&p.receipts?.[s.code]&&['CO','WI','MS','NH','TN'].includes(s.code))nexus=onlineNexus(s,p);
  else if(donorStates.has(s.code)||receiptHere)nexus={trigger:null,why:'You reported donors here without directed appeals. Review how those gifts arose, online contacts and any other activity before deciding whether registration is needed.'};
  else if(online)nexus=onlineNexus(s,p);
  else if(existing)nexus={trigger:null,why:'An existing registration requires an annual filing or formal withdrawal review even if current appeals stopped.'};
  else nexus={trigger:false,why:'Local presence alone has not established a solicitation trigger under the facts entered. Review any past appeals and charitable assets duties.'};
  if(nexus.trigger===true)r.connectionConfirmed=true;
  if(noAppeals)r.notes.push('An information-only website or program update without a request for gifts is not being treated as an online appeal. Charitable assets, receipt and existing filing duties remain separate.');
  if(p.thirdPartyAppeal==='independent')r.notes.push('An independent third-party appeal without your knowledge or consent was reported. This does not establish an authorized campaign or automatic clearance. Preserve the facts and ask the state about attribution; your own appeals are assessed separately.');
  if(s.code==='NY'&&p.type==='hospital'){
   r.inputs.push('hospitalLicense');r.partialExemptions=['Hospital eligibility can remove EPTL registration; it does not by itself remove Article 7-A solicitation registration.'];
   r.notes.push(...r.partialExemptions);r.sources.push({title:'EPTL hospital exclusion',url:'https://www.nysenate.gov/legislation/laws/EPT/8-1.4'},{title:'Separate solicitation exemptions',url:'https://www.nysenate.gov/legislation/laws/EXC/172-A'});
   if(physical&&!direct&&p.hospitalLicense!=='yes')nexus={trigger:null,why:'Confirm whether the entity itself is a qualifying hospital for the EPTL exclusion. A hospital affiliate is not automatically excluded.'};
  }
  r.registrationTrigger=nexus.trigger;
  if(focused&&nexus.trigger===null&&(!r.connectionConfirmed||activityMode)){r.nexusPending=true;r.label=activityMode?'Confirm the state registration connection':'Confirm an online fundraising connection';}
  if(nexus.trigger===false){set('none',nexus.why,'Retain the facts used in this assessment and reassess if appeals, receipts, contacts or operations change.',`${s.code}.nexus-not-indicated`);}
  else if(nexus.trigger===null){set('review',nexus.why,'Confirm the missing facts or obtain the agency’s interpretation before deciding on registration.',`${s.code}.nexus-review`);}
  else set('required',nexus.why,'Review the linked registration process and file before covered solicitation; assets based deadlines can differ.',`${s.code}.registration-trigger`);
  const independentRoute=activityMode?institutionRoute(s.code,p.type,p):null;
  // An entity-wide statutory exclusion can settle registration without first
  // declaring a gift to be solicitation. Mandatory/discretionary applications
  // remain behind the confirmed-nexus gate.
  const independentExclusion=independentRoute&&['none','optional','verify'].includes(independentRoute.filing)&&!independentRoute.checks.some(k=>p[k]==='no');
  if(nexus.trigger!==false&&(!r.nexusPending||independentExclusion||activityMode&&s.code==='PA'&&p.type==='religious')){
   if(s.code==='DC'&&p.dcMembershipOnly==='yes'){
    r.inputs.push('dcMembershipOnly');set('exemption','Requests were reported as exclusively among the existing membership, supporting DC Code 44-1703(c)(2).','No solicitation certificate is indicated for this membership-only route. Retain the audience evidence; separate business and entity duties remain.','DC.membership-only');r.filing='none';r.filingLabel=FILING_LABELS.none;r.label=r.filingLabel;
   }else if(s.code==='IL'&&p.type==='religious'){
    set('required','Illinois’s religious reporting exemption requires an initial registration statement. It does not remove that initial filing.','Submit CO-1 registration and CO-3 if requesting the religious annual-report exemption. Retain the Attorney General’s determination.','IL.religious-initial-registration');r.partialExemptions=['A genuine religious category can support annual-report relief after initial registration; it also has separate charitable trust relief.'];r.notes.push(...r.partialExemptions);r.sources.push({title:'Current CO-1 and CO-3 instructions',url:'https://www.illinoisattorneygeneral.gov/Consumer-Protection/Charities/Building-Better-Charities/Charity-Registration/'});
   }else if(grantOnly&&['MD','NC','VA','HI','FL'].includes(s.code)&&!institutionRoute(s.code,p.type,p)?.checks.every(k=>Object.hasOwn(paid,k)?paid[k]===true:p[k]==='yes')){
    const allowed={MD:['government','privateFoundation','corporate'],NC:['government','charity','other501c','privateFoundation'],VA:['charity','privateFoundation','corporate'],HI:['government','charity','privateFoundation'],FL:['government','charity','other501c','privateFoundation']}[s.code];
    const kinds=p.grantSources||[],eligible=kinds.length>0&&kinds.every(k=>allowed.includes(k));
    const url={MD:'https://sos.maryland.gov/Charity/Pages/FAQ.aspx',NC:'https://www.ncleg.gov/EnactedLegislation/Statutes/HTML/ByChapter/Chapter_131F.html',VA:'https://law.lis.virginia.gov/vacode/title57/chapter5/section57-60/',HI:'https://data.capitol.hawaii.gov/hrscurrent/Vol10_Ch0436-0474/HRS0467B/HRS_0467B-0001.htm',FL:'https://www.flsenate.gov/Laws/Statutes/2026/496.404'}[s.code];
    r.sources.push({title:'Grant-only eligibility',url});r.inputs.push('grantSources');
    if(s.code==='MD'){r.inputs.push('grantFundingOnly','noSolicitor');r.sources.push({title:'Maryland limited funding exemption',url:'https://mgaleg.maryland.gov/mgawebsite/Laws/StatuteText?article=gbr&section=6-102'});}
    const mdSupported=s.code!=='MD'||p.grantFundingOnly==='yes'&&(kinds.every(k=>k==='government')||paid.noSolicitor===true);
    if(eligible&&mdSupported&&(s.code!=='FL'||kinds.every(k=>k==='government')||p.flGrantmakerRegistered==='yes')){
     if(s.code==='VA'){set('exemption','Only grant proposals to the listed for-profit corporations, 501(c)(3) organizations or private foundations were reported, supporting Virginia’s section 57-60(A)(14) route.','Submit Virginia’s exemption claim (Form 100) and required fee. Keep the approval and reassess before adding public appeals.','VA.grant-only-qualified');r.filing='application';r.filingLabel=FILING_LABELS.application;r.label=r.filingLabel;}
     else if(s.code==='MD'&&kinds.some(k=>k!=='government')){set('exemption','All received contributions were reported as coming only from for-profit corporations or federally determined private foundations, apart from government grants, and no professional solicitor is employed.','Keep the funding and private-foundation determination evidence. Provide satisfactory exemption evidence if requested by Maryland; reassess before accepting public contributions.','MD.grant-only-qualified');r.filing='none';r.filingLabel=FILING_LABELS.none;}
     else{set('none','Only applications to grantmakers covered by this state’s solicitation exclusion were reported. No public or individual donation requests were stated.','Keep the grant applications and grantmaker eligibility evidence. A grant agreement can separately require registration; reassess before public appeals.',`${s.code}.grant-only-qualified`);r.filing='none';}
    }else{
     set('review','Grant-only activity has a specific route, but the supplied grantmaker facts do not establish it.','Identify every grantmaker type and verify the linked conditions. Do not add a public donation appeal while relying on a grant-only exclusion.',`${s.code}.grant-missing-facts`);
     r.questions=['Identify all grantmaker types.'];if(s.code==='MD')r.questions.push('Confirm all received contributions come from those types, and whether a professional solicitor is employed.');if(s.code==='FL'){r.inputs.push('flGrantmakerRegistered');r.questions.push('For nonprofit grantmakers, confirm Florida registration.');}
    }
   }else if(s.code==='AK'&&p.akGamingPermit==='yes'){
    set('exemption','A current Alaska charitable gaming permit under AS 05.15.100 was confirmed.','Retain the current permit. Alaska’s one-time exemption notice is optional; reassess when the permit expires.','AK.gaming-permit');r.filing='optional';
   }else if(s.code==='MN'&&p.type==='privateFoundation'){
    r.inputs.push('mnPersonsSolicited','mnTrustAssets');const persons=number(p.mnPersonsSolicited),assets=number(p.mnTrustAssets);
    if(persons!==null&&persons<=100){set('exemption','The private foundation solicited no more than 100 persons in its last completed accounting year.','Submit Minnesota’s Charitable Organization Exemption Form. Retain private-foundation and solicitation-count evidence; separately assess Chapter 501B charitable trust registration.','MN.private-foundation');r.filing='application';
     if(assets===null||assets>=25000){r.partialExemptions=['The private-foundation solicitation exemption does not clear charitable trust registration.'];set('review',assets===null?'Solicitation relief is supported, but charitable trust assets have not been supplied.':'Charitable trust assets of $25,000 or more require a separate Chapter 501B scope/exemption review.','Confirm the charitable trust scope and exclusions; do not treat solicitation relief as trust clearance.','MN.trust-missing-facts');}
    }else{set('review','Private-foundation solicitation relief requires no more than 100 persons solicited in the last accounting year; charitable trust duties are separate.','Enter the actual solicitation count and charitable trust assets.','MN.foundation-missing-facts');}
   }else if(s.code==='PA'&&p.type==='religious'){
    const missing=[];
    if(!['yes','no'].includes(p.paReligiousSupport))missing.push('Is the organization primarily supported by government grants or contracts, appeals to its own members, congregation or previous donors, or fees for services?');
    if(!['yes','no'].includes(p.paNoInurement))missing.push('Is the organization’s net income free of direct private benefit to any individual?');
    r.inputs.push('type','paReligiousSupport','paNoInurement');
    r.notes=['This route is for a bona fide religious institution or a group that forms an integral part of one. Tax exemption is assumed from this tool’s 501(c)(3) scope; it has not been verified.','Pennsylvania’s religious exclusion has no contribution dollar cap or all-volunteer condition. This result concerns charitable solicitation registration, not every legal or tax duty.'];
    if(p.paReligiousSupport==='no'||p.paNoInurement==='no'){
     set('review','Your answers do not establish Pennsylvania’s religious exclusion. This does not by itself establish that registration is required.','Review another exemption, including the small organization route if applicable, or confirm registration with Pennsylvania’s Bureau of Corporations and Charitable Organizations.','PA.religious-condition-not-established');
     r.label='Religious exclusion not established';
    }else if(missing.length){
     set('review','Pennsylvania excludes qualifying religious institutions. We need the specific eligibility facts below before applying that exclusion.','Answer the remaining religious eligibility questions. Then review your Pennsylvania result before deciding on registration.','PA.religious-missing-facts');
     r.label=`Confirm ${missing.length} religious eligibility ${missing.length===1?'fact':'facts'}`;r.questions=missing;
    }else{
     set('exemption','Based on your religious organization category and eligibility answers, Pennsylvania’s religious exclusion appears to apply.','No charitable solicitation registration is indicated under this exclusion. Keep evidence of tax exemption, your primary sources of support and the absence of private inurement; reassess if those facts change.','PA.religious-exclusion');
     r.label='Religious exclusion appears to apply';
     r.filing='optional';r.filingLabel=FILING_LABELS.optional;
     r.action+=' BCO-9 is available for optional agency approval of the exclusion.';
    }
    if(p.specialCategory==='yes')r.notes.push('You also reported a special activity. Confirm it is part of the qualifying religious institution rather than a separate organization or fundraising arrangement.');
   }else if((p.type==='unknown'||p.type==='other'||p.type==='privateFoundation'||p.specialCategory==='yes')&&!institutionRoute(s.code,p.type,p)?.clarifiesCategory){
    set('review','An unclassified organization, private foundation or special statutory category requires a separate exemption and trust review.','Confirm the organization’s legal category and all applicable registration regimes.',`${s.code}.category-review`);
   }else if(institutionRoute(s.code,p.type,p)){
    let route=institutionRoute(s.code,p.type,p);
    const valuesFor=route=>route.checks.map(k=>Object.hasOwn(paid,k)?paid[k]:p[k]==='yes'?true:p[k]==='no'?false:null);
    let values=valuesFor(route);
    if(values.includes(false)&&route.alternative){r.inputs.push(...route.checks);route=route.alternative;values=valuesFor(route);}
    r.inputs.push(...route.checks);r.filing=route.filing;r.filingLabel=FILING_LABELS[route.filing];
    if(!r.sources.some(x=>x.url===route.url))r.sources.push({url:route.url,title:'Institutional eligibility and filing procedure'});
    if(values.includes(false)){
     set('review','Your answers do not establish this institutional exemption. That does not itself establish that registration is required.','Check an alternate exemption, including a small organization route, or review the registration requirements with the agency.',`${s.code}.institution-condition-not-established`);
     r.label='Institutional exemption not established';
     if(VERIFIED_CATEGORY_STATES.has(s.code)&&!SMALL[s.code]&&!['AK','ME'].includes(s.code)&&nexus.trigger===true){set('required','Covered activity establishes a registration trigger, and your answers do not establish the listed institutional exemption.','Use the agency’s registration process unless another documented statutory route applies. A discretionary waiver must be approved before you rely on it.',`${s.code}.institution-not-qualified`);r.filing=null;r.filingLabel=null;r.label=LABELS.required;}
    }else if(values.includes(null)){
     const keys=route.checks.filter((k,i)=>values[i]===null);r.questionKeys=keys;
     r.questions=keys.map(k=>QUESTIONS[k]?.[0]||'Confirm there is no professional solicitor, fundraising counsel or commercial co-venturer.');
     set('review','The institutional category has a possible exemption, but these eligibility facts are missing.','Answer the relevant eligibility questions before relying on this exemption.',`${s.code}.institution-missing-facts`);
     r.label='Confirm institutional eligibility';
    }else{
     set('exemption','The supplied eligibility facts support this institutional exemption or exclusion. Documents and current registry standing have not been verified.',route.action,`${s.code}.institution-qualified`);
     if(route.approvalRequired)r.approvalRequired=true;
     if(route.discretionary){r.discretionaryRequest=true;r.why='The supplied facts support requesting a discretionary waiver. Only the Director can approve it; this assessment does not establish that registration relief has been granted.';}
     r.label=FILING_LABELS[route.filing];
     trustRemainder(s.code,p,r,set,physical,ops,route.regime);
     if(nexus.trigger===null)r.notes.push('The exemption route is conditional on the supplied eligibility facts; the underlying fundraising connection has not been independently established.');
    }
   }else if(!VERIFIED_CATEGORY_STATES.has(s.code)&&(s.categories.includes(p.type)||['educationalFoundation','hospitalFoundation'].includes(p.type))){
    const ineligible=(p.type==='religious'&&['HI','MN','ND','WI'].includes(s.code)&&p.religion990==='no')||(['school','university'].includes(p.type)&&['AR','HI','NC','PA'].includes(s.code)&&p.accreditation==='no')||(p.type==='hospital'&&['AR','HI','KS','NC','PA','TN'].includes(s.code)&&p.hospitalLicense==='no');
    if(ineligible){
     set('review','The supplied institutional eligibility answer does not establish the state’s category exclusion. Another filing route may still apply.','Check the category definition, any alternate approval and small organization routes before deciding.',`${s.code}.category-condition-not-established`);
    }else
    if(s.code==='IL'&&['school','university'].includes(p.type)){
     set('required','Illinois educational reporting relief does not itself remove initial registration; solicitation or charitable assets establish a trigger.','Review initial registration first, then the separate annual reporting exemption.','IL.initial-versus-reporting');
    }else{
     set('review',`Your category may qualify, but this version has not verified every eligibility condition and exemption filing procedure for this state. ${nexus.trigger===null?'The solicitation connection also remains unresolved.':''}`.trim(),`Confirm the exact institutional definition and whether a claim is mandatory, optional or unnecessary. ${s.note}`,`${s.code}.category-review`);
     r.filing='verify';r.filingLabel=FILING_LABELS.verify;r.label='Verify institutional exemption';
     r.notes.push('Type alone is insufficient: confirm federal return exclusions, school accreditation or approval, hospital licensing, control and solicitation audience as relevant. No exemption is granted by this tool.');
    }
   }else if(s.code==='NY'&&physical){
    r.notes.push('A small Article 7-A solicitation route does not remove a separate EPTL charitable assets or operations trigger. Review the regimes independently.');
   }else if(screenLimited(s,p,paid,r,set)){
   }else if(SMALL[s.code]){
    screenSmall(s,p,paid,r,set,physical,ops,nexus);
    if(s.code==='KS'&&r.status!=='exemption')r.inputs.push('ksPersonsActual','ksPersonsExpected');
    if(['MI','OH'].includes(s.code)&&r.status==='exemption')trustRemainder(s.code,p,r,set,physical,ops,s.code);
   }else if(['AK','CO','KS','ME','MD','MI','NJ','NY','OH','SC','VA','WV'].includes(s.code)){
    const t=totals(p,'fiscal');
    if(t.unknown||t.max<=50000)set('review','A small organization, limited donor or alternate filing route may apply. This exemption is not automated in the prototype.','Review the state’s dollar basis, donor limit, compensation restrictions and any charitable assets regime.',`${s.code}.unautomated-small-route`);
   }
   if((SMALL[s.code]||['AK','ME'].includes(s.code))&&r.ruleIds.some(id=>/institution-condition-not-established|religious-condition-not-established/.test(id))){
    r.notes.push('The institutional route was not established. The separately supplied financial and paid role facts were checked for a small organization alternative.');
    if(!screenLimited(s,p,paid,r,set))screenSmall(s,p,paid,r,set,physical,ops,nexus);
    if(['MI','OH'].includes(s.code)&&r.status==='exemption')trustRemainder(s.code,p,r,set,physical,ops,s.code);
   }
   if(number(p.grantAmount)>0&&(r.status==='required'||r.status==='exemption')){
    r.notes.push('Grant receipts were reported. State contribution definitions differ; reconcile included and excluded grants before relying on a dollar based route.');
    if(!['MI','OH','SC','AK','ME','WV','NJ','MD'].includes(s.code)&&r.ruleIds.some(x=>x.includes('small-')))set('review','Grant receipts can change the statutory contribution total. A dollar based exemption needs reconciliation.','Calculate contributions using this state’s definition, including applicable grant exclusions.',`${s.code}.grant-definition-review`);
   }
  }
  if(existing){r.notes.push('You reported an existing registration. This tool does not verify status and does not authorize stopping renewals.');r.action+=' Confirm current renewal, final report or formal withdrawal duties before changing filings.';if(['none','exemption'].includes(r.status)){set('review','An existing registration requires renewal or formal withdrawal review even if an exemption or exclusion may apply.','Confirm the current registration and whether the state must approve conversion to an exemption or formal withdrawal. Do not stop filings based on this screening.',`${s.code}.existing-registration`);r.label='Review existing registration';}}
  if(s.code==='DC'&&nexus.trigger!==false&&!r.nexusPending){
   r.inputs.push('dcMembershipOnly');
  }
  if(s.code==='FL'&&r.filing==='simplified'){
   r.inputs.push('flCurrentActual');const current=number(p.flCurrentActual);
   if(current!==null&&current>=50000){set('required','Current actual contributions have reached $50,000, ending the prior-year small-charity filing route.','Register within 30 days after reaching $50,000. Confirm disclosures and current filing instructions.','FL.small-transition');r.filing=null;r.filingLabel=null;}
  }
  if(s.code==='NJ'&&r.ruleIds.some(id=>id==='NJ.small-candidate')){r.inputs.push('njCurrentContributions');if(number(p.njCurrentContributions)>10000){set('required','Current-year contributions exceeded New Jersey’s $10,000 small-exemption limit.','Register within 30 days after crossing the limit. Assess short-form eligibility separately; short form is registration.','NJ.small-transition');r.filing=null;r.filingLabel=null;}}
  if(s.code==='MD'&&r.ruleIds.includes('MD.small-candidate')&&number(p.mdFiscalContributions)===25000){r.filing='verify';r.filingLabel=FILING_LABELS.verify;r.action='The statute and notice checkbox use not more than $25,000, while the notice instructions say less than $25,000. Confirm Maryland’s exact-boundary filing procedure; do not treat this as no filing.';r.notes.push('Exact $25,000 boundary: reconcile statute/checkbox with agency instruction wording.');}
  if(s.code==='WA'&&(physical||ops.has('WA'))){
   r.inputs.push('waTrustAssets');const assets=number(p.waTrustAssets);
   if(assets!==null&&assets>250000){r.inputs.push('waTrustExempt');
    if(p.waTrustExempt!=='yes'){r.partialExemptions=[...(r.partialExemptions||[]),'Any solicitation exemption does not remove separate charitable trust registration.'];set(p.waTrustExempt==='no'?'required':'review','Income-producing trust assets exceed $250,000; Washington’s separate trust exclusions must be assessed.','Confirm the trust instrument and religious, remainder or accredited-public-education exclusion; register the trust if no exclusion applies.','WA.trust-scope');}
   }
  }
  if(p.pastSolicitation==='yes'&&['required','review'].includes(r.status))r.notes.push('Past solicitation was reported. Review any historical or late filings separately from the prospective action shown.');
  return r;
 });
 for(const r of result)if(registered.has(r.code)&&r.status==='none'){r.status='review';r.why='An existing registration requires renewal or formal withdrawal review even when a new registration trigger is not indicated.';r.action='Confirm ongoing filings and the state’s formal withdrawal process before stopping renewals.';r.ruleIds.push(`${r.code}.existing-registration`);}
 for(const r of result)r.nextSteps=nextSteps(p,r);
 const onlineNotes=[];
 if(p.online==='yes')onlineNotes.push('A public donation button is different from directed appeals. Emails, ads or follow-up appeals to donors whose state you know can establish targeting; select those states as fundraising states. Receipt thresholds do not excuse targeted solicitation.');
 if(p.online==='yes'&&p.onlineMethod==='offline')onlineNotes.push('A website asking people to mail a check or call is still an appeal. An interactive website receipt threshold cannot automatically be used to clear that off-site process. Directed emails remain separate triggers.');
 if(p.onlineMethod==='daf')onlineNotes.push('A donor-advised fund portal and an unsolicited DAF distribution are different from your own public appeal. Keep the sponsoring charity’s records and identify any appeals you make; a portal listing is not nationwide clearance.');
 if(p.onlineMethod==='platform')onlineNotes.push('A contracted fundraising platform can have consent, eligibility, contract and standing requirements. Its filings do not automatically satisfy your nonprofit’s own registration duties.');
 if(p.thirdPartyAppeal==='independent')onlineNotes.push('An unapproved third-party appeal requires an attribution review. Do not label it as your authorized campaign or assume it excuses your own fundraising.');
 if(p.online==='yes'&&['public','local','incidental'].includes(p.onlineReach))onlineNotes.push('This local assessment does not clear every state that can access your website. Florida has no verified numeric internet safe harbor here: a public donation page needs a Florida reach and eligibility check even without a national campaign. Confirm any religious, educational or small charity route.');
 return {onlineNotes,confirmedActivityStates:result.filter(r=>r.status!=='outside'&&r.connectionConfirmed).map(r=>r.code),onlineConnectionQuestions:result.filter(r=>r.status!=='outside'&&!r.connectionConfirmed).map(r=>r.code),incidentalGifts,scopeQuestions,version:VERSION,reviewDate:REVIEW_DATE,assessedAt:new Date().toISOString(),scope:'Charitable solicitation and related charity registration screening for recognized 501(c)(3) organizations; not a standing check.',results:result,counts:Object.fromEntries(Object.keys(LABELS).map(k=>[k,result.filter(r=>r.status===k).length]))};
}
