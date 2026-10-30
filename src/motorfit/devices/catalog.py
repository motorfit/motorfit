"""MotorFit's native acquisition coverage, independent of external device SDKs."""

import argparse
import json

CATALOG = {
    "robstride": {
        "models": [f"rs{i:02d}" for i in range(7)],
        "transport": "SocketCAN",
        "bam_record_fit": True,
        "hardware_validated_models": ["rs05"],
        "notes": "Private extended-CAN protocol. RS05 has a measured reference study.",
    },
    "damiao": {
        "models": [
            "3507",
            "4310",
            "4310p",
            "4340",
            "4340p",
            "4340_v20",
            "6006",
            "8006",
            "8009",
            "10010l",
            "10010",
            "h3510",
            "g6215",
            "h6220",
            "jh11",
            "6248p",
        ],
        "transport": "SocketCAN",
        "bam_record_fit": True,
        "hardware_validated_models": [],
        "notes": "MIT protocol; software-tested. Profile 4340_v20 refers to 4340X.",
    },
}


def list_motors(arguments):
    parser = argparse.ArgumentParser(description="MotorFit native models and validation coverage")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(arguments)
    if args.json:
        print(json.dumps(dict(families=CATALOG), indent=2))
        return
    for family, info in CATALOG.items():
        print(f"{family}: {', '.join(info['models'])}\n  {info['notes']}")
    print("Profiles are software support; only RS05 has hardware validation here.")
