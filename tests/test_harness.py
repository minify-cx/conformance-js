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
                "minifier": {"name": "Minify++", "version": "1.1.2", "version_string": "Minify++ 1.1.2", "commit": "a"*40},
                "oracle": {"name": "o", "version": "1"}, "generated_at": "2026-01-01T00:00:00Z"}
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            (td/"res.json").write_text(json.dumps(base))
            (td/"pub.json").write_text(json.dumps(base))
            (td/"index.html").write_text("<h1>ok</h1>")
            h.verify_dashboard(td/"res.json", td/"index.html", td/"pub.json")
            bad = dict(base); bad["minifier"] = {"name": "Minify++", "version": "1.1.1", "commit": "b"*40}
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



    def test_combine_propagates_identity(self):
        import json, tempfile
        base = {
            "schema_version": 1, "format": "javascript",
            "source_revisions": {"test262": {"revision": "r"}}, "runtime": "v22.0.0",
            "minifier": {"name": "Minify++", "version": "1.1.2", "version_string": "Minify++ 1.1.2", "commit": "a"*40},
            "oracle": {"name": "nodejs", "version": "v22.0.0"},
            "shard": {"index": 0, "count": 2}, "corpus_total": 0, "duration_seconds": 1.0,
            "counts": {"pass": 2}, "runtime_incompatibilities": {},
            "results": [],
        }
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            for i in (0, 1):
                s = dict(base); s["shard"] = {"index": i, "count": 2}
                (td/f"shard-{i}.json").write_text(json.dumps(s))
            h.combine([td/"shard-0.json", td/"shard-1.json"], td/"combined.json")
            out = json.loads((td/"combined.json").read_text())
            self.assertEqual(out["minifier"], base["minifier"])
            self.assertEqual(out["oracle"], base["oracle"])



def test_validate_identity_rejects_incomplete(self):
    import copy
    base = {"minifier": {"name": "Minify++", "version": "1.1.2", "version_string": "Minify++ 1.1.2", "commit": "a"*40},
            "oracle": {"name": "o", "version": "1"}}
    with self.assertRaises(SystemExit): h.validate_identity({"oracle": base["oracle"]})
    with self.assertRaises(SystemExit): h.validate_identity({"minifier": {}, "oracle": base["oracle"]})
    bad = copy.deepcopy(base); bad["minifier"]["version_string"] = ""
    with self.assertRaises(SystemExit): h.validate_identity(bad)
    bad = copy.deepcopy(base); bad["minifier"]["commit"] = "zz"
    with self.assertRaises(SystemExit): h.validate_identity(bad)
    bad = copy.deepcopy(base); bad["oracle"] = {"name": "x"}
    with self.assertRaises(SystemExit): h.validate_identity(bad)
    with self.assertRaises(SystemExit): h.validate_identity(base, expected_commit="f"*40)

def test_dashboard_rejects_matching_empty_identity(self):
    import tempfile
    empty = {"counts": {"pass": 1}, "source_revisions": {}, "minifier": {}, "oracle": {}, "generated_at": "2026-01-01T00:00:00Z"}
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        (td/"res.json").write_text(json.dumps(empty))
        (td/"pub.json").write_text(json.dumps(empty))
        (td/"index.html").write_text("<h1>ok</h1>")
        with self.assertRaises(SystemExit):
            h.verify_dashboard(td/"res.json", td/"index.html", td/"pub.json")

if __name__=='__main__': unittest.main()
