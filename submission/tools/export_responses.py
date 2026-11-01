"""Export readable reasons from saved decisions without changing historical evidence."""
import argparse
import json
from pathlib import Path
from ott_agent.explanations import export_responses

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(export_responses(args.run)))
