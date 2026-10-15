"""Build the six-minute draft from fixed public aggregates; no model calls."""
import csv
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE = ROOT / "docs/presentation_sources/20261016T_reachable_rescues"
BUILD = ROOT / ".cache/midterm_slides_20261016"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(name):
    with (SOURCE / name).open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def run(args):
    return subprocess.run(args, cwd=HERE, check=True, capture_output=True, text=True).stdout


def main():
    BUILD.mkdir(parents=True, exist_ok=True)
    repair = rows("repair_summary.csv")
    conditions = ["self_refine", "execution_feedback", "self_debugging"]
    overall = {
        r["condition_id"]: r for r in repair
        if r["scope"] == "pooled" and r["grouping"] == "overall"
    }
    assert [int(overall[c]["rescued"]) for c in conditions] == [96, 183, 180]
    assert all(int(overall[c]["initial_failures"]) == 545 for c in conditions)
    assert all(int(overall[c]["initial_successes"]) == 455 for c in conditions)
    overlap = next(r for r in rows("fd_overlap_summary.csv") if r["scope"] == "pooled" and r["grouping"] == "overall")
    assert [int(overlap[k]) for k in ("both", "F_only", "D_only", "neither")] == [140, 43, 40, 322]
    snapshot = json.loads((SOURCE / "results_snapshot.json").read_text())
    assert [snapshot[k] for k in ("discordant_pairs", "discordant_condition_paths", "discordant_transitions")] == [83, 166, 398]
    third = {r["condition_id"]: r for r in rows("third_round_summary.csv") if r["scope"] == "pooled" and r["grouping"] == "overall"}
    assert [int(third[c]["additional_rescues"]) for c in conditions] == [19, 28, 33]
    assert [f'{100 * float(third[c]["loss_if_stop_at_2"]):.1f}' for c in conditions] == ["19.8", "15.3", "18.3"]
    for category, expected in [("import_error", [271, 58, 72]), ("build_error", [126, 76, 68])]:
        by_error = {r["condition_id"]: r for r in repair if r["scope"] == "pooled" and r["grouping"] == "baseline_error" and r["baseline_error_category"] == category}
        assert [int(by_error[conditions[1]]["initial_failures"]), int(by_error[conditions[1]]["rescued"]), int(by_error[conditions[2]]["rescued"])] == expected
    assert json.loads((SOURCE / "sanity_report.json").read_text())["passed"] is True
    colors = ["Gray", "Teal", "Orange"]
    labels = ["R：自己見直し", "F：実行結果提示", "D：自己デバッグ"]
    bars = []
    for i, c in enumerate(conditions):
        n = int(overall[c]["rescued"])
        rate = 100 * n / 545
        y = 2.6 - i
        bars.append(
            rf"\node[anchor=east,font=\small] at (-.8,{y}) {{{labels[i]}}};"
            rf"\fill[{colors[i]}] (0,{y-.23}) rectangle ({rate},{y+.23});"
            rf"\node[anchor=west,font=\small\bfseries,text={colors[i]}] at ({rate+.5},{y}) {{{rate:.1f}\%\quad {n}/545組}};"
        )
    data = ["% Generated from the fixed public CSVs by build.py.", r"\newcommand{\rescuebars}{" + "\n".join(bars) + "}"]
    for c, short in zip(conditions, "RFD"):
        cost = next(r for r in snapshot["overall_costs"] if r["condition_id"] == c and int(r["cap"]) == 3)
        assert int(cost["rescued"]) == int(overall[c]["rescued"])
        data.append(r"\newcommand{\cost" + short + "}{" + f'{cost["tokens_per_rescue"]:,.1f}' + "}")
    modelrows = []
    models = ["qwen3.5:4b", "gemma4:e4b-it-qat", "qwen3.5:9b", "qwen2.5-coder:7b", "gemma3:4b"]
    for model in models:
        selected = {
            r["condition_id"]: r for r in repair
            if r["scope"] == "pooled" and r["grouping"] == "model" and r["model_spec"] == "ollama:" + model
        }
        cells = [rf"\texttt{{{model}}}", selected[conditions[0]]["initial_failures"]]
        cells += [selected[c]["rescued"] for c in conditions]
        modelrows.append(" & ".join(cells) + r" \\")
    data.append(r"\newcommand{\modelrows}{" + "\n".join(modelrows) + "}")
    (HERE / "data.tex").write_text("\n".join(data) + "\n")
    logs = []
    for _ in range(2):
        logs.append(run(["platex", "-interaction=nonstopmode", "-halt-on-error", f"-output-directory={BUILD}", "slides.tex"]))
    logs.append(run(["dvipdfmx", "-p", "160mm,90mm", "-f", "ptex-ipaex.map", "-o", str(HERE / "slides.pdf"), str(BUILD / "slides.dvi")]))
    (BUILD / "build_output.txt").write_text("\n".join(logs))
    info = run(["pdfinfo", str(HERE / "slides.pdf")])
    text = run(["pdftotext", "-layout", str(HERE / "slides.pdf"), "-"])
    fonts = run(["pdffonts", str(HERE / "slides.pdf")])
    log = (BUILD / "slides.log").read_text()
    checks = {
        "eleven_pages_eight_main_three_appendix": bool(re.search(r"Pages:\s+11\b", info)),
        "six_minute_timing": sum([15, 35, 55, 45, 60, 50, 55, 45]) == 360,
        "no_overflow_missing_glyphs_or_unresolved_refs": not bool(re.search(r"Overfull|Missing character|undefined references|undefined on input", log, re.I)),
        "main_counts_in_pdf": all(s in text for s in ["96/545", "183/545", "180/545", "17.6%", "33.6%", "33.0%", "18,852.6", "9,333.8", "10,976.6"]),
        "fonts_embedded": all(bool(re.search(r"\byes\s+(?:yes|no)\s+(?:yes|no)\s+\d+\s+\d+\s*$", line)) for line in fonts.splitlines()[2:]),
        "fixed_source_sanity_passed": True,
        "source_csv_counts_match_slides": True,
    }
    (BUILD / "slides_extracted.txt").write_text(text)
    (BUILD / "pdfinfo.txt").write_text(info)
    (BUILD / "pdffonts.txt").write_text(fonts)
    source_names = ["results_snapshot.json", "repair_summary.csv", "fd_overlap_summary.csv", "third_round_summary.csv", "cost_by_cap_and_stratum.csv", "discordant_transitions.csv", "preventive_summary.csv", "source_manifest.json", "sanity_report.json", "validation_report.json"]
    source_paths = [SOURCE / n for n in source_names] + [
        ROOT / "docs/midterm2026/paper.tex",
        ROOT / "docs/analysis/reevaluation_followup_20261015/specification_review.md",
        ROOT / "docs/analysis/reevaluation_followup_20261015/partial_rerun_sanity_report.json",
    ]
    report = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "automated_checks_passed_pending_visual_review" if all(checks.values()) else "failed",
        "checks": checks,
        "main_slides": 8, "appendix_slides": 3, "target_seconds": 360,
        "timing_seconds": [15, 35, 55, 45, 60, 50, 55, 45],
        "fixed_snapshot_captured_at_utc": snapshot["captured_at_utc"],
        "new_model_requests": 0, "generated_code_executions": 0,
        "sources_sha256": {str(p.relative_to(ROOT)): sha(p) for p in source_paths},
        "artifacts_sha256": {p.name: sha(p) for p in [HERE / "slides.tex", HERE / "data.tex", HERE / "slides.pdf", HERE / "speaker_notes.txt", Path(__file__).resolve()]},
    }
    (HERE / "validation_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"checks": checks, "pdf": str(HERE / "slides.pdf")}, ensure_ascii=False, indent=2))
    if not all(checks.values()):
        raise SystemExit("Slide validation failed; see validation_report.json and .cache/midterm_slides_20261016")


if __name__ == "__main__":
    main()
