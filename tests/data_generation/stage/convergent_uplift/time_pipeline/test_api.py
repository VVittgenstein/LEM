"""Check the saved public adapter against independently exported window frames."""

from pathlib import Path as _BootstrapPath
import sys as _bootstrap_sys
_project_root = next(p for p in _BootstrapPath(__file__).resolve().parents if (p / 'pyproject.toml').is_file() and (p / 'AGENTS.md').is_file())
for _relative in ('data_generation/stage/convergent_uplift/time_pipeline', 'data_generation/stage/mask_generator', 'data_generation/stage/seafloor_generator', 'viewer', 'data_generation/stage/convergent_uplift'):
    _code_path = str(_project_root / _relative)
    if _code_path not in _bootstrap_sys.path:
        _bootstrap_sys.path.append(_code_path)

import time
from schedule import ConvergentSchedule
from tcontext import *

def main():
    tic=time.perf_counter();schedule=ConvergentSchedule(1003)
    assert schedule.at_time(0).shape==(500,500) and np.all(schedule.at_time(0)==0)
    modern=schedule.at_time(48e6)
    file=np.load(OUT/'seed1003/event01/window_frames.npz');error=float(np.max(np.abs(modern-file['u_m_per_yr'][-1])))
    assert error<1e-8 and modern.max()>0
    earlier=np.load(OUT/'seed1003/event00/window_frames.npz');time0=float(earlier['sim_Myr'][3])
    first=schedule.at_time(time0*1e6);first_error=float(np.max(np.abs(first-earlier['u_m_per_yr'][3])));assert first_error<1e-8
    assert not np.array_equal(first,modern)
    # Explicit complete coordinates belong to one belt, rather than a multi-belt grid.
    complete=ConvergentSchedule(1003,layout='complete',event_index=1)
    native=np.load(OUT/'seed1003/event01/native_frames.npz');native_error=float(np.max(np.abs(complete.at_time(48e6)-native['u_m_per_yr'][-1])));assert native_error<1e-8
    try:ConvergentSchedule(1003,layout='complete')
    except ValueError:pass
    else:raise AssertionError('Complete coordinates must identify their belt')
    rate=schedule.mean_rate(47.999e6,48e6);mid=schedule.at_time(47.9995e6)
    midpoint_error=float(np.max(np.abs(rate-mid)));assert midpoint_error<1e-7
    assert np.all(schedule.displacement(0,1e6)==0)
    try:schedule.at_time(48e6+1)
    except ValueError:pass
    else:raise AssertionError('Out-of-window simulation was accepted')
    save(Path(os.environ.get('LEM_TEST_OUTPUT',str(CHECKS)))/'api.json',dict(passed=True,shape=list(modern.shape),modern_export_error_m_yr=error,first_belt_export_error_m_yr=first_error,complete_belt_export_error_m_yr=native_error,
        short_interval_midpoint_error_m_yr=midpoint_error,time_input_unit='years since 48 Ma',rate_unit='m/yr',displacement_unit='m',elapsed_seconds=time.perf_counter()-tic))
    print('API checked',error,midpoint_error,flush=True)

def test_saved_api():
    main()

if __name__=='__main__':main()
