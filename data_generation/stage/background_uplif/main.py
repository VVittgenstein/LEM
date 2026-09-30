"""Reproducible background-uplift pipeline; no LEM execution."""
import argparse
import json
import subprocess
import sys
from pathlib import Path
import numpy as np
import context as c
import reference
import spatial
import taper


def prepare(out):
    ref = reference.load_window(out)
    data = np.load(out / "reference_window.npz", allow_pickle=False)
    models = []
    for i, rate in enumerate(data["rates_m_per_Myr"], 1):
        fit = spatial.fit_one(rate, data["weights"], data["x_km"], data["y_km"], i)
        fit.update(ref["intervals"][i-1])
        models.append(fit)
        c.write_json(out / "fitted_models.json", {"version": c.VERSION, "models": models})
        print(f"interval {i}: mean {fit['rate_mean_m_per_Myr']:.4f}, SD {fit['rate_std_m_per_Myr']:.4f} m/Myr; "
              f"sigma {fit['sigma_x_km']:.1f}/{fit['sigma_y_km']:.1f} km; fit {fit['fit_log_rms']:.3f}", flush=True)
    payload = {"version": c.VERSION, "created_utc": c.utc_now(), "models": models,
               "reference_hash": c.file_sha256(out / "reference_window.npz"),
               "source_hash": c.file_sha256(out / "source/sources.json"),
               "field_lattice": {"n": spatial.LATENT_N, "cell_km": spatial.LATENT_DX_KM,
                                 "output_cell_km": 1., "interpolation": "cubic spline of a padded latent field"},
               "fitting": "eight directional normalized variogram values; fixed ten-realization ensemble",
               "generation": "64 new spatial proposals per seed and interval; smallest spatial-statistic discrepancy",
               "normalization": "mean and population SD of the untapered 500x500 field match the M2 native-node interval statistics",
               "temporal_policy": "five constant interval-average velocity fields; no within-interval time variation; cross-interval spatial covariance not fitted"}
    c.write_json(out / "fitted_models.json", payload)
    return payload


def generate(out):
    models = c.read_json(out / "fitted_models.json")
    if models["reference_hash"] != c.file_sha256(out / "reference_window.npz"):
        raise ValueError("Prepared reference changed")
    data = np.load(out / "reference_window.npz", allow_pickle=False)
    summary = []
    for seed in c.SEEDS:
        sample = c.load_mask(seed)
        dest = out / f"seed{seed}"
        dest.mkdir(exist_ok=True)
        weight, hard, rings, ring_info = taper.make_taper(sample["labels"], sample["mask"])
        for name, arr in (("taper_weight", weight), ("ring_weight", hard), ("ring_index", rings)):
            np.save(dest / f"{name}.npy", arr)
        c.write_json(dest / "taper.json", ring_info)
        raw_fields, final_fields, stats = [], [], []
        for model in models["models"]:
            raw, record = spatial.generate_one(seed, model, data["x_km"], data["y_km"])
            final = raw * weight
            i = model["interval"]
            raw_yr, final_yr = raw/1e6, final/1e6
            raw_fields.append(raw_yr); final_fields.append(final_yr)
            np.save(dest / f"interval{i:02d}_raw_m_per_yr.npy", raw_yr)
            np.save(dest / f"interval{i:02d}_rate_m_per_yr.npy", final_yr)
            record.update({"start_elapsed_Myr": model["start_elapsed_Myr"],
                           "end_elapsed_Myr": model["end_elapsed_Myr"],
                           "final_mean_m_per_Myr": float(final.mean()), "final_std_m_per_Myr": float(final.std()),
                           "final_min_m_per_Myr": float(final.min()), "final_max_m_per_Myr": float(final.max()),
                           "platform_mean_m_per_Myr": float(final[sample["mask"]].mean()),
                           "outside_mean_m_per_Myr": float(final[~sample["mask"]].mean()),
                           "negative_fraction": float((final<0).mean()),
                           "reference_mean_m_per_Myr": model["rate_mean_m_per_Myr"],
                           "reference_std_m_per_Myr": model["rate_std_m_per_Myr"],
                           "fit_sigma_x_km": model["sigma_x_km"], "fit_sigma_y_km": model["sigma_y_km"]})
            stats.append(record)
            print(f"seed {seed}, interval {i}: spatial error {record['spatial_log_rms']:.3f}", flush=True)
        durations = np.diff(c.ELAPSED_MYR)*1e6
        raw_cumulative = np.cumsum(np.array(raw_fields)*durations[:,None,None], axis=0)
        cumulative = np.cumsum(np.array(final_fields)*durations[:,None,None], axis=0)
        np.savez_compressed(dest / "schedule.npz", start_yr=np.array(c.ELAPSED_MYR[:-1])*1e6,
                            end_yr=np.array(c.ELAPSED_MYR[1:])*1e6,
                            rate_m_per_yr=np.array(final_fields), raw_rate_m_per_yr=np.array(raw_fields),
                            cumulative_displacement_m=cumulative, raw_cumulative_displacement_m=raw_cumulative)
        c.write_json(dest / "config.json", {"version": c.VERSION, "seed": seed, "grid": {"nx":500,"ny":500,"dx_m":1000.},
                     "input_hashes": sample["source_hashes"], "models_hash": c.file_sha256(out / "fitted_models.json"),
                     "ring_rules": taper.WEIGHTS, "temporal_policy": models["temporal_policy"],
                     "intervals": stats, "cumulative_48Myr": {"raw_mean_m": float(raw_cumulative[-1].mean()),
                           "raw_std_m": float(raw_cumulative[-1].std()), "final_mean_m": float(cumulative[-1].mean()),
                           "final_min_m": float(cumulative[-1].min()), "final_max_m": float(cumulative[-1].max())}})
        summary.extend(stats)
    c.write_csv(out / "sample_statistics.csv", summary)
    return summary


def audit(out, reproduce=True):
    models = c.read_json(out / "fitted_models.json")
    ref = np.load(out / "reference_window.npz", allow_pickle=False)
    source = c.read_json(out / "source/sources.json")
    source_ok = all(c.file_sha256(out/"source"/r["file"])==r["sha256"] for r in source["files"])
    # Independently reconstruct the retained source chronology from the frozen NC grids.
    from scipy.io import netcdf_file
    from scipy.ndimage import map_coordinates
    native = {}
    for age in reference.FILES:
        with netcdf_file(out/"source"/f"M2.{age}.Ma.nc", "r", mmap=False) as nc:
            lon, lat = nc.variables["lon"][:], nc.variables["lat"][:]
            ix = np.flatnonzero(np.isin(lon, ref["longitude"]))
            iy = np.flatnonzero(np.isin(lat, ref["latitude"]))
            native[age] = nc.variables["z"][:][np.ix_(iy, ix)].astype(float)
    expected_history = np.stack([.9*native[49]+.1*native[39], *[native[a] for a in (39,29,19,9,0)]])
    expected_delta = np.diff(expected_history, axis=0)
    expected_rates = expected_delta / np.diff(c.ELAPSED_MYR)[:,None,None]
    reference_checks = {
        "source_files": source_ok,
        "source_manifest_hash": models["source_hash"] == c.file_sha256(out/"source/sources.json"),
        "reference_hash": models["reference_hash"] == c.file_sha256(out/"reference_window.npz"),
        "native_shape": ref["rates_m_per_Myr"].shape == (5,9,11),
        "age_direction": bool(np.array_equal(ref["ages_Ma_BP"],c.AGES_MA)
                              and np.array_equal(ref["elapsed_Myr"],c.ELAPSED_MYR)),
        "source_history_and_48Ma_interpolation": bool(np.array_equal(ref["elevation_m"],expected_history)),
        "interval_difference": bool(np.array_equal(ref["interval_net_m"],expected_delta)),
        "interval_rate_units": bool(np.array_equal(ref["rates_m_per_Myr"],expected_rates)),
        "source_cumulative": bool(np.array_equal(ref["cumulative_m"],expected_history-expected_history[0])),
        "five_models": len(models["models"]) == 5,
        "optimizer_success": all(m["fit_optimizer_success"] for m in models["models"]),
    }
    for i, model in enumerate(models["models"]):
        rate = expected_rates[i]
        mu = np.average(rate,weights=ref["weights"])
        sd = np.sqrt(np.average((rate-mu)**2,weights=ref["weights"]))
        reference_checks[f"interval_{i+1}_statistics"] = bool(
            abs(mu-model["rate_mean_m_per_Myr"])<1e-12
            and abs(sd-model["rate_std_m_per_Myr"])<1e-12
            and np.allclose(spatial.variogram_features(rate,sd**2),model["target_variogram"],atol=1e-12,rtol=0))
    rows = []
    for seed in c.SEEDS:
        folder = out / f"seed{seed}"
        cfg = c.read_json(folder/"config.json")
        sample = c.load_mask(seed)
        w = np.load(folder/"taper_weight.npy", allow_pickle=False)
        new_w, hard, rings, info = taper.make_taper(sample["labels"], sample["mask"])
        sched = np.load(folder/"schedule.npz", allow_pickle=False)
        checks = {"source_files": source_ok,
                  "models_unchanged": cfg["models_hash"]==c.file_sha256(out/"fitted_models.json"),
                  "five_intervals": len(cfg["intervals"])==5 and sched["rate_m_per_yr"].shape==(5,500,500),
                  "inputs_unchanged": all(c.file_sha256(Path(r["path"]))==r["sha256"] for r in cfg["input_hashes"]),
                  "taper_reproduced": np.array_equal(w,new_w),
                  "ring_baselines": np.array_equal(hard,np.load(folder/"ring_weight.npy")),
                  "ring_indices": np.array_equal(rings,np.load(folder/"ring_index.npy")),
                  "weights_bounded": bool(np.all((w>=0)&(w<=1))),
                  "outer_three_and_beyond_zero": bool(np.all(w[rings>=3]==0)),
                  "domain_boundary_zero": info["domain_edge_max_weight"]==0,
                  "time_intervals": bool(np.array_equal(sched["start_yr"], np.array(c.ELAPSED_MYR[:-1])*1e6)
                                   and np.array_equal(sched["end_yr"], np.array(c.ELAPSED_MYR[1:])*1e6))}
        interval_rows = []
        for model, record in zip(models["models"], cfg["intervals"]):
            i = model["interval"]
            raw = np.load(folder/f"interval{i:02d}_raw_m_per_yr.npy")
            final = np.load(folder/f"interval{i:02d}_rate_m_per_yr.npy")
            yy,xx = np.meshgrid(ref["y_km"]+249.5,ref["x_km"]+249.5,indexing="ij")
            observed = spatial.variogram_features(map_coordinates(raw*1e6,np.array([yy,xx]),order=3,mode="nearest"),
                                                   model["rate_std_m_per_Myr"]**2)
            spatial_error = spatial.feature_error(observed,np.array(model["target_variogram"]))
            ic = {"shape_units": raw.shape==final.shape==(500,500),
                  "finite": bool(np.isfinite(raw).all() and np.isfinite(final).all()),
                  "mean_matches": bool(abs(raw.mean()*1e6-model["rate_mean_m_per_Myr"])<1e-9),
                  "std_matches": bool(abs(raw.std()*1e6-model["rate_std_m_per_Myr"])<1e-9),
                  "taper_product": bool(np.allclose(final,raw*w,atol=1e-20,rtol=1e-13)),
                  "spatial_statistics": spatial_error<=spatial.SPATIAL_LOG_RMS_LIMIT,
                  "spatial_record_matches": bool(np.allclose(observed,record["variogram"],rtol=0,atol=1e-12)
                                             and abs(spatial_error-record["spatial_log_rms"])<1e-12),
                  "schedule_same": bool(np.array_equal(final,sched["rate_m_per_yr"][i-1])
                                    and np.array_equal(raw,sched["raw_rate_m_per_yr"][i-1]))}
            if reproduce:
                again, _ = spatial.generate_one(seed,model,ref["x_km"],ref["y_km"])
                ic["seed_reproduction"] = np.array_equal(raw,again/1e6)
            interval_rows.append({"interval":i,"checks":ic,"passed":all(ic.values())})
        checks["cumulative_integral"] = bool(np.allclose(sched["cumulative_displacement_m"],
                  np.cumsum(sched["rate_m_per_yr"]*(sched["end_yr"]-sched["start_yr"])[:,None,None],axis=0),
                  rtol=1e-13,atol=1e-12))
        checks["raw_cumulative_integral"] = bool(np.allclose(sched["raw_cumulative_displacement_m"],
                  np.cumsum(sched["raw_rate_m_per_yr"]*(sched["end_yr"]-sched["start_yr"])[:,None,None],axis=0),
                  rtol=1e-13,atol=1e-12))
        rows.append({"seed":seed,"checks":checks,"intervals":interval_rows,
                     "passed":all(checks.values()) and all(x["passed"] for x in interval_rows)})
    result = {"source_grid_count":6,"source_native_nodes":99,"generated_fields":30,
              "seed_reproduction_run":reproduce,"reference_checks":reference_checks,"rows":rows,
              "passed":all(reference_checks.values()) and all(r["passed"] for r in rows)}
    c.write_json(out/"audit.json",result)
    distribution_diagnostics(out)
    print("audit passed:",result["passed"],flush=True)
    return result


def distribution_diagnostics(out):
    """Report unconstrained extrema and local signs from actual saved arrays."""
    rows=[]
    for i,ref in enumerate(c.read_json(out/"reference.json")["intervals"],1):
        samples=[];raw_min=[];raw_max=[]
        for seed in c.SEEDS:
            raw=np.load(out/f"seed{seed}/interval{i:02d}_raw_m_per_yr.npy")*1e6
            final=np.load(out/f"seed{seed}/interval{i:02d}_rate_m_per_yr.npy")*1e6
            raw_min.append(float(raw.min()));raw_max.append(float(raw.max()))
            samples.append({"seed":seed,"fraction_of_whole_domain":float((final<0).mean()),
                            "minimum_m_per_Myr":float(final.min())})
        rows.append({"interval":i,"reference_rate_min_m_per_Myr":ref["rate_min_m_per_Myr"],
                     "reference_rate_max_m_per_Myr":ref["rate_max_m_per_Myr"],
                     "generated_raw_min_m_per_Myr":min(raw_min),"generated_raw_max_m_per_Myr":max(raw_max),
                     "final_negative_fractions":samples})
    c.write_json(out/"distribution_diagnostics.json",{"intervals":rows,
        "interpretation":"Mean, standard deviation and directional variograms are constrained. Marginal shape, extrema and cross-interval covariance are not fitted; compare source minima with generated signs explicitly."})


def run_tests(out):
    result = subprocess.run([sys.executable,"-B","-m","unittest","discover","-s",str(c.ROOT/"tests/data_generation/stage/background_uplif"),"-t",str(c.ROOT),"-v"],
                            cwd=c.CODE,capture_output=True,text=True,encoding="utf-8",errors="replace")
    (out/"test_log.txt").write_text(result.stdout+result.stderr,encoding="utf-8")
    c.write_json(out/"tests.json",{"passed":result.returncode==0,"exit_code":result.returncode})
    if result.returncode:
        raise RuntimeError(result.stderr)


def manifest(out):
    import platform
    from importlib.metadata import version
    dependency_paths = [Path(sys.modules[name].__file__).resolve() for name in
                        (c.read_json.__module__, c.geometry.__module__, c.BandedScale.__module__)]
    c.write_json(out/"runtime.json", {"python":sys.version,"executable":sys.executable,
                  "platform":platform.platform(),
                  "packages":{name:version(name) for name in ("numpy","scipy","matplotlib","Pillow")},
                  "project_dependencies":[{"path":str(p),"sha256":c.file_sha256(p)} for p in dependency_paths]})
    paths = sorted(p for p in c.CODE.rglob("*") if p.is_file() and "__pycache__" not in p.parts
                   and p.name not in ("manifest.json",) and not p.name.endswith(".tmp"))
    c.write_json(out/"manifest.json",{"version":c.VERSION,"created_utc":c.utc_now(),
                  "files":[{"path":str(p.relative_to(c.CODE)),"bytes":p.stat().st_size,
                            "sha256":c.file_sha256(p)} for p in paths]})


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--stage",choices=("all","prepare","generate","audit","render","test"),default="all")
    parser.add_argument("--output")
    a=parser.parse_args();out=c.output_folder(a.output)
    if a.stage in ("all","test"):run_tests(out)
    if a.stage in ("all","prepare"):prepare(out)
    if a.stage in ("all","generate"):generate(out)
    if a.stage in ("all","render"):
        import figures
        figures.render(out)
    if a.stage in ("all","audit"):
        if not audit(out)["passed"]:
            raise RuntimeError("Numerical audit failed; inspect audit.json")
    if a.stage in ("all","render","audit"):
        import figures
        if not figures.check_svgs(out)["passed"]:
            raise RuntimeError("SVG audit failed; inspect svg_checks.json")
    if a.stage in ("all","render","audit","generate"):
        import figures
        figures.delivery(out)
    manifest(out)


if __name__=="__main__":
    main()
