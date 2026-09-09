import importlib.util,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; spec=importlib.util.spec_from_file_location('h',ROOT/'tools/conformance.py'); h=importlib.util.module_from_spec(spec); spec.loader.exec_module(h)
class Tests(unittest.TestCase):
 def test_metadata(self):
  m=h.metadata('/*---\nflags:\n  - onlyStrict\nincludes: [compareArray.js]\nfeatures: [BigInt]\n---*/'); self.assertEqual(m['flags'],['onlyStrict']); self.assertEqual(m['includes'],['compareArray.js'])
 def test_eligibility(self):
  self.assertEqual(h.eligibility('',{'negative':True}),'negative-test'); self.assertEqual(h.eligibility('',{'flags':['module']}),'module'); self.assertEqual(h.eligibility('$262.agent.start()',{}),'agent-host-api'); self.assertIsNone(h.eligibility('$DONE()',{'flags':['async']})); self.assertIsNone(h.eligibility('1+1',{})); self.assertEqual(h.eligibility('',{'_missing':True}),'missing-frontmatter-or-fixture')
  self.assertEqual(h.eligibility('',{},'test/built-ins/Function/prototype/toString/function.js'),'source-text-introspection')
if __name__=='__main__': unittest.main()
