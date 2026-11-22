/* One original Chrome-rendered frame; callers still own identity and postchecks. */
const CCOwnedSourcePixels=(()=>{
  const lanes=new Set(),receivers=new Map();
  // Manifest V3 requires synchronous registration while the worker loads.
  // Per-capture registrations can miss the first Chrome debugger event.
  chrome.debugger.onEvent.addListener((source,method,params)=>{
    receivers.get(source.tabId)?.(source,method,params);
  });
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
    let timer,listener,active=false,rendering=false;
    const invoke=(method,params={})=>chrome.debugger.sendCommand({tabId},method,params);
    try{
      const layout=await invoke('Page.getLayoutMetrics');
      if(!coversViewport(options,layout)||!alive())throw Error('pixel_capture_not_viewport');
      const v=layout.cssVisualViewport||layout.visualViewport;
      const actual=(await invoke('Runtime.evaluate',{
        expression:'({width:innerWidth,height:innerHeight,focused:document.hasFocus()})',returnByValue:true
      }))?.result?.value;
      // Chrome metadata includes scrollbars; layout metrics exclude them.
      // Read the exact owned document viewport rather than allowing a margin
      // or shrinking the source image to the content width.
      if(!actual||![actual.width,actual.height].every(Number.isFinite)
          ||actual.width+1<v.clientWidth||actual.height+1<v.clientHeight
          ||actual.width*actual.height>20000000||typeof actual.focused!=='boolean'||!alive())throw Error('pixel_capture_geometry');
      // Layout metrics are CSS pixels; screencast metadata is in DIP.
      // Browser zoom and the scrollbar gutter belong to that conversion.
      const zoom=v.zoom===undefined?1:v.zoom;
      if(!Number.isFinite(zoom)||zoom<=0||zoom>5)throw Error('pixel_capture_zoom');
      const expected={width:(v.clientWidth+actual.width-Math.round(v.clientWidth))*zoom,
        height:(v.clientHeight+actual.height-Math.round(v.clientHeight))*zoom};
      if(expected.width*expected.height>20000000)throw Error('pixel_capture_geometry');
      // Quiet tabs can have a loaded DOM but no compositor frames. This
      // emulates focus only in the owned renderer; it never activates a tab
      // or window. Preserve an existing focused renderer and restore only
      // the emulation enabled by this exact capture.
      if(!actual.focused){
        await invoke('Emulation.setFocusEmulationEnabled',{enabled:true});rendering=true;
      }
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
              ||Math.abs(m.deviceWidth-expected.width)>1||Math.abs(m.deviceHeight-expected.height)>1
              ||Math.abs(m.scrollOffsetX-v.pageX)>1||Math.abs(m.scrollOffsetY-v.pageY)>1
              ||m.offsetTop!==0||!image(params?.data))return;
          resolve({data:params.data});
        };
        receivers.set(tabId,listener);
        timer=setTimeout(()=>reject(Error('pixel_capture_frame_timeout')),Math.max(1,stop-Date.now()));
      });
      // Attach rejection handling before start so command failure cannot leave
      // an unhandled frame timeout or an event listener on a later document.
      frame.catch(()=>{});
      active=true;
      await invoke('Page.startScreencast',{format:'jpeg',quality:options.quality||75,
        maxWidth:Math.ceil(expected.width),maxHeight:Math.ceil(expected.height),everyNthFrame:1});
      const result=await frame;
      if(!alive()||Date.now()>=deadline)throw Error('pixel_capture_stale');
      observe({method:'original-frame',milliseconds:Date.now()-began});
      return result;
    }finally{
      clearTimeout(timer);
      receivers.delete(tabId);
      if(active)await invoke('Page.stopScreencast').catch(()=>{});
      if(rendering)await invoke('Emulation.setFocusEmulationEnabled',{enabled:false}).catch(()=>{});
      lanes.delete(tabId);
    }
  }
  // The DOM can be clear while Chrome still supplies the previous ORION frame.
  // Measure a small copy solely for quality control; publish the original JPEG.
  function nvVeilInPixels(rgba,width,height) {
    const pixels=width*height;
    let dark=0,blueCenter=0;
    for(let i=0;i<pixels;i++) {
      const k=i*4,r=rgba[k],g=rgba[k+1],b=rgba[k+2];
      if(Math.max(r,g,b)<130 && ++dark>pixels*.00015)return false;
      const x=i%width,y=Math.floor(i/width);
      if(x>width*.43&&x<width*.57&&y>height*.39&&y<height*.61
          &&b>120&&b-r>75&&b-g>45)blueCenter++;
    }
    return blueCenter>=Math.max(8,pixels*.00005);
  }
  async function nvDetailVeiled(data) {
    if(!image(data))throw Error('invalid_nv_detail_image');
    const bytes=Uint8Array.from(atob(data),c=>c.charCodeAt(0));
    const bitmap=await createImageBitmap(new Blob([bytes],{type:'image/jpeg'}));
    try {
      const scale=Math.min(1,768/Math.max(bitmap.width,bitmap.height));
      const w=Math.max(1,Math.round(bitmap.width*scale)),h=Math.max(1,Math.round(bitmap.height*scale));
      const ctx=new OffscreenCanvas(w,h).getContext('2d',{willReadFrequently:true});
      ctx.drawImage(bitmap,0,0,w,h);
      return nvVeilInPixels(ctx.getImageData(0,0,w,h).data,w,h);
    } finally {bitmap.close();}
  }
  if(typeof module!=='undefined')module.exports={coversViewport,image,capture,nvDetailVeiled,nvVeilInPixels,pendingCount:()=>receivers.size};
  return {capture,coversViewport,nvDetailVeiled};
})();
