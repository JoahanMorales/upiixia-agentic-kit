#!/usr/bin/env python3
"""UAK-901: validate paired visual-reference scores and real captures offline."""
import json
import struct
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path

from test_hack import expect

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "visual_reference_eval.py"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def png_chunk(kind, content):
    return struct.pack(">I", len(content)) + kind + content + struct.pack(">I", zlib.crc32(kind + content) & 0xFFFFFFFF)


def tiny_png():
    return (PNG_SIGNATURE + png_chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)) +
            png_chunk(b"IDAT", zlib.compress(b"\0\0\0\0\0")) + png_chunk(b"IEND", b""))


def make_manifest(tmp, pairs):
    root = Path(tmp)
    for pair in pairs:
        for arm_name in ("baseline", "reference"):
            captures = pair[arm_name].get("captures", {})
            for kind, name in (("desktop", "1280.png"), ("mobile", "390.png")):
                path = root / captures.get(kind, "")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(tiny_png())
    manifest = root / "manifest.json"
    manifest.write_text(json.dumps({"version": 1, "pairs": pairs}), encoding="utf-8")
    return manifest


def arm(root, key, score, tokens=10):
    return {"score": score, "captures": {"desktop": "captures/%s/1280.png" % key,
            "mobile": "captures/%s/390.png" % key}, "tokens": tokens,
            **({"source": {"kind": "human", "id": "local"}} if key.startswith("R") else {})}


def run_eval(manifest):
    return subprocess.run([sys.executable, str(SCRIPT), str(manifest)], capture_output=True, text=True)


def scores_paired_real_captures():
    with tempfile.TemporaryDirectory() as tmp:
        pairs = [{"brief": "one", "seed": 17, "baseline": arm(tmp, "A1", 3), "reference": arm(tmp, "R1", 4)},
                 {"brief": "two", "seed": 18, "baseline": arm(tmp, "A2", 4), "reference": arm(tmp, "R2", 4)}]
        result = run_eval(make_manifest(tmp, pairs))
        expect(result.returncode == 0, result.stderr)
        report = json.loads(result.stdout)
        expect(report["wins"] == 1 and report["ties"] == 1, str(report))
        expect([p["score_difference"] for p in report["pairs"]] == [1, 0], str(report))
        (Path(tmp) / "captures/A1/1280.png").write_bytes(b"not a png")
        expect(run_eval(Path(tmp) / "manifest.json").returncode != 0, "non-PNG capture accepted")
        (Path(tmp) / "captures/A1/1280.png").write_bytes(PNG_SIGNATURE)
        expect(run_eval(Path(tmp) / "manifest.json").returncode != 0, "truncated PNG accepted")
    return "one win and one tie"


def refuses_missing_or_synthetic_captures():
    with tempfile.TemporaryDirectory() as tmp:
        pair = {"brief": "one", "seed": 1, "baseline": arm(tmp, "A1", 3), "reference": arm(tmp, "R1", 4)}
        manifest = make_manifest(tmp, [pair])
        (Path(tmp) / "captures/R1/390.png").unlink()
        expect(run_eval(manifest).returncode != 0, "missing mobile capture accepted")
        (Path(tmp) / "captures/R1/390.png").write_bytes(tiny_png())
        pair["reference"]["captures"]["mobile"] = ".uak-shots/visual-reference/390.png"
        (Path(tmp) / ".uak-shots/visual-reference").mkdir(parents=True)
        (Path(tmp) / ".uak-shots/visual-reference/390.png").write_bytes(tiny_png())
        manifest.write_text(json.dumps({"version": 1, "pairs": [pair]}), encoding="utf-8")
        expect(run_eval(manifest).returncode != 0, "synthetic capture accepted")
        pair["reference"]["captures"]["mobile"] = "captures/R1/390.png"
        with tempfile.TemporaryDirectory(dir=str(Path(tmp).parent)) as outside_tmp:
            outside = Path(outside_tmp)
            (outside / "1280.png").write_bytes(tiny_png())
            pair["reference"]["captures"]["desktop"] = "../%s/1280.png" % outside.name
            manifest.write_text(json.dumps({"version": 1, "pairs": [pair]}), encoding="utf-8")
            expect(run_eval(manifest).returncode != 0, "capture outside manifest directory accepted")
            pair["reference"]["captures"]["desktop"] = "captures/R1/1280.png"
            (Path(tmp) / "captures/R1/1280.png").unlink()
            (Path(tmp) / "captures/R1/1280.png").symlink_to(outside / "1280.png")
            manifest.write_text(json.dumps({"version": 1, "pairs": [pair]}), encoding="utf-8")
            expect(run_eval(manifest).returncode != 0, "symlink outside manifest directory accepted")
    return "missing and synthetic captures rejected"


def refuses_invalid_or_unpaired_scores():
    with tempfile.TemporaryDirectory() as tmp:
        pair = {"brief": "one", "seed": 1, "baseline": arm(tmp, "A1", 3), "reference": arm(tmp, "R1", 4)}
        manifest = make_manifest(tmp, [pair])
        for score in (0, 3.5):
            pair["baseline"]["score"] = score
            manifest.write_text(json.dumps({"version": 1, "pairs": [pair]}), encoding="utf-8")
            expect(run_eval(manifest).returncode != 0, "invalid score accepted: %s" % score)
        pair["baseline"]["score"] = 3
        del pair["reference"]
        manifest.write_text(json.dumps({"version": 1, "pairs": [pair]}), encoding="utf-8")
        expect(run_eval(manifest).returncode != 0, "unpaired record accepted")
    return "invalid and unpaired records rejected"


def preserves_unknown_token_usage():
    with tempfile.TemporaryDirectory() as tmp:
        pair = {"brief": "one", "seed": 1, "baseline": arm(tmp, "A1", 3, None), "reference": arm(tmp, "R1", 4, 12)}
        result = run_eval(make_manifest(tmp, [pair]))
        expect(result.returncode == 0, result.stderr)
        report = json.loads(result.stdout)
        expect(report["token_totals"]["baseline"] is None, str(report))
        expect(report["token_totals"]["reference"] == 12, str(report))
    return "unknown total remains null"


TESTS = [scores_paired_real_captures, refuses_missing_or_synthetic_captures,
         refuses_invalid_or_unpaired_scores, preserves_unknown_token_usage]


def main():
    if not (ROOT / "install.sh").is_file():
        print("VISUAL_REFERENCE_EVAL_RESULT SKIP source-only evaluator unavailable")
        return 0
    if not SCRIPT.is_file():
        print("VISUAL_REFERENCE_EVAL_RESULT FAIL source-only evaluator missing")
        return 1
    failures = 0
    for test in TESTS:
        try:
            print("PASS %s (%s)" % (test.__name__, test()))
        except Exception as exc:
            failures += 1
            print("FAIL %s (%s)" % (test.__name__, str(exc)[:1500]))
    print("VISUAL_REFERENCE_EVAL_RESULT %s passed=%d failed=%d" % ("PASS" if not failures else "FAIL", len(TESTS) - failures, failures))
    return bool(failures)


if __name__ == "__main__":
    raise SystemExit(main())
