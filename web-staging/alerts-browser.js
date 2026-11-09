(() => {
  window.CCAlertsBrowser = (action, profile) => new Promise(resolve => {
    const id=crypto.randomUUID();
    const timer=setTimeout(()=>{window.removeEventListener('message',request);resolve({ok:false});},2500);
    const request=event=>{
      if(event.source!==window || event.origin!==location.origin || event.data?.channel!=='cc-alerts-browser-v1'
          || event.data?.direction!=='response' || event.data?.id!==id)return;
      clearTimeout(timer);
      window.removeEventListener('message',request);
      resolve(event.data.result || {ok:false});
    };
    window.addEventListener('message',request);
    window.postMessage({channel:'cc-alerts-browser-v1',direction:'request',id,action,profile},location.origin);
  });
})();
