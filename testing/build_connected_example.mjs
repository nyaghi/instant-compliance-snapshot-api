// Explicit fictional preview fixture; never used by registry lookup or runtime matching.
import fs from 'node:fs';
import {assess} from '../deployment/insight/head-start/engine.js';
import {registrationTable} from '../deployment/insight/head-start/decisions.js';
const profile={taxStatus:'recognized501c3',screeningMode:'activity',type:'hospital',base:'PA',incorporation:'PA',homeOnly:'no',
 target:['PA','HI','CA','CT','CO','WA','NY'],online:'yes',onlineReach:'public',onlineNationwide:'no',fiscalActual:250000,
 donorStates:[],operations:['WA'],registered:[],bankStates:[],receipts:{},solicitor:'no',consultant:'no',paidStaff:'no',coVenturer:'no',
 hospitalLicense:'yes',caPrimaryInstitution:'yes',paHospitalRegulated:'yes',waTrustAssets:300000,waTrustExempt:'no',
 coFiscalGross:15000,coExpectedGross:20000};
const result=assess(profile),groups=registrationTable(result,profile,{includeGeneralFramework:true});
const middle=new Map(groups.potentialExemption.map(r=>[r.code,r]));
const head_start={schema_version:'cc.head-start/1',assessment_id:'4d43f91a-52fa-48f3-a4b4-ef7e04a690d3',organization_name:'Example Regional Hospital',ein:'012345678',
 assessed_at:result.assessedAt,engine_version:result.version,ui_version:'0.19.0',profile,
 requirements:result.results.map(r=>({...r,exemption_evidence:middle.get(r.code)?.exemptionEvidence||null,possible_exemption:middle.has(r.code),
 approvalRequired:!!r.approvalRequired,discretionaryRequest:!!r.discretionaryRequest,deferred:!!r.deferred,nexusPending:!!r.nexusPending}))};
const statuses={PA:'Upcoming Filing',HI:'Current',CA:'Current',CO:'Current',CT:'Not Registered',WA:'Not Registered',NY:'Site Not Reachable',RI:'Current'};
const results=Object.entries(statuses).map(([state,status])=>({organization_name:head_start.organization_name,ein:head_start.ein,state,status,
 comments:'Fictional example for the connected report preview. No registry check was performed.'+(state==='PA'?' Illustrative registration expiration: 11/15/2026.':''),
 raw_status_text:'Illustrative result: '+status,source_note:'Sample evidence only; not a real organization or registry result.',
 source_url:'https://example.org/registry',matched_registry_identifier:status==='Current'?'EXAMPLE-001':'',checked_at_epoch:Math.floor(Date.now()/1000),app_version:'illustrative-example',
 ...(state==='PA'?{computed_due_date:'2026-11-15'}:{})}));
fs.mkdirSync('testing/fixtures/connected-hospital',{recursive:true});
fs.writeFileSync('testing/fixtures/connected-hospital/assessment.json',JSON.stringify(head_start,null,2));
fs.writeFileSync('testing/fixtures/connected-hospital/report-payload.json',JSON.stringify({illustrative_example:true,head_start,results},null,2));
console.log(JSON.stringify({states:results.length,requirements:head_start.requirements.length,scope:'fictional preview only'}));
