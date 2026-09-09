#!/usr/bin/env python3
"""Selected Test262 semantic conformance runner for Minify++."""
import argparse,datetime,hashlib,html,json,re,shutil,subprocess,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; RESULTS=ROOT/'results/latest.json'
def now(): return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z')
def load(p): return json.loads(Path(p).read_text())
def save(p,v): p=Path(p); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n')
def lock():
 p=ROOT/'.state/sources.lock.json'; return load(p) if p.exists() else {}
def sync():
 spec=load(ROOT/'config/sources.json')['test262']; dst=ROOT/spec['path']; dst.parent.mkdir(parents=True,exist_ok=True)
 if dst.exists(): subprocess.run(['git','fetch','--prune','origin',spec['branch']],cwd=dst,check=True); subprocess.run(['git','checkout','--detach','FETCH_HEAD'],cwd=dst,check=True)
 else: subprocess.run(['git','clone','--filter=blob:none','--no-tags',spec['url'],str(dst)],check=True)
 rev=subprocess.check_output(['git','rev-parse','HEAD'],cwd=dst,text=True).strip(); state=lock(); state['test262']={'url':spec['url'],'revision':rev,'synced_at':now()}; save(ROOT/'.state/sources.lock.json',state); print(rev)
def metadata(text):
 m=re.search(r'/\*---(.*?)---\*/',text,re.S)
 if not m: return {}
 block=m.group(1); result={}
 for key in ('flags','features','includes'):
  x=re.search(r'^'+key+r':\s*\[(.*?)\]',block,re.M|re.S)
  if x: result[key]=[v.strip().strip("'\"") for v in x.group(1).split(',') if v.strip()]
 if re.search(r'^negative:',block,re.M): result['negative']=True
 return result
def eligibility(text,meta):
 flags=set(meta.get('flags',[]))
 if meta.get('negative'): return 'negative-test'
 if 'module' in flags: return 'module'
 if 'CanBlockIsFalse' in flags: return 'host-constraint'
 if '$262.' in text or '$DONE' in text or 'agent.' in text: return 'host-api'
 return None
def extract(source,out,limit):
 rows=[]; skipped={}
 for p in sorted((source/'test').rglob('*.js')):
  text=p.read_text(encoding='utf-8'); meta=metadata(text); reason=eligibility(text,meta)
  if reason: skipped[reason]=skipped.get(reason,0)+1; continue
  rel=p.relative_to(source).as_posix(); ident=hashlib.sha256((rel+'\0'+text).encode()).hexdigest()[:16]; rows.append({'id':ident,'suite':'test262','source':rel,'js':text,'flags':meta.get('flags',[]),'includes':meta.get('includes',[])})
  if limit and len(rows)>=limit: break
 out.parent.mkdir(parents=True,exist_ok=True); out.write_text(''.join(json.dumps(r,sort_keys=True)+'\n' for r in rows)); save(out.with_suffix('.summary.json'),{'eligible':len(rows),'skipped':skipped}); print(json.dumps({'eligible':len(rows),'skipped':skipped},sort_keys=True))
def executable(value):
 p=Path(value).expanduser()
 if p.exists(): return p.resolve()
 found=shutil.which(value)
 if not found: raise SystemExit(f'executable not found: {value}')
 return Path(found)
def minify(cases,exe):
 outputs={}; errors={}
 with tempfile.TemporaryDirectory() as td:
  paths=[]
  for i,c in enumerate(cases): p=Path(td)/f'case-{i:06d}.js'; p.write_text(c['js']); paths.append(p)
  cp=subprocess.run([str(exe),*map(str,paths)],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
  for c,p in zip(cases,paths):
   out=p.with_name(p.stem+'.min.js')
   if out.exists(): outputs[c['id']]=out.read_text()
   else: errors[c['id']]=(cp.stderr or cp.stdout or 'no output produced')[-2000:]
 return outputs,errors
def invoke_node(source,case,test262,node,timeout):
 harness=test262/'harness'; pieces=[(harness/'assert.js').read_text(),(harness/'sta.js').read_text()]
 for include in case.get('includes',[]):
  p=harness/include
  if not p.exists(): return {'ok':False,'harness_error':f'missing include: {include}'}
  pieces.append(p.read_text())
 pieces.append(source); script='\n'.join(pieces)
 try:
  cp=subprocess.run([str(node),'--unhandled-rejections=strict','-e',script],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout)
  return {'ok':cp.returncode==0,'exit_code':cp.returncode,'stdout':cp.stdout[-2000:],'stderr':cp.stderr[-2000:]}
 except subprocess.TimeoutExpired: return {'ok':False,'timeout':True}
def invoke_batch(sources,cases,test262,node,timeout):
 harness=test262/'harness'; prepared=[]; missing={}
 for source,case in zip(sources,cases):
  flags=set(case.get('flags',[])); pieces=[] if 'raw' in flags else [(harness/'assert.js').read_text(),(harness/'sta.js').read_text()]
  absent=None
  for include in case.get('includes',[]):
   p=harness/include
   if not p.exists(): absent=f'missing include: {include}'; break
   pieces.append(p.read_text())
  if absent: missing[case['id']]={'ok':False,'harness_error':absent}; prepared.append(''); continue
  if 'onlyStrict' in flags: pieces.append('"use strict";')
  pieces.append(source); prepared.append('\n'.join(pieces))
 runner="""const fs=require('fs'),vm=require('vm');const xs=JSON.parse(fs.readFileSync(process.argv[1],'utf8'));let out=[];for(const code of xs){try{vm.runInNewContext(code,{}, {timeout:Number(process.argv[2])});out.push({ok:true})}catch(e){out.push({ok:false,error:String(e&&e.stack||e)})}}process.stdout.write(JSON.stringify(out));"""
 with tempfile.TemporaryDirectory() as td:
  p=Path(td)/'cases.json'; p.write_text(json.dumps(prepared))
  cp=subprocess.run([str(node),'-e',runner,str(p),str(max(1,int(timeout*1000)))],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=max(30,len(cases)*timeout))
  results=json.loads(cp.stdout)
 for i,c in enumerate(cases):
  if c['id'] in missing: results[i]=missing[c['id']]
 return results
def execute(path,minifier,node,test262,result,timeout):
 cases=[json.loads(x) for x in path.read_text().splitlines() if x.strip()]; started=time.time(); outputs,errors=minify(cases,minifier); originals=invoke_batch([c['js'] for c in cases],cases,test262,node,timeout); transformed=invoke_batch([outputs.get(c['id'],'') for c in cases],cases,test262,node,timeout); rows=[]; counts={}
 for pos,c in enumerate(cases):
  if c['id'] in errors: status='minify-error'; evidence={'error':errors[c['id']]}
  else:
   before=originals[pos]; after=transformed[pos]
   if before.get('harness_error'): status='harness-inapplicable'
   elif before.get('timeout'): status='source-timeout'
   elif not before['ok']: status='source-failed'
   elif after.get('timeout'): status='minified-timeout'
   elif not after['ok']: status='semantic-failure'
   else: status='pass'
   evidence={'before':before,'after':after}
  counts[status]=counts.get(status,0)+1; row={k:c[k] for k in ('id','suite','source','flags','includes')}; row['status']=status
  if status!='pass': row['evidence']=evidence
  rows.append(row)
 payload={'schema_version':1,'format':'javascript','generated_at':now(),'duration_seconds':round(time.time()-started,3),'source_revisions':lock(),'runtime':subprocess.check_output([str(node),'--version'],text=True).strip(),'minifier':{'path':str(minifier)},'total':len(rows),'counts':counts,'results':rows}; save(result,payload); save(ROOT/'results/history'/f'{datetime.datetime.now(datetime.timezone.utc):%Y%m%dT%H%M%SZ}.json',payload); print(json.dumps(counts,sort_keys=True))
 return 1 if any(counts.get(x) for x in ('minify-error','minified-timeout','semantic-failure')) else 0
def dashboard(result):
 data=load(result); cards=''.join(f'<li><strong>{html.escape(k)}</strong><span>{v}</span></li>' for k,v in sorted(data['counts'].items())); bad=[r for r in data['results'] if r['status']!='pass'][:200]
 rows=''.join(f"<tr><td>{html.escape(r['status'])}</td><td>{html.escape(r['source'])}</td><td><code>{r['id']}</code></td></tr>" for r in bad) or '<tr><td colspan="3">No non-pass cases.</td></tr>'
 g=ROOT/'generated/latest.html'; g.parent.mkdir(exist_ok=True); g.write_text(f'<section class="hero"><p class="eyebrow">JavaScript conformance</p><h1>Minify++ against selected Test262</h1><p>{data["total"]} independently sourced executable cases on {html.escape(data["runtime"])}. Generated {data["generated_at"]}.</p></section><ul class="stats">{cards}</ul><section><h2>Non-pass evidence</h2><table><thead><tr><th>Status</th><th>Source</th><th>ID</th></tr></thead><tbody>{rows}</tbody></table></section>')
 shutil.copy2(result,ROOT/'public/results/latest.json'); subprocess.run(['nift','build-all'],cwd=ROOT,check=True)
def main():
 p=argparse.ArgumentParser(); s=p.add_subparsers(dest='cmd',required=True); s.add_parser('sync'); e=s.add_parser('extract-js'); e.add_argument('--source',type=Path,default=ROOT/'.state/upstreams/test262'); e.add_argument('--output',type=Path,default=ROOT/'work/test262-js.jsonl'); e.add_argument('--limit',type=int)
 for name in ('run-js','smoke'):
  q=s.add_parser(name); q.add_argument('--minify-bin',default='../minify/minify'); q.add_argument('--node-bin',default='node'); q.add_argument('--test262',type=Path,default=ROOT/'.state/upstreams/test262'); q.add_argument('--results',type=Path,default=RESULTS); q.add_argument('--timeout',type=float,default=5); q.add_argument('--dashboard',action='store_true')
  if name=='run-js': q.add_argument('--cases',type=Path,default=ROOT/'work/test262-js.jsonl')
 d=s.add_parser('dashboard'); d.add_argument('--results',type=Path,default=RESULTS); a=p.parse_args()
 if a.cmd=='sync': sync(); return 0
 if a.cmd=='extract-js': extract(a.source,a.output,a.limit); return 0
 if a.cmd=='dashboard': dashboard(a.results); return 0
 if a.cmd=='smoke':
  path=ROOT/'work/smoke-js.jsonl'; path.parent.mkdir(exist_ok=True); cases=[{'id':'basic','suite':'smoke','source':'basic','js':'assert.sameValue((()=>{ const x = 2; return x * 3; })(), 6);','flags':[],'includes':[]}]; path.write_text(''.join(json.dumps(x)+'\n' for x in cases)); a.test262=ROOT/'work/smoke-test262'; (a.test262/'harness').mkdir(parents=True,exist_ok=True); (a.test262/'harness/assert.js').write_text('var assert={sameValue:function(a,b){if(!Object.is(a,b))throw new Error("not same")}};'); (a.test262/'harness/sta.js').write_text('')
 else: path=a.cases
 rc=execute(path,executable(a.minify_bin),executable(a.node_bin),a.test262,a.results,a.timeout)
 if a.dashboard: dashboard(a.results)
 return rc
if __name__=='__main__': raise SystemExit(main())
