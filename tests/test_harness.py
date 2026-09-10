import importlib.util,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; spec=importlib.util.spec_from_file_location('h',ROOT/'tools/conformance.py'); h=importlib.util.module_from_spec(spec); spec.loader.exec_module(h)
class Tests(unittest.TestCase):
 def test_metadata(self):
  m=h.metadata('/*---\nflags:\n  - onlyStrict\nincludes: [compareArray.js]\nfeatures: [BigInt]\n---*/'); self.assertEqual(m['flags'],['onlyStrict']); self.assertEqual(m['includes'],['compareArray.js'])
 def test_eligibility(self):
  self.assertEqual(h.eligibility('',{'negative':True}),'negative-test'); self.assertEqual(h.eligibility('',{'flags':['module']}),'module'); self.assertEqual(h.eligibility('$262.agent.start()',{}),'agent-host-api'); self.assertIsNone(h.eligibility('$DONE()',{'flags':['async']})); self.assertIsNone(h.eligibility('1+1',{})); self.assertEqual(h.eligibility('',{'_missing':True}),'missing-frontmatter-or-fixture')
  self.assertEqual(h.eligibility('',{},'test/built-ins/Function/prototype/toString/function.js'),'source-text-introspection')


class IdentityTests(unittest.TestCase):
    def test_parser_oracle_identity(self):
        o = h.oracle_identity("node") if hasattr(h, "oracle_identity") else h.parser_identity()
        self.assertIn("name", o)
        self.assertTrue(o.get("version"))

    def test_dashboard_identity_propagation(self):
        import json, tempfile
        base = {"counts": {"pass": 1}, "source_revisions": {},
                "minifier": {"name": "Minify++", "version": "1.1.2", "commit": "x"*40},
                "oracle": {"name": "o", "version": "1"}, "generated_at": "2026-01-01T00:00:00Z"}
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            (td/"res.json").write_text(json.dumps(base))
            (td/"pub.json").write_text(json.dumps(base))
            (td/"index.html").write_text("<h1>ok</h1>")
            h.verify_dashboard(td/"res.json", td/"index.html", td/"pub.json")
            bad = dict(base); bad["minifier"] = {"name": "Minify++", "version": "1.1.1", "commit": "y"*40}
            (td/"pub.json").write_text(json.dumps(bad))
            with self.assertRaises(SystemExit):
                h.verify_dashboard(td/"res.json", td/"index.html", td/"pub.json")

    def test_minifier_identity_reads_git_commit(self):
        import subprocess, tempfile
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            subprocess.run(["git", "init", "-q"], cwd=td, check=True)
            subprocess.run(["git", "config", "user.email", "t@t"], cwd=td, check=True)
            subprocess.run(["git", "config", "user.name", "t"], cwd=td, check=True)
            exe = td/"minify"
            exe.write_text("#!/bin/sh\necho 'Minify++ 1.1.2'\n")
            exe.chmod(0o755)
            subprocess.run(["git", "add", "minify"], cwd=td, check=True)
            subprocess.run(["git", "commit", "-qm", "c"], cwd=td, check=True)
            ident = h.minifier_identity(exe)
            self.assertEqual(ident["name"], "Minify++")
            self.assertEqual(ident["version"], "1.1.2")
            self.assertTrue(ident["commit"])

if __name__=='__main__': unittest.main()
