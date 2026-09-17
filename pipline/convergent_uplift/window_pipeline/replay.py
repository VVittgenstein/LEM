"""Reproduce one complete selection with the same frozen input and random streams."""
from wcontext import *
from sample_windows import sample

if __name__=='__main__':
    seed=1006;p=CHECKS/f'replay/seed{seed}';sample(seed,p)
    a=load(OUT/f'seed{seed}/selection.json');b=load(p/'selection.json')
    keys=('candidate_id','path_id','center_source_km','rotation_matrix','movement_from_outside_km','span_x_km','span_y_km','witness')
    same={k:a[k]==b[k] for k in keys};x=np.load(OUT/f'seed{seed}/window.npz');y=np.load(p/'window.npz')
    arrays={k:bool(np.array_equal(x[k],y[k])) for k in x.files};passed=all(same.values()) and all(arrays.values())
    save(CHECKS/'reproducibility.json',{'passed':passed,'seed':seed,'selection_fields':same,'arrays':arrays})
    print('full selection replay',passed)
    if not passed:raise RuntimeError('Replay differs')
