/* One original Chrome-rendered frame; callers still own identity and postchecks. */
const CCOwnedSourcePixels=(()=>{
  const lanes=new Set();
  const image=value=>typeof value==='string'&&value.length>100&&value.length<=4000000
    &&/^[A-Za-z0-9+/]+={0,2}$/.test(value);
  function coversViewport(options,layout){
    const v=layout?.cssVisualViewport||layout?.visualViewport;
    if(!v||![v.clientWidth,v.clientHeight,v.pageX,v.pageY].every(Number.isFinite)
        ||v.clientWidth<1||v.clientHeight<1||v.clientWidth*v.clientHeight>20000000)return false;
    if(!options.clip)return options.captureBeyondViewport===false;
    const c=options.clip;
    return c.scale===1&&Math.abs(c.x-v.pageX)<=1&&Math.abs(c.y-v.pageY)<=1
      &&Math.abs(c.width-v.clientWidth)<=1&&Math.abs(c.height-v.clientHeight)<=1;
  }
  async function capture(tabId,options,{deadline,alive=()=>true,observe=()=>{}}){
    if(!Number.isInteger(tabId)||lanes.has(tabId)||!alive())throw Error('pixel_capture_not_owned');
    const stop=Math.min(deadline-500,Date.now()+2500);
    if(stop-Date.now()<250)throw Error('pixel_capture_deadline');
    lanes.add(tabId);
    let timer,listener,active=false;
    const invoke=(method,params={})=>chrome.debugger.sendCommand({tabId},method,params);
    try{
      const layout=await invoke('Page.getLayoutMetrics');
      if(!coversViewport(options,layout)||!alive())throw Error('pixel_capture_not_viewport');
      const v=layout.cssVisualViewport||layout.visualViewport;
      const began=Date.now();
      const frame=new Promise((resolve,reject)=>{
        listener=(source,method,params)=>{
          if(source.tabId!==tabId||method!=='Page.screencastFrame')return;
          if(Number.isInteger(params?.sessionId))invoke('Page.screencastFrameAck',{sessionId:params.sessionId}).catch(()=>{});
          const m=params?.metadata;
          // A frame from before this operation, another viewport or a scaled
          // preview cannot authorize publication of the selected source.
          if(!alive()||Date.now()>=stop)return reject(Error('pixel_capture_stale'));
          if(!m||!Number.isFinite(m.timestamp)||m.timestamp*1000<began-10
              ||m.timestamp*1000>Date.now()+1000||m.pageScaleFactor!==1
              ||Math.abs(m.deviceWidth-v.clientWidth)>1||Math.abs(m.deviceHeight-v.clientHeight)>1
              ||Math.abs(m.scrollOffsetX-v.pageX)>1||Math.abs(m.scrollOffsetY-v.pageY)>1
              ||m.offsetTop!==0||!image(params?.data))return;
          resolve({data:params.data});
        };
        chrome.debugger.onEvent.addListener(listener);
        timer=setTimeout(()=>reject(Error('pixel_capture_frame_timeout')),Math.max(1,stop-Date.now()));
      });
      // Attach rejection handling before start so command failure cannot leave
      // an unhandled frame timeout or an event listener on a later document.
      frame.catch(()=>{});
      active=true;
      await invoke('Page.startScreencast',{format:'jpeg',quality:options.quality||75,
        maxWidth:Math.ceil(v.clientWidth),maxHeight:Math.ceil(v.clientHeight),everyNthFrame:1});
      const result=await frame;
      if(!alive()||Date.now()>=deadline)throw Error('pixel_capture_stale');
      observe({method:'original-frame',milliseconds:Date.now()-began});
      return result;
    }finally{
      clearTimeout(timer);
      if(listener)chrome.debugger.onEvent.removeListener(listener);
      if(active)await invoke('Page.stopScreencast').catch(()=>{});
      lanes.delete(tabId);
    }
  }
  if(typeof module!=='undefined')module.exports={coversViewport,image,capture};
  return {capture,coversViewport};
})();
