"""Generate the same profile twice with one seed and compare every raw and ground-truth checksum."""
import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path

from generator.generate_data import SEED_DEFAULT, build

ROOT = Path(__file__).resolve().parents[1]


def checksums(root):
    files = sorted((root / "raw").glob("*.csv")) + [root / "ground_truth" / "ground_truth.csv"]
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


def verify(profile, seed):
    with tempfile.TemporaryDirectory() as tmp:
        runs = []
        for name in ["run_1", "run_2"]:
            out = Path(tmp) / name
            build(profile, seed, out)
            runs.append(checksums(out))
    mismatched = sorted(k for k in set(runs[0]) | set(runs[1]) if runs[0].get(k) != runs[1].get(k))
    return {"profile": profile, "seed": seed, "files_compared": len(runs[0]),
            "identical": not mismatched, "mismatched_files": mismatched, "sha256_run_1": runs[0]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=["starter", "full"], default="starter")
    parser.add_argument("--seed", type=int, default=SEED_DEFAULT)
    parser.add_argument("--report", type=Path, default=ROOT / "data" / "processed" / "reproducibility_check.json")
    args = parser.parse_args()
    result = verify(args.profile, args.seed)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2))
    print(json.dumps({k: v for k, v in result.items() if k != "sha256_run_1"}, indent=2))
    sys.exit(0 if result["identical"] else 1)


if __name__ == "__main__":
    main()
