/* Isolated upload rehearsal. Never operates on Tennessee or clicks Submit. */
(() => {
  'use strict';
  async function populate(root,co,documentUrl) {
    const source=new URL(documentUrl,location.origin);
    if(location.origin!=='https://charityclarity-final-four-29-2.onrender.com'||root.dataset.demoOnly!=='true'||
      source.origin!==location.origin||!/^\/api\/tn-extension-demo\/documents\/[a-f0-9]{32}$/.test(source.pathname)||source.search||source.hash||!/^CO\d+$/.test(co))throw new Error('Only the isolated staging upload rehearsal is supported.');
    const response=await fetch(source.href,{credentials:'same-origin',signal:AbortSignal.timeout(15000)});
    if(!response.ok||!(response.headers.get('content-type')||'').includes('application/pdf'))throw new Error('The matching test attachment could not be loaded.');
    const blob=await response.blob();if(blob.size>2097152)throw new Error('Test attachment is too large.');
    const input=root.querySelector('#tnPortalUpload'),field=root.querySelector('#tnPortalCO');
    const transfer=new DataTransfer();transfer.items.add(new File([blob],'demo-only-supporting-document.pdf',{type:'application/pdf'}));
    field.value=co;field.dispatchEvent(new Event('input',{bubbles:true}));field.dispatchEvent(new Event('change',{bubbles:true}));
    input.files=transfer.files;input.dispatchEvent(new Event('change',{bubbles:true}));
    if(input.files.length!==1||input.files[0].size!==blob.size)throw new Error('The test attachment did not reach the upload control.');
    return {co,filename:input.files[0].name,bytes:blob.size,demo_only:true};
  }
  window.CCTennesseePortalRehearsal={populate};
})();
