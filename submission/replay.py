"""One-command evaluator replay; no personal API key or network required."""
import sys
from pathlib import Path
from ott_agent.__main__ import main

if __name__=='__main__':
    root=Path(__file__).resolve().parent
    sys.argv[1:]=['replay','--pack',str(root.parent),'--out',str(root/'runs/evaluator'),
        '--env-file',str(root/'.env'),'--provider','recorded',*sys.argv[1:]]
    raise SystemExit(main())
