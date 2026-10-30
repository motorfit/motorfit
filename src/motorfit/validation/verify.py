"""Verify model, recordings, acquisition evidence and saved references."""

import argparse
import json
from pathlib import Path

from motorfit.dataset import Dataset, save_json


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = Dataset(args.dataset).verify()
    if args.output:
        if args.output.exists():
            raise FileExistsError(args.output)
        save_json(args.output, result)
    print(json.dumps(result, indent=2))
