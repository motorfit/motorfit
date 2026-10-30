"""Portable datasets: immutable recordings, explicit relative paths and hashes."""

import hashlib
import json
from collections import Counter
from pathlib import Path


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


class Dataset:
    """Paths resolve against the manifest, never the process working directory.

    Historical absolute paths inside raw JSON are provenance only. Current
    readers use this manifest and verify content before using it.
    """

    def __init__(self, manifest):
        self.path = Path(manifest).resolve()
        self.root = self.path.parent
        self.metadata = json.loads(self.path.read_text())
        if self.metadata.get("schema_version") != 1:
            raise ValueError("Unsupported dataset schema")
        self.rows = self.metadata["records"]
        if not self.rows or len({r["id"] for r in self.rows}) != len(self.rows):
            raise ValueError("Expected nonempty records with unique IDs")
        self.model_path = self.resolve(self.metadata["model_path"])
        self.check(self.model_path, self.metadata["model_sha256"])
        if dict(Counter(r["split"] for r in self.rows)) != self.metadata["split_counts"]:
            raise ValueError("Dataset split counts do not match the manifest")

    def resolve(self, relative):
        path = Path(relative)
        if path.is_absolute():
            raise ValueError(f"Dataset paths must be relative: {relative}")
        return (self.root / path).resolve()

    @staticmethod
    def check(path, expected):
        if sha256(path) != expected:
            raise ValueError(f"SHA-256 mismatch: {path}")

    def log(self, row, raw=False):
        path = self.resolve(row["raw_path" if raw else "processed_path"])
        self.check(path, row["raw_sha256" if raw else "sha256"])
        value = json.loads(path.read_text())
        if value["motor_uid"] != self.metadata["motor_uid"] or value["split"] != row["split"]:
            raise ValueError(f"Recording identity/split mismatch: {row['id']}")
        return value

    def reference(self, row):
        import numpy as np

        path = self.resolve(row["reference_path"])
        self.check(path, row["reference_sha256"])
        with np.load(path, allow_pickle=False) as saved:
            return saved["prediction"].copy()

    def record_dir(self, row):
        directory = self.resolve(row["record_path"])
        for name, digest in row["source_sha256"].items():
            self.check(directory / name, digest)
        return directory

    def verify(self):
        samples = 0
        for row in self.rows:
            self.log(row)
            samples += len(self.log(row, raw=True)["entries"])
            self.reference(row)
            if "record_path" in row:
                self.record_dir(row)
        if samples != self.metadata["formal_raw_samples"]:
            raise ValueError("Raw sample count differs from manifest")
        return {
            "records": len(self.rows),
            "raw_samples": samples,
            "splits": self.metadata["split_counts"],
            "model_sha256": sha256(self.model_path),
            "all_hashes_match": True,
        }
