"""Lab worker-owned Chromium reuse; no registry or classification logic.

A browser is leased exclusively to one isolated job. That job still creates
fresh contexts and keeps its original deadline. After its process tree stops,
the supervisor destroys remaining contexts and confirms cleanup before releasing
source permits or lending the browser again. Busy/unavailable pools use the
existing private launch. No customer browser or profile is attached.
"""
import json
import os
from pathlib import Path
import queue
import re
import signal
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit

SERVER_SCRIPT = r"""
const {chromium} = require(process.argv[1]);
const count=Number(process.argv[2]);
const readline=require('readline');
let entries=[];
async function main(){
  for(let i=0;i<count;i++){
    const server=await chromium.launchServer({headless:true,host:'127.0.0.1',port:0});
    console.log(JSON.stringify({started:{index:i,endpoint:server.wsEndpoint(),pid:server.process().pid}}));
    const admin=await chromium.connect(server.wsEndpoint());
    const cdp=await admin.newBrowserCDPSession();
    entries.push({server,admin,cdp,dead:false});
  }
  console.log(JSON.stringify({ready:true,entries:entries.map((e,i)=>({index:i,endpoint:e.server.wsEndpoint(),pid:e.server.process().pid}))}));
  let chain=Promise.resolve();
  readline.createInterface({input:process.stdin}).on('line',line=>{
    chain=chain.then(async()=>{
      const request=JSON.parse(line);
      if(request.op==='close'){
        await Promise.all(entries.filter(e=>!e.dead).map(e=>e.server.kill()));
        console.log(JSON.stringify({id:request.id,closed:true}));process.exit(0);
      }
      const e=entries[request.index];
      if(!e)throw Error('Invalid browser');
      if(e.dead){console.log(JSON.stringify({id:request.id,disabled:true,remaining:0}));return;}
      try{
        const before=(await e.cdp.send('Target.getBrowserContexts')).browserContextIds;
        if(request.op==='cleanup')
          for(const id of before){
            // The disconnected client's own cleanup can close it concurrently.
            // The authoritative check is the final empty context list below.
            try{await e.cdp.send('Target.disposeBrowserContext',{browserContextId:id})}catch(error){}
          }
        const after=(await e.cdp.send('Target.getBrowserContexts')).browserContextIds;
        if(request.op==='cleanup' && after.length)throw Error('Contexts remain');
        console.log(JSON.stringify({id:request.id,before:before.length,remaining:after.length,disabled:false}));
      }catch(error){
        await e.server.kill();e.dead=true;
        console.log(JSON.stringify({id:request.id,remaining:0,disabled:true}));
      }
    }).catch(error=>{console.error(error.stack);process.exit(1)});
  }).on('close',()=>Promise.all(entries.filter(e=>!e.dead).map(e=>e.server.kill())).finally(()=>process.exit(0)));
}
main().catch(error=>{console.error(error.stack);process.exit(1)});
"""


def _identity(pid):
    """Linux process creation identity; never target a reused process ID."""
    try:
        fields=Path(f'/proc/{pid}/stat').read_text().rsplit(') ',1)[1].split()
        return fields[19],int(fields[2]),fields[0]
    except FileNotFoundError:return None


class BrowserPool:
    def __init__(self, directory, size, version, env=None, *, local_test=False):
        if not 1<=size<=4:raise ValueError('Trial pool size must be between one and four')
        if not version.endswith('-performance-lab'):raise ValueError('Lab only')
        if not sys.platform.startswith('linux') and not local_test:raise ValueError('Linux worker only')
        import playwright
        package=Path(playwright.__file__).parent/'driver/package'
        node=package.parent/('node.exe' if os.name=='nt' else 'node')
        self.root=Path(directory).resolve();self.root.mkdir(parents=True,exist_ok=False)
        self.version=version;self.closed=False;self.sequence=0;self.lock=threading.Lock();self.messages=queue.Queue()
        self.log=(self.root/'manager.log').open('wb')
        runtime=os.environ if env is None else env
        # The browser infrastructure needs system paths, never app/DB credentials.
        runtime={k:v for k,v in runtime.items() if k.upper() in {
            'PATH','HOME','TMPDIR','TMP','TEMP','SYSTEMROOT','WINDIR','LOCALAPPDATA','USERPROFILE',
            'PLAYWRIGHT_BROWSERS_PATH','LD_LIBRARY_PATH','FONTCONFIG_PATH','LANG','LC_ALL'}}
        self.process=subprocess.Popen([str(node),'-e',SERVER_SCRIPT,str(package),str(size)],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.log,env=runtime,text=True,
            start_new_session=os.name!='nt',creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        def collect():
            for line in self.process.stdout:
                try:self.messages.put(json.loads(line))
                except ValueError:self.messages.put({'invalid':True})
            self.messages.put({'eof':True})
        self.reader=threading.Thread(target=collect,daemon=True);self.reader.start()
        self.entries=[];self.owned={}
        try:
            end=time.monotonic()+30
            while True:
                ready=self.messages.get(timeout=max(.01,end-time.monotonic()))
                if 'started' not in ready:break
                entry=ready['started'];self.entries.append(entry)
                if sys.platform.startswith('linux'):
                    ident=_identity(entry['pid'])
                    if ident is None or ident[1]!=entry['pid']:raise RuntimeError('Browser process group was not private')
                    self.owned[entry['pid']]=ident[0]
            if not ready.get('ready') or len(ready.get('entries',[]))!=size:raise RuntimeError('Browser pool startup failed')
            self.entries=ready['entries']
            for entry in self.entries:
                parsed=urlsplit(entry['endpoint'])
                if parsed.scheme!='ws' or parsed.hostname not in ('127.0.0.1','localhost'):raise RuntimeError('Browser endpoint is not local')
                if sys.platform.startswith('linux'):
                    ident=_identity(entry['pid'])
                    if ident is None or ident[1]!=entry['pid']:raise RuntimeError('Browser process group was not private')
                    self.owned[entry['pid']]=ident[0]
            self.config=self.root/'config.json'
            self.config.write_text(json.dumps({'version':version,'entries':self.entries}),encoding='utf-8')
        except BaseException:
            self.close();raise

    def command(self, op, index=None, timeout=5):
        with self.lock:
            self.sequence+=1;ident=self.sequence
            self.process.stdin.write(json.dumps({'id':ident,'op':op,'index':index})+'\n');self.process.stdin.flush()
            response=self.messages.get(timeout=timeout)
            if response.get('id')!=ident:raise RuntimeError('Pool cleanup not acknowledged')
            return response

    def owner(self, path, token, job_id):
        if not re.fullmatch(r'[a-f0-9-]{36}',token):raise ValueError('Invalid job capability')
        path=Path(path)
        path.write_text(json.dumps({'token':token,'job_id':job_id,'version':self.version}),encoding='utf-8')
        return {'CE_LAB_BROWSER_POOL_CONFIG':str(self.config),'CE_LAB_BROWSER_POOL_OWNER':str(path)}

    def release(self, owner_path):
        """Caller must stop/reap the job's process tree first."""
        owner=json.loads(Path(owner_path).read_text(encoding='utf-8'))
        for entry in self.entries:
            lease=self.root/(str(entry['index'])+'.lease')
            if not lease.exists():continue
            held=json.loads(lease.read_text(encoding='utf-8'))
            if held!=owner:continue
            proof=self.command('cleanup',entry['index'])
            if proof.get('remaining')!=0:raise RuntimeError('Leased browser still has contexts')
            if proof.get('disabled'):
                self.confirm_stopped(entry)
                (self.root/(str(entry['index'])+'.disabled')).touch()
            lease.unlink()

    def confirm_stopped(self, entry):
        """An acknowledged browser kill must also stop its Linux descendants."""
        if not sys.platform.startswith('linux'):return
        from deployment.queue_worker import group_running
        end=time.monotonic()+3
        while group_running(entry['pid']):
            if time.monotonic()>=end:raise RuntimeError('Disabled browser descendants still alive')
            time.sleep(.05)

    def close(self):
        if self.closed:return
        try:
            if self.process.poll() is None:
                try:self.command('close',timeout=8)
                except Exception:
                    if os.name=='nt':
                        subprocess.run(['taskkill','/PID',str(self.process.pid),'/T','/F'],capture_output=True,timeout=10)
                    else:
                        try:os.killpg(self.process.pid,signal.SIGKILL)
                        except ProcessLookupError:pass
                self.process.wait(timeout=10)
            if sys.platform.startswith('linux'):
                from deployment.queue_worker import group_running
                for pid,created in self.owned.items():
                    current=_identity(pid)
                    if current and (current[0]!=created or current[1]!=pid):
                        raise RuntimeError('Refusing to target a reused browser process ID')
                    if group_running(pid):
                        try:os.killpg(pid,signal.SIGKILL)
                        except ProcessLookupError:pass
                end=time.monotonic()+5
                while time.monotonic()<end:
                    alive=[pid for pid in self.owned if group_running(pid)]
                    if not alive:break
                    time.sleep(.05)
                if alive:raise RuntimeError('Browser pool termination not confirmed')
            self.closed=True
        finally:
            self.reader.join(timeout=2)
            if self.process.stdin:self.process.stdin.close()
            if not self.reader.is_alive() and self.process.stdout:self.process.stdout.close()
            self.log.close()


def leased_browser(playwright, kwargs):
    """Acquire only a worker-issued local lease; unsupported launch args retain private launch."""
    if kwargs.get('headless') is not True or set(kwargs)-{'headless','timeout'}:return None
    config=os.environ.get('CE_LAB_BROWSER_POOL_CONFIG','');owner_path=os.environ.get('CE_LAB_BROWSER_POOL_OWNER','')
    if not config or not owner_path or not os.environ.get('CE_APP_VERSION','').endswith('-performance-lab'):return None
    try:
        path=Path(config).resolve();root=path.parent
        if path.name!='config.json' or not root.name.startswith('cc-lab-browser-'):return None
        settings=json.loads(path.read_text(encoding='utf-8'));owner=json.loads(Path(owner_path).read_text(encoding='utf-8'))
        if settings['version']!=os.environ['CE_APP_VERSION'] or owner['version']!=settings['version']:return None
        if not re.fullmatch(r'[a-f0-9-]{36}',owner['token']):return None
        for entry in settings['entries']:
            index=entry['index']
            if not isinstance(index,int) or not 0<=index<4:continue
            if (root/(str(index)+'.disabled')).exists():continue
            url=urlsplit(entry['endpoint'])
            if url.scheme!='ws' or url.hostname not in ('127.0.0.1','localhost') or url.username or url.password:continue
            lease=root/(str(index)+'.lease')
            try:os.link(owner_path,lease)
            except FileExistsError:
                if json.loads(lease.read_text(encoding='utf-8'))!=owner:continue
            # Failure retains the lease for supervisor cleanup. It cannot be
            # reassigned while this child could still have a browser connection.
            return playwright.chromium.connect(entry['endpoint'],timeout=min(1000,kwargs.get('timeout',1000)))
    except Exception as exc:
        print('Lab browser lease fallback: '+type(exc).__name__,file=sys.stderr)
        return None
    return None
