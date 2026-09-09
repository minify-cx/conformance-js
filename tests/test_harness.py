import importlib.util,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; spec=importlib.util.spec_from_file_location('h',ROOT/'tools/conformance.py'); h=importlib.util.module_from_spec(spec); spec.loader.exec_module(h)
class Tests(unittest.TestCase):
 def test_metadata(self):
  m=h.metadata('/*---\nflags: [onlyStrict]\nincludes: [compareArray.js]\nfeatures: [BigInt]\n---*/'); self.assertEqual(m['flags'],['onlyStrict']); self.assertEqual(m['includes'],['compareArray.js'])
 def test_eligibility(self):
  self.assertEqual(h.eligibility('',{'negative':True}),'negative-test'); self.assertEqual(h.eligibility('',{'flags':['module']}),'module'); self.assertEqual(h.eligibility('$DONE()',{}),'host-api'); self.assertIsNone(h.eligibility('1+1',{}))
if __name__=='__main__': unittest.main()
