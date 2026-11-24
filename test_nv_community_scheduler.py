import ast,unittest,os
from unittest.mock import Mock, patch
from pathlib import Path
HERE=Path(__file__).resolve().parent
RELEASE=HERE if (HERE/'main.py').exists() else HERE/'nv_railway_release'
class SchedulerTests(unittest.TestCase):
 def function(self):
  tree=ast.parse((RELEASE/'main.py').read_text());fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='run_community_bot');ns={'_flag_enabled':Mock(return_value=False),'run_script':Mock(),'log':Mock()};exec(compile(ast.Module(body=[fn],type_ignores=[]),'main.py','exec'),ns);return ns
 def test_disabled_never_runs(self):
  ns=self.function();self.assertEqual(ns['run_community_bot'](),'disabled');ns['run_script'].assert_not_called()
 def test_enabled_only_private_entrypoint(self):
  ns=self.function();ns['_flag_enabled'].return_value=True;ns['run_community_bot']();ns['run_script'].assert_called_once_with('nv_community_preview_entrypoint.py','Community Private Preview')
 def test_wrapper_defaults_to_private_preview(self):
  from nv_community_preview_entrypoint import main
  with patch.dict(os.environ,{},clear=True), patch('nv_community_preview_entrypoint.subprocess.run') as run:
   run.return_value.returncode=0
   self.assertEqual(main(),0)
   self.assertIn('--preview',run.call_args.args[0])
 def test_nonexact_approval_stays_private(self):
  from nv_community_preview_entrypoint import main
  with patch.dict(os.environ,{'COMMUNITY_PUBLIC_REPLIES_APPROVED':'yes'},clear=True), patch('nv_community_preview_entrypoint.subprocess.run') as run:
   run.return_value.returncode=0
   self.assertEqual(main(),0)
   self.assertIn('--preview',run.call_args.args[0])
if __name__=='__main__':unittest.main()
