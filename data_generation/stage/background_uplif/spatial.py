"""Five fitted spatial models, sharing one correlated-random-field implementation.

The old radial Gaussian uplift dome is absent. Gaussian spectral filtering here
defines random spatial correlation only; the platform taper is a separate field.
"""
import numpy as np
from scipy.ndimage import map_coordinates
from scipy.optimize import minimize

LATENT_N = 128
LATENT_DX_KM = 16.
FIT_ENSEMBLE = 10
GENERATION_CANDIDATES = 64
SPATIAL_LOG_RMS_LIMIT = .30  # engineering diagnostic, not a geological acceptance test
FIT_SEED = 793141


def white_spectrum(seed, interval, candidate):
    rng = np.random.default_rng(np.random.SeedSequence([int(seed), 13731, int(interval), int(candidate)]))
    return np.fft.rfft2(rng.standard_normal((LATENT_N, LATENT_N)))


def latent_field(spectrum, sigma_x_km, sigma_y_km):
    ky = np.fft.fftfreq(LATENT_N, d=LATENT_DX_KM)[:, None]
    kx = np.fft.rfftfreq(LATENT_N, d=LATENT_DX_KM)[None, :]
    filt = np.exp(-2*np.pi**2*((sigma_x_km*kx)**2+(sigma_y_km*ky)**2))
    filt[0, 0] = 0.
    field = np.fft.irfft2(spectrum * filt, s=(LATENT_N, LATENT_N))
    return field


def at_coordinates(field, x_km, y_km):
    x, y = np.meshgrid(x_km, y_km)
    center = (LATENT_N-1)/2
    return map_coordinates(field, np.array([center+y/LATENT_DX_KM,
                                            center+x/LATENT_DX_KM]), order=3, mode="wrap")


def normalize(field, mean=0., std=1.):
    sd = float(field.std())
    if sd <= 1e-14:
        raise ValueError("Degenerate correlated field")
    return (field-float(field.mean()))*(std/sd)+mean


def variogram_features(field, variance=None):
    """Directional half-mean-squared increments at 1..4 native grid lags, / variance."""
    v = float(field.var()) if variance is None else float(variance)
    if v <= 0:
        raise ValueError("Positive variance required for spatial-scale fitting")
    return np.array([.5 * np.mean(np.diff(field, n=1, axis=axis)**2)/v if lag == 1
                     else .5 * np.mean((np.take(field, range(lag, field.shape[axis]), axis=axis)
                                      -np.take(field, range(field.shape[axis]-lag), axis=axis))**2)/v
                     for axis in (1, 0) for lag in (1, 2, 3, 4)])


def feature_error(observed, target):
    return float(np.sqrt(np.mean(np.log(np.maximum(observed, 1e-10)/np.maximum(target, 1e-10))**2)))


def coarse_candidate(spectrum, sx, sy, x_ref, y_ref):
    latent = latent_field(spectrum, sx, sy)
    dense_coarse = at_coordinates(latent, np.arange(5., 500., 10.)-250., np.arange(5., 500., 10.)-250.)
    mean, sd = float(dense_coarse.mean()), float(dense_coarse.std())
    if sd <= 1e-14:
        raise ValueError("Degenerate finite-window variance")
    reference_points = (at_coordinates(latent, x_ref, y_ref)-mean)/sd
    return latent, variogram_features(reference_points, variance=1.)


def fit_one(rate, weights, x_ref, y_ref, interval):
    mean = float(np.sum(rate*weights)/weights.sum())
    std = float(np.sqrt(np.sum(weights*(rate-mean)**2)/weights.sum()))
    target = variogram_features(rate, variance=std**2)
    spectra = [white_spectrum(FIT_SEED, interval, k) for k in range(FIT_ENSEMBLE)]
    cache = {}
    def evaluate(log_sigma):
        sx, sy = np.exp(log_sigma)
        key = (float(sx), float(sy))
        if key not in cache:
            fs = [coarse_candidate(s, sx, sy, x_ref, y_ref)[1] for s in spectra]
            avg = np.mean(fs, axis=0)
            cache[key] = (feature_error(avg, target), avg)
        return cache[key][0]
    candidates = [(sx, sy) for sx in (25., 60., 140., 320.) for sy in (25., 60., 140., 320.)]
    best = min(candidates, key=lambda p: evaluate(np.log(p)))
    opt = minimize(evaluate, np.log(best), method="Nelder-Mead",
                   bounds=[(np.log(12.), np.log(640.))]*2,
                   options={"maxiter": 90, "xatol": .012, "fatol": 1e-5})
    sx, sy = map(float, np.exp(opt.x)); loss = evaluate(opt.x)
    _, predicted = cache[(sx, sy)]
    return {"interval": interval, "rate_mean_m_per_Myr": mean, "rate_std_m_per_Myr": std,
            "sigma_x_km": sx, "sigma_y_km": sy, "covariance_efold_x_km": 2*sx,
            "covariance_efold_y_km": 2*sy, "target_variogram": target.tolist(),
            "fitted_ensemble_variogram": predicted.tolist(), "fit_log_rms": loss,
            "fit_optimizer_success": bool(opt.success), "fit_optimizer_message": str(opt.message),
            "fit_evaluations": len(cache), "fit_ensemble": FIT_ENSEMBLE, "fit_seed": FIT_SEED,
            "near_parameter_bound": bool(min(sx, sy) < 13 or max(sx, sy) > 620),
            "native_lags_x_km": (np.arange(1,5)*float(x_ref[1]-x_ref[0])).tolist(),
            "native_lags_y_km": (np.arange(1,5)*float(y_ref[1]-y_ref[0])).tolist(),
            "method": "finite-window ensemble fit of anisotropic Gaussian spectral correlation",
            "scope": "window-specific engineering correlation model, not a universal dynamic-topography distribution"}


def generate_one(seed, model, x_ref, y_ref):
    sx, sy = model["sigma_x_km"], model["sigma_y_km"]
    target = np.array(model["target_variogram"])
    proposals = []
    best = None
    for k in range(GENERATION_CANDIDATES):
        spectrum = white_spectrum(seed, model["interval"], k)
        latent, feature = coarse_candidate(spectrum, sx, sy, x_ref, y_ref)
        error = feature_error(feature, target)
        proposals.append(error)
        if best is None or error < best[0]:
            best = error, k, latent
    _, k, latent = best
    coords = np.arange(500, dtype=float)+.5-250.
    raw = normalize(at_coordinates(latent, coords, coords),
                    model["rate_mean_m_per_Myr"], model["rate_std_m_per_Myr"])
    # Compare at the same 99 physical positions as the source, without upsampling the source.
    yy, xx = np.meshgrid(y_ref+249.5, x_ref+249.5, indexing="ij")
    sampled = map_coordinates(raw, np.array([yy, xx]), order=3, mode="nearest")
    feature = variogram_features(sampled, variance=model["rate_std_m_per_Myr"]**2)
    error = feature_error(feature, target)
    return raw, {"seed": seed, "interval": model["interval"], "selected_proposal": k,
                 "proposal_count": GENERATION_CANDIDATES, "proposal_log_rms": proposals,
                 "variogram": feature.tolist(), "spatial_log_rms": error,
                 "spatial_check_limit": SPATIAL_LOG_RMS_LIMIT, "spatial_check": error <= SPATIAL_LOG_RMS_LIMIT,
                 "raw_mean_m_per_Myr": float(raw.mean()), "raw_std_m_per_Myr": float(raw.std()),
                 "raw_min_m_per_Myr": float(raw.min()), "raw_max_m_per_Myr": float(raw.max())}
