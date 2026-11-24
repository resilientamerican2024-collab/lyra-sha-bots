"""Existing-host entrypoint: private intended replies only, never public dispatch."""
import os,subprocess,sys
from pathlib import Path
if __name__=='__main__':
    here=Path(__file__).resolve().parent
    source=Path(os.environ.get('COMMUNITY_META_CONFIG_PATH',str(here/'review_bot_config.json')))
    result=subprocess.run([sys.executable,str(here/'nv_community_runtime.py'),'--preview','--config',str(source)],check=False)
    raise SystemExit(result.returncode)
