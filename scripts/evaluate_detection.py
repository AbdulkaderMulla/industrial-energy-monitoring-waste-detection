"""Compare rule-based detections with ground-truth labels (labels are read here only)."""
import argparse
import json
from pathlib import Path

import pandas as pd

from app.services.analytics import detect_anomalies, load_data

ROOT = Path(__file__).resolve().parents[1]


def evaluate(data_dir, ground_truth_path):
    gt = pd.read_csv(ground_truth_path)
    findings = detect_anomalies(load_data(data_dir))
    detected = {(f["issue_type"], e) for f in findings for e in f["entity_ids"]}
    expected = set(zip(gt.issue_type, gt.entity_id.astype(str)))
    report = {}
    for issue_type in sorted({t for t, _ in expected} | {t for t, _ in detected}):
        exp = {e for t, e in expected if t == issue_type}
        det = {e for t, e in detected if t == issue_type}
        tp, fp, fn = len(exp & det), len(det - exp), len(exp - det)
        report[issue_type] = {
            "expected": len(exp), "detected": len(det), "true_positive": tp,
            "false_positive": fp, "false_negative": fn,
            "precision": round(tp / (tp + fp), 4) if tp + fp else None,
            "recall": round(tp / (tp + fn), 4) if tp + fn else None,
        }
    totals = {k: sum(v[k] for v in report.values()) for k in ["true_positive", "false_positive", "false_negative"]}
    return {"per_issue_type": report, "totals": totals}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data" / "raw")
    parser.add_argument("--ground-truth", type=Path, default=ROOT / "data" / "ground_truth" / "ground_truth.csv")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "processed" / "evaluation_metrics.json")
    args = parser.parse_args()
    result = evaluate(args.data_dir, args.ground_truth)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
