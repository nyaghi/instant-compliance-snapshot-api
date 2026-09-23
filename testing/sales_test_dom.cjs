// Minimal DOM fixture; executes real Sales handlers without browser/network I/O.
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
exports.setup=({origin='https://staging.compliance-express.com'}={})=>{
 const elements={},inputs=[],events=[],calls=[],pending=new Map();let active=0,peak=0;
 class Element{
  constructor(){this.children=[];this.events={};this.style={};this.dataset={};this.value='';this.checked=false;this.disabled=false;this.hidden=false;this.textContent='';this.classList={contains:()=>true};}
  set innerHTML(s){this._html=s;for(const m of s.matchAll(/id="([^"]+)"/g)){const e=new Element();e.id=m[1];e.parentElement=this;elements[e.id]=e;}for(const m of s.matchAll(/name="salesStates" value="([A-Z]+)"/g)){const e=new Element();e.value=m[1];inputs.push(e);}}
  get innerHTML(){return this._html||'';} append(...els){els.forEach(e=>{e.parentElement=this;this.children.push(e);});}prepend(...els){this.children.unshift(...els);els.forEach(e=>{e.parentElement=this;if(e.id)elements[e.id]=e;});}replaceChildren(...els){this.children=[];this.append(...els);}setAttribute(k,v){this[k]=v;}focus(){}querySelectorAll(){return inputs;}addEventListener(k,v){this.events[k]=v;}
 }
 for(const id of ['progressBox','submitButton','organizationName','ein','email','adminPasscode'])elements[id]=new Element();
 const standard=[new Element(),new Element()],main=new Element();main.children=standard.slice();
 const context={location:{origin},document:{querySelector:()=>main,createElement:()=>new Element(),head:new Element(),getElementById:id=>elements[id]},window:{dispatchEvent:e=>events.push(e)},CustomEvent:class{constructor(type,x){this.type=type;this.detail=x.detail;}},performance,setInterval,clearInterval,internalUnlocked:true,isComplianceExpressEmail:()=>true,API_BASE:'https://staging.example',requestSingleState:(...args)=>{calls.push(args);peak=Math.max(peak,++active);return new Promise((resolve,reject)=>pending.set(args[3],{resolve,reject}));}};
 vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(__dirname,'../web-staging/sales-mode.js'),'utf8'),context);
 if(elements.ccSalesName){elements.ccSalesName.value='Control';elements.ccSalesEin.value='123456789';elements.ccSalesConsent.checked=true;elements.email.value='test@example.test';elements.adminPasscode.value='fixture';}
 const finish=(state,result)=>{const p=pending.get(state);if(!p)throw Error('No pending '+state);pending.delete(state);active--;result instanceof Error?p.reject(result):p.resolve(result);};
 return {context,elements,inputs,events,calls,standard,get peak(){return peak;},finish,submit:()=>elements.ccSalesForm.events.submit({preventDefault(){}}),async drain(){while(pending.size){for(const state of [...pending.keys()])finish(state,{state,status:'Current'});await new Promise(setImmediate);}}};
};
