"""Prepare, calibrate, generate and audit the approved six paired samples."""
import os
for _name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ[_name] = "1"
os.environ["MPLBACKEND"] = "Agg"

import argparse
from pathlib import Path
import platform
import sys
import time
import traceback
import unittest

CODE = Path(__file__).resolve().parent
if str(CODE) not in sys.path:
    sys.path.insert(0, str(CODE))


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=next(p for p in Path(__file__).resolve().parents if (p / 'pyproject.toml').is_file() and (p / 'AGENTS.md').is_file()) / "output/mask_generator")
    parser.add_argument("--stage", choices=("all", "prepare", "calibrate", "generate", "audit", "report", "test"), default="all")
    parser.add_argument("--workers", type=int, choices=range(1, 9), default=8,
                        help="Total Python process budget including the coordinator; every process is pinned to one CPU.")
    return parser.parse_args()


def claim_output(output: Path):
    from common.io import read_json, utc_now, write_json
    output.mkdir(parents=True, exist_ok=True)
    marker = output / ".mask_generator.json"
    if marker.exists():
        if read_json(marker).get("owner") != "LEM mask_generator":
            raise RuntimeError("output is owned by another program")
    else:
        if any(output.iterdir()):
            raise RuntimeError("output already contains files without this generator's ownership marker")
        write_json(marker, {"owner": "LEM mask_generator", "created_utc": utc_now()})


def run_tests(output: Path) -> dict:
    from common.io import utc_now, write_json
    test_root = next(p for p in CODE.parents if (p / 'pyproject.toml').is_file())
    sys.path.insert(0, str(test_root))
    suite = unittest.defaultTestLoader.loadTestsFromNames([
        'tests.data_generation.stage.mask_generator.' + name
        for name in ('test_geometry', 'test_numerics', 'test_report')
    ])
    with (output / "unit_tests.log").open("w", encoding="utf-8") as stream:
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    record = {"created_utc": utc_now(), "tests_run": result.testsRun, "failures": len(result.failures),
              "errors": len(result.errors), "skipped": len(result.skipped), "passed": result.wasSuccessful(),
              "log": "unit_tests.log", "interpreter": sys.executable}
    write_json(output / "unit_tests.json", record)
    print(f"unit tests: {result.testsRun}, failures={len(result.failures)}, errors={len(result.errors)}", flush=True)
    if not result.wasSuccessful():
        print((output / "unit_tests.log").read_text(encoding="utf-8"), flush=True)
        raise RuntimeError("code tests failed")
    return record


def manifest(output: Path, seeds: list[int], cpus: list[int], wall: float):
    from importlib.metadata import version
    from common.io import file_sha256, read_json, utc_now, write_json
    code_files = sorted(p for p in CODE.rglob("*") if p.is_file() and p.suffix in (".py", ".ps1", ".md", ".txt"))
    outputs = sorted(p for p in output.rglob("*") if p.is_file() and p.relative_to(output).as_posix() not in ("manifest.json", "run_status.json")
                     and "cache" not in p.relative_to(output).parts)
    record = {"created_utc": utc_now(), "seeds": seeds, "methods": ["ellipse", "reference_overlay"],
              "interpreter": sys.executable, "python": sys.version, "platform": platform.platform(),
              "libraries": {key: version(key) for key in ("numpy", "scipy", "shapely", "pyproj", "matplotlib", "Pillow")},
              "process_limit_including_coordinator": len(cpus), "cpu_indices": cpus, "threads_per_process": 1,
              "wall_s": wall, "reference_manifest": "reference/manifest.json",
              "code_files": [{"path": str(p), "sha256": file_sha256(p)} for p in code_files],
              "output_files": [{"path": p.relative_to(output).as_posix(), "bytes": p.stat().st_size, "sha256": file_sha256(p)} for p in outputs],
              "audit_passed": read_json(output / "audit.json")["passed"],
              "scope": "水下台地平面掩膜；海底高程、过渡、地质活动与演化不在本轮输出中。"}
    write_json(output / "manifest.json", record)


def main():
    args = arguments()
    output = args.output.resolve()
    claim_output(output)
    os.environ["MPLCONFIGDIR"] = str(output / "cache/matplotlib")
    from common.runtime import configure_process_tree
    from common.io import file_sha256, read_csv, read_json, utc_now, write_csv, write_json
    from common.reference import load_reference, prepare_reference
    from common.export import audit_results, export_sample, load_samples
    from common.numerics import shared_sample
    from common.render import calibration_png, comparison_png, statistics_png
    from common.report import write_report
    from ellipse.calibrate import calibrate
    from ellipse.generator import generate_ellipse_mask
    from reference_overlay.generator import generate_reference_mask

    start = time.perf_counter()
    cpus = configure_process_tree(args.workers)
    seeds = list(range(1001, 1007))
    print(f"stage={args.stage}; output={output}; process budget={len(cpus)}; one CPU per process", flush=True)
    if args.stage in ("all", "test"):
        run_tests(output)
    if args.stage == "test":
        return
    # Any generation invalidates a prior image review. Keep its earlier record as history.
    if args.stage in ("all", "generate") and (output / "visual_review.json").exists():
        previous = read_json(output / "visual_review.json")
        write_json(output / "previous_visual_review.json", previous)
        write_json(output / "visual_review.json", {"state": "本轮重新生成，图像检查待记录", "user_acceptance": "待用户检查"})
    try:
        write_json(output / "run_status.json", {"state": "running", "stage": args.stage, "started_utc": utc_now()})
        if args.stage in ("all", "prepare"):
            reference = prepare_reference(output / "reference")
        else:
            reference = load_reference(output / "reference")
        if args.stage == "prepare":
            write_json(output / "run_status.json", {"state": "reference_prepared", "finished_utc": utc_now()})
            return
        if args.stage in ("all", "calibrate"):
            calibration = calibrate(reference, output / "calibration", args.workers, cpus)
            calibration_png(output / "calibration/search.png", calibration)
        else:
            calibration = read_json(output / "calibration/calibration.json")
        if args.stage == "calibrate":
            write_json(output / "run_status.json", {"state": "method_a_calibrated", "finished_utc": utc_now()})
            return
        selected = read_json(output / "calibration/selected.json")
        if (selected["reference_model_sha256"] != file_sha256(output / "reference/shape_model.json")
                or selected["reference_coverage_sha256"] != reference.manifest["coverage_array_sha256"]):
            raise RuntimeError("selected calibration and current reference differ; rerun calibration")
        if args.stage in ("all", "generate"):
            samples = []
            for seed in seeds:
                shared = shared_sample(seed)
                for result in (generate_ellipse_mask(seed, reference, selected, shared=shared),
                               generate_reference_mask(seed, reference, shared=shared)):
                    item = export_sample(result, reference, output / f"seed{seed}" / result.method)
                    samples.append(item)
                    print(f"exported seed={seed} method={result.method} area={result.mask.mean():.6f}", flush=True)
        else:
            samples = load_samples(output, seeds)
        if args.stage in ("all", "generate", "audit"):
            audit_results(output, reference, selected, seeds)
        comparison_png(output, samples)
        statistics_png(output / "calibration/statistical_comparison.png", reference.model, calibration,
                       read_csv(output / "calibration/sample_statistics.csv"), samples)
        write_csv(output / "summary.csv", [{"seed": s["seed"], "method": s["method"],
                   **{k: s["metrics"][k] for k in ("fraction", "area_km2", "axis_ratio", "shoreline_development",
                                                  "components_4", "largest_component_fraction", "closed_water_cells")},
                   "longest_band_contact_km": max(s["metrics"]["longest_straight_band_contact_km"].values())} for s in samples])
        write_report(output, samples)
        manifest(output, seeds, cpus, time.perf_counter()-start)
        write_json(output / "run_status.json", {"state": "complete", "stage": args.stage, "finished_utc": utc_now(),
                   "wall_s": time.perf_counter()-start, "samples": 12, "visual_acceptance": "awaiting_user_review"})
        print(f"completed: 12 masks, 12 primary PNGs, comparison.png and report.html ({time.perf_counter()-start:.1f}s)", flush=True)
    except Exception:
        write_json(output / "run_status.json", {"state": "failed", "stage": args.stage, "failed_utc": utc_now(),
                                              "traceback": traceback.format_exc()})
        raise


if __name__ == "__main__":
    main()
