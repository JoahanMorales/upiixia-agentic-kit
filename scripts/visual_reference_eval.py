#!/usr/bin/env python3
"""Compare paired visual-reference design captures from an offline JSON manifest."""
import json
from pathlib import Path
import struct
import sys
import zlib


def validate_arm(arm, name, root):
    if not isinstance(arm, dict) or not isinstance(arm.get("score"), int) or isinstance(arm["score"], bool) or not 1 <= arm["score"] <= 5:
        raise ValueError("%s score must be an integer from 1 to 5" % name)
    tokens = arm.get("tokens")
    if tokens is not None and (not isinstance(tokens, int) or isinstance(tokens, bool) or tokens < 0):
        raise ValueError("%s tokens must be a nonnegative integer or null" % name)
    captures = arm.get("captures")
    if not isinstance(captures, dict) or set(captures) != {"desktop", "mobile"}:
        raise ValueError("%s must include desktop and mobile captures" % name)
    for kind, filename in (("desktop", "1280.png"), ("mobile", "390.png")):
        value = captures[kind]
        if not isinstance(value, str) or not value:
            raise ValueError("%s %s capture path is required" % (name, kind))
        path = Path(value)
        if path.is_absolute() or path.name != filename:
            raise ValueError("%s %s capture must be a relative %s path" % (name, kind, filename))
        resolved = (root / path).resolve()
        try:
            resolved.relative_to(root.resolve())
        except ValueError:
            raise ValueError("%s %s capture must stay inside the manifest directory" % (name, kind))
        if ".uak-shots" in path.parts and "visual-reference" in path.parts or ".uak-shots" in resolved.parts and "visual-reference" in resolved.parts:
            raise ValueError("synthetic visual-reference captures cannot be scored")
        if not resolved.is_file():
            raise ValueError("%s %s capture is missing: %s" % (name, kind, value))
        if not valid_png(resolved):
            raise ValueError("%s %s capture is not a complete PNG: %s" % (name, kind, value))
    return arm["score"], tokens


def valid_png(path):
    try:
        with path.open("rb") as image:
            if image.read(8) != b"\x89PNG\r\n\x1a\n":
                return False
            seen_header = seen_data = False
            while True:
                head = image.read(8)
                if len(head) != 8:
                    return False
                length, kind = struct.unpack(">I4s", head)
                if (not seen_header and kind != b"IHDR") or kind == b"IHDR" and seen_header:
                    return False
                if kind == b"IHDR" and length != 13:
                    return False
                if kind == b"IDAT":
                    seen_data = seen_data or length > 0
                remaining, checksum, header = length, zlib.crc32(kind), b""
                while remaining:
                    chunk = image.read(min(remaining, 65536))
                    if not chunk:
                        return False
                    if kind == b"IHDR":
                        header += chunk
                    checksum = zlib.crc32(chunk, checksum)
                    remaining -= len(chunk)
                crc = image.read(4)
                if len(crc) != 4 or struct.unpack(">I", crc)[0] != checksum & 0xFFFFFFFF:
                    return False
                if kind == b"IHDR":
                    width, height = struct.unpack(">II", header[:8])
                    if not width or not height:
                        return False
                    seen_header = True
                if kind == b"IEND":
                    return length == 0 and seen_header and seen_data and image.read(1) == b""
    except (OSError, struct.error):
        return False


def evaluate(manifest_path):
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("cannot read manifest: %s" % exc)
    if not isinstance(data, dict) or not isinstance(data.get("version"), int) or isinstance(data.get("version"), bool) or data["version"] != 1:
        raise ValueError("manifest version must be 1")
    pairs = data.get("pairs")
    if not isinstance(pairs, list) or not pairs:
        raise ValueError("manifest pairs must be a nonempty list")
    root = manifest_path.parent
    results = []
    token_values = {"baseline": [], "reference": []}
    wins = ties = losses = 0
    for index, pair in enumerate(pairs, 1):
        if not isinstance(pair, dict) or not isinstance(pair.get("brief"), str) or not pair["brief"] or not isinstance(pair.get("seed"), int) or isinstance(pair.get("seed"), bool):
            raise ValueError("pair %d needs a brief and shared integer seed" % index)
        if "baseline" not in pair or "reference" not in pair:
            raise ValueError("pair %d must include baseline and reference arms" % index)
        source = pair["reference"].get("source") if isinstance(pair["reference"], dict) else None
        if not isinstance(source, dict) or not all(isinstance(source.get(key), str) and source[key] for key in ("kind", "id")):
            raise ValueError("pair %d reference needs source kind and id" % index)
        base, base_tokens = validate_arm(pair["baseline"], "pair %d baseline" % index, root)
        ref, ref_tokens = validate_arm(pair["reference"], "pair %d reference" % index, root)
        difference = ref - base
        wins += difference > 0
        losses += difference < 0
        ties += difference == 0
        token_values["baseline"].append(base_tokens)
        token_values["reference"].append(ref_tokens)
        results.append({"brief": pair["brief"], "seed": pair["seed"], "baseline_score": base,
                        "reference_score": ref, "score_difference": difference,
                        "tokens": {"baseline": base_tokens, "reference": ref_tokens}})
    totals = {arm: sum(values) if all(value is not None for value in values) else None
              for arm, values in token_values.items()}
    return {"pairs": results, "wins": wins, "ties": ties, "losses": losses,
            "mean_difference": sum(item["score_difference"] for item in results) / len(results),
            "token_totals": totals}


def main():
    if len(sys.argv) != 2:
        print("usage: visual_reference_eval.py MANIFEST.json", file=sys.stderr)
        return 2
    try:
        report = evaluate(Path(sys.argv[1]).resolve())
    except ValueError as exc:
        print("visual-reference-eval: %s" % exc, file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
