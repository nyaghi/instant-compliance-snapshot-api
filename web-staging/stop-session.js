/* Isolated UI coordinator proposal. No network endpoints or credentials. */
'use strict';
class StopRun {
  constructor({states,requestId,admission,recoverAdmission,backend,abort,cleanup,
    onState=()=>{},timeoutMs=30000,pollMs=500}) {
    this.states=Object.freeze([...states]);this.requestId=requestId;
    this.admission=Promise.resolve(admission);this.admission.catch(()=>{});
    this.recoverAdmission=recoverAdmission;this.backend=backend;
    this.abort=abort;this.cleanup=cleanup;this.onState=onState;
    this.timeoutMs=timeoutMs;this.pollMs=pollMs;this.token=null;
    this.results=new Map();this.phase='running';this.pending=null;this.abortSent=false;
  }
  record(result) {
    if(this.phase!=='running'||!this.states.includes(result.state)||this.results.has(result.state))return false;
    this.results.set(result.state,result);return true;
  }
  change(phase) {this.phase=phase;this.onState(phase,[...this.results.values()]);}
  async bounded(promise,deadline) {
    if(Date.now()>=deadline)throw Object.assign(new Error('Stopping could not be confirmed.'),{code:'STOP_UNCONFIRMED'});
    let timer;
    try {
      return await Promise.race([promise,new Promise((_,reject)=>{
        timer=setTimeout(()=>reject(Object.assign(new Error('Stopping could not be confirmed.'),{code:'STOP_UNCONFIRMED'})),Math.max(1,deadline-Date.now()));
      })]);
    } finally {clearTimeout(timer);}
  }
  stop() {
    if(this.phase==='completed'||this.phase==='stopped')return Promise.resolve(this.summary());
    if(this.pending)return this.pending;
    this.change('stopping');
    if(!this.abortSent){this.abortSent=true;this.abort();}
    const deadline=Date.now()+this.timeoutMs;
    this.pending=(async()=>{
      try {
        if(!this.token) {
          let admission;
          try {admission=await this.bounded(this.admission,deadline);}
          catch(error) {
            if(error.code==='STOP_UNCONFIRMED'||!this.recoverAdmission)throw error;
            // Adapter must reuse the immutable original idempotency key.
            admission=await this.bounded(this.recoverAdmission(this.requestId),deadline);
          }
          if(admission?.token)this.token=admission.token;
          else if(admission?.notSubmitted!==true)throw new Error('Workflow ownership is unconfirmed.');
        }
        if(this.token)await this.bounded(this.backend.cancel(this.token),deadline);
        const cleanup=await this.bounded(this.cleanup(),deadline);
        if(cleanup?.confirmed!==true)throw new Error('Owned browser cleanup is unconfirmed.');
        if(this.token) {
          while(true) {
            const status=await this.bounded(this.backend.poll(this.token),deadline);
            if(Number.isFinite(status.finished)&&['canceled','completed','expired'].includes(status.phase))break;
            await this.bounded(new Promise(resolve=>setTimeout(resolve,this.pollMs)),deadline);
          }
        }
        this.change('stopped');return this.summary();
      } catch(error) {
        this.change('stop_failed');error.code='STOP_UNCONFIRMED';
        error.partialResults=[...this.results.values()];throw error;
      } finally {this.pending=null;}
    })();
    return this.pending;
  }
  complete() {
    if(this.phase==='running')this.change('completed');
    return this.summary();
  }
  summary() {
    return {phase:this.phase,results:[...this.results.values()],
      unfinishedStates:this.states.filter(state=>!this.results.has(state))};
  }
  bindButton(button,{onStopped=()=>{},onError=()=>{}}={}) {
    const previous=this.onState;
    this.onState=(phase,results)=>{
      button.disabled=phase==='stopping';
      button.textContent=phase==='running'?'Checking public registries — Stop':
        phase==='stopping'?'Stopping…':phase==='stop_failed'?'Retry stopping':'Run CharityClarity';
      previous(phase,results);
    };
    button.addEventListener('click',event=>{
      if(!['running','stopping','stop_failed'].includes(this.phase))return;
      event.preventDefault();void this.stop().then(onStopped,onError);
    });
    this.onState(this.phase,[]);
  }
}

class CCStopSession {
  constructor(states,onState=()=>{}) {
    this.states=[...states];this.controller=new AbortController();this.lookups=new Map();this.run=null;this.onState=onState;
  }
  get signal(){return this.controller.signal;}
  get phase(){return this.run?.phase||'running';}
  bind(control){
    if(this.run)throw new Error('Workflow Stop control is already bound.');
    this.run=new StopRun({...control,states:this.states,abort:()=>this.controller.abort(),onState:this.onState});
  }
  owned(handle){
    if(!handle||typeof handle.lookupId!=='string'||!this.states.includes(handle.state)||typeof handle.stop!=='function')throw new Error('Owned lookup handle is invalid.');
    if(this.lookups.has(handle.lookupId))throw new Error('Duplicate owned lookup handle.');
    this.lookups.set(handle.lookupId,handle);
  }
  async confirmCleanup(){
    const receipts=await Promise.all([...this.lookups.values()].map(h=>h.stop()));
    return {confirmed:receipts.every(r=>r?.confirmed===true),receipts};
  }
  record(result){return this.run?.record(result)||false;}
  complete(){return this.run?.complete();}
  stop(){if(!this.run)return Promise.reject(new Error('Workflow Stop ownership is unavailable.'));return this.run.stop();}
}
window.CCStopSession=CCStopSession;
