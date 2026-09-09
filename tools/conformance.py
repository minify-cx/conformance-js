#!/usr/bin/env python3
"""Selected Test262 semantic conformance runner for Minify++."""
import argparse,datetime,hashlib,html,json,re,shutil,subprocess,tempfile,time,yaml
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; RESULTS=ROOT/'results/latest.json'
def now(): return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z')
def load(p): return json.loads(Path(p).read_text())
def save(p,v): p=Path(p); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n')
def lock():
 p=ROOT/'.state/sources.lock.json'; return load(p) if p.exists() else {}
def actual_revisions():
 # Record the revision actually checked out for each configured source. The
 # sync lock records what `sync` last checked out, which is stale when a
 # corpus is pinned manually to reproduce a retained checkpoint; results must
 # carry the revision the extraction truly used.
 state={}; spec=load(ROOT/'config/sources.json')
 for name,s in spec.items():
  dst=ROOT/s['path']; old=lock().get(name,{})
  if (dst/'.git').exists():
   try: rev=subprocess.check_output(['git','rev-parse','HEAD'],cwd=dst,text=True).strip()
   except Exception: rev=old.get('revision','')
   state[name]={'url':s.get('url',old.get('url','')),'revision':rev,'synced_at':old.get('synced_at',now())}
 return state
def sync():
 spec=load(ROOT/'config/sources.json')['test262']; dst=ROOT/spec['path']; dst.parent.mkdir(parents=True,exist_ok=True)
 if dst.exists(): subprocess.run(['git','fetch','--prune','origin',spec['branch']],cwd=dst,check=True); subprocess.run(['git','checkout','--detach','FETCH_HEAD'],cwd=dst,check=True)
 else: subprocess.run(['git','clone','--filter=blob:none','--no-tags',spec['url'],str(dst)],check=True)
 rev=subprocess.check_output(['git','rev-parse','HEAD'],cwd=dst,text=True).strip(); state=lock(); state['test262']={'url':spec['url'],'revision':rev,'synced_at':now()}; save(ROOT/'.state/sources.lock.json',state); print(rev)
def metadata(text):
 m=re.search(r'/\*---(.*?)---\*/',text,re.S)
 if not m: return {'_missing':True}
 raw=yaml.safe_load(m.group(1)) or {}; result={}
 for key in ('flags','features','includes'): result[key]=list(raw.get(key) or [])
 if raw.get('negative') is not None: result['negative']=True
 return result
def eligibility(text,meta,source=''):
 flags=set(meta.get('flags',[]))
 if meta.get('_missing'): return 'missing-frontmatter-or-fixture'
 if meta.get('negative'): return 'negative-test'
 if '/Function/prototype/toString/' in source or source in {
  'test/staging/sm/async-functions/toString.js',
  'test/staging/sm/class/parenExprToString.js',
  'test/staging/sm/generators/runtime.js'}: return 'source-text-introspection'
 if 'module' in flags: return 'module'
 if 'CanBlockIsFalse' in flags: return 'host-constraint'
 if '$262.agent' in text or 'agent.' in text: return 'agent-host-api'
 if '$262.IsHTMLDDA' in text: return 'html-dda-host-api'
 return None
def extract(source,out,limit):
 rows=[]; skipped={}
 for p in sorted((source/'test').rglob('*.js')):
  text=p.read_text(encoding='utf-8'); meta=metadata(text); rel=p.relative_to(source).as_posix(); reason='test-fixture' if p.name.endswith('_FIXTURE.js') else eligibility(text,meta,rel)
  if reason: skipped[reason]=skipped.get(reason,0)+1; continue
  ident=hashlib.sha256((rel+'\0'+text).encode()).hexdigest()[:16]; rows.append({'id':ident,'suite':'test262','source':rel,'js':text,'flags':meta.get('flags',[]),'features':meta.get('features',[]),'includes':meta.get('includes',[])})
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
  entries=[]
  for i,c in enumerate(cases): p=Path(td)/f'case-{i:06d}.js'; p.write_text(c['js']); entries.append((c,p))
  def group(items):
   cp=subprocess.run([str(exe),*[str(p) for _,p in items]],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
   produced=[(c,p,p.with_name(p.stem+'.min.js')) for c,p in items]
   if cp.returncode==0 and all(out.exists() for _,_,out in produced):
    for c,_,out in produced: outputs[c['id']]=out.read_text()
   elif len(items)>1:
    mid=len(items)//2; group(items[:mid]); group(items[mid:])
   else:
    c,_,out=produced[0]
    if out.exists(): outputs[c['id']]=out.read_text()
    else: errors[c['id']]=(cp.stderr or cp.stdout or 'no output produced')[-2000:]
  for start in range(0,len(entries),500): group(entries[start:start+500])
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
 if len(cases)>200:
  results=[]
  for start in range(0,len(cases),200):
   results.extend(invoke_batch(sources[start:start+200],cases[start:start+200],test262,node,timeout))
  return results
 harness=test262/'harness'; prepared=[]; missing={}
 for source,case in zip(sources,cases):
  flags=set(case.get('flags',[])); pieces=[] if 'raw' in flags else [(harness/'assert.js').read_text(),(harness/'sta.js').read_text()]
  absent=None
  for include in case.get('includes',[]):
   p=harness/include
   if not p.exists(): absent=f'missing include: {include}'; break
   pieces.append(p.read_text())
  if absent: missing[case['id']]={'ok':False,'harness_error':absent}; prepared.append(''); continue
  code='\n'.join(pieces+[source]); prepared.append({'code':('"use strict";\n'+code) if 'onlyStrict' in flags else code,'async':'async' in flags,'timeout_ms':max(1,int(timeout*1000))})
 with tempfile.TemporaryDirectory() as td:
  p=Path(td)/'cases.json'; p.write_text(json.dumps(prepared))
  try:
   cp=subprocess.run([str(node),'--expose-gc',str(ROOT/'tools/node_runner.js'),str(p)],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=max(30,len(cases)*timeout))
  except subprocess.TimeoutExpired:
   if len(cases)>1:
    mid=len(cases)//2
    return invoke_batch(sources[:mid],cases[:mid],test262,node,timeout)+invoke_batch(sources[mid:],cases[mid:],test262,node,timeout)
   return [{'ok':False,'runner_crash':True,'timeout':True,'error':'Node runner timeout'}]
  if cp.returncode:
   if len(cases)>1:
    mid=len(cases)//2
    return invoke_batch(sources[:mid],cases[:mid],test262,node,timeout)+invoke_batch(sources[mid:],cases[mid:],test262,node,timeout)
   return [{'ok':False,'runner_crash':True,'error':cp.stderr or f'Node runner exited {cp.returncode}'}]
  results=json.loads(cp.stdout)
 for i,c in enumerate(cases):
  if c['id'] in missing: results[i]=missing[c['id']]
 return results
def runtime_reason(result,case):
 error=result.get('error','')
 if result.get('harness_error'): return 'missing-harness-include'
 if result.get('runner_crash'): return 'runtime-process-failure'
 if result.get('timeout'): return 'runtime-timeout'
 if '$262' in error and ('not defined' in error or 'not a function' in error): return 'unsupported-host-api'
 if 'SyntaxError' in error: return 'unsupported-syntax'
 if 'immutable-arraybuffer' in case.get('features',[]): return 'unsupported-feature:immutable-arraybuffer'
 if 'legacy-regexp' in case.get('features',[]): return 'runtime-divergence:legacy-regexp'
 features=case.get('features',[])
 if 'Temporal' in features: return 'unsupported-feature:Temporal'
 if 'dynamic-import' in features: return 'unsupported-harness:dynamic-import'
 if features: return 'declared-feature:'+str(features[0])
 if '/annexB/language/function-code/' in case.get('source',''): return 'runtime-divergence:annex-b-block-functions'
 if 'Test262Error' in error: return 'runtime-semantics'
 return 'runtime-execution'
def execute(path,minifier,node,test262,result,timeout,shard_index=0,shard_count=1):
 all_cases=[json.loads(x) for x in path.read_text().splitlines() if x.strip()]; cases=[c for pos,c in enumerate(all_cases) if pos%shard_count==shard_index]; started=time.time(); outputs,errors=minify(cases,minifier); originals=invoke_batch([c['js'] for c in cases],cases,test262,node,timeout); transformed=invoke_batch([outputs.get(c['id'],'') for c in cases],cases,test262,node,timeout); rows=[]; counts={}
 for pos,c in enumerate(cases):
  if c['id'] in errors: status='minify-error'; evidence={'error':errors[c['id']]}
  else:
   before=originals[pos]; after=transformed[pos]
   if before.get('harness_error'): status='harness-inapplicable'
   elif before.get('timeout'): status='runtime-inapplicable'
   elif not before['ok']: status='runtime-inapplicable'
   elif after.get('timeout'): status='minified-timeout'
   elif not after['ok']: status='semantic-failure'
   else: status='pass'
   evidence={'before':before,'after':after}
   if status=='runtime-inapplicable': evidence['runtime_reason']=runtime_reason(before,c)
  counts[status]=counts.get(status,0)+1; row={k:c[k] for k in ('id','suite','source','flags','features','includes')}; row['status']=status
  if status!='pass': row['evidence']=evidence
  if status in {'minify-error','minified-timeout','semantic-failure'}: row.update(input=c['js'],output=outputs.get(c['id']))
  rows.append(row)
 incompatibilities={}
 for row in rows:
  if row['status']=='runtime-inapplicable':
   reason=row['evidence']['runtime_reason']; incompatibilities[reason]=incompatibilities.get(reason,0)+1
 payload={'schema_version':1,'format':'javascript','generated_at':now(),'duration_seconds':round(time.time()-started,3),'source_revisions':actual_revisions(),'runtime':subprocess.check_output([str(node),'--version'],text=True).strip(),'minifier':{'path':str(minifier)},'corpus_total':len(all_cases),'shard':{'index':shard_index,'count':shard_count},'total':len(rows),'counts':counts,'runtime_incompatibilities':incompatibilities,'results':rows}; save(result,payload); print(json.dumps({'counts':counts,'runtime_incompatibilities':incompatibilities},sort_keys=True))
 return 1 if any(counts.get(x) for x in ('minify-error','minified-timeout','semantic-failure')) else 0
def combine(paths,result):
 parts=[load(p) for p in paths]
 if not parts: raise SystemExit('no shard results supplied')
 count=parts[0]['shard']['count']; indices={p['shard']['index'] for p in parts}
 if len(parts)!=count or indices!=set(range(count)): raise SystemExit(f'incomplete shard set: have {sorted(indices)}, expected 0..{count-1}')
 for p in parts[1:]:
  if p['source_revisions']!=parts[0]['source_revisions'] or p['runtime']!=parts[0]['runtime']: raise SystemExit('shard environment mismatch')
 rows=[]; counts={}; incompat={}
 for p in parts:
  rows.extend(p['results'])
  for k,v in p['counts'].items(): counts[k]=counts.get(k,0)+v
  for row in p['results']:
   if row['status']=='runtime-inapplicable':
    reason=runtime_reason(row['evidence']['before'],row); row['evidence']['runtime_reason']=reason; incompat[reason]=incompat.get(reason,0)+1
 payload={k:parts[0][k] for k in ('schema_version','format','source_revisions','runtime','minifier')}; payload.update(generated_at=now(),duration_seconds=round(sum(p['duration_seconds'] for p in parts),3),total=len(rows),counts=counts,runtime_incompatibilities=incompat,results=rows)
 if len(rows)!=parts[0]['corpus_total']: raise SystemExit('combined result does not cover corpus')
 save(result,payload); save(ROOT/'results/history'/f'{datetime.datetime.now(datetime.timezone.utc):%Y%m%dT%H%M%SZ}.json',payload); print(json.dumps({'counts':counts,'runtime_incompatibilities':incompat},sort_keys=True))
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
  if name=='run-js': q.add_argument('--cases',type=Path,default=ROOT/'work/test262-js.jsonl'); q.add_argument('--shard-index',type=int,default=0); q.add_argument('--shard-count',type=int,default=1)
 c=s.add_parser('combine'); c.add_argument('shards',nargs='+',type=Path); c.add_argument('--results',type=Path,default=RESULTS)
 d=s.add_parser('dashboard'); d.add_argument('--results',type=Path,default=RESULTS); a=p.parse_args()
 if a.cmd=='sync': sync(); return 0
 if a.cmd=='extract-js': extract(a.source,a.output,a.limit); return 0
 if a.cmd=='dashboard': dashboard(a.results); return 0
 if a.cmd=='combine': return combine(a.shards,a.results)
 if a.cmd=='smoke':
  path=ROOT/'work/smoke-js.jsonl'; path.parent.mkdir(exist_ok=True); cases=[{'id':'basic','suite':'smoke','source':'basic','js':'assert.sameValue((()=>{ const x = 2; return x * 3; })(), 6);','flags':[],'includes':[]}]; path.write_text(''.join(json.dumps(x)+'\n' for x in cases)); a.test262=ROOT/'work/smoke-test262'; (a.test262/'harness').mkdir(parents=True,exist_ok=True); (a.test262/'harness/assert.js').write_text('var assert={sameValue:function(a,b){if(!Object.is(a,b))throw new Error("not same")}};'); (a.test262/'harness/sta.js').write_text('')
 else: path=a.cases
 rc=execute(path,executable(a.minify_bin),executable(a.node_bin),a.test262,a.results,a.timeout,getattr(a,'shard_index',0),getattr(a,'shard_count',1))
 if a.dashboard: dashboard(a.results)
 return rc
if __name__=='__main__': raise SystemExit(main())
