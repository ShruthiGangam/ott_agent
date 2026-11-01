import json
import time
import unittest
from pathlib import Path
started=time.monotonic()
suite=unittest.defaultTestLoader.discover('tests')
result=unittest.TextTestRunner(verbosity=1).run(suite)
report={'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
    'skipped':len(result.skipped),'passed':result.wasSuccessful(),'elapsed_s':round(time.monotonic()-started,3),
    'network_calls':0,'scope':'automated local regression suite; transport/test doubles confined to tests'}
Path('benchmarks').mkdir(exist_ok=True)
Path('benchmarks/test_report.json').write_text(json.dumps(report,indent=2))
raise SystemExit(0 if result.wasSuccessful() else 1)
