"""Re-tabulate frozen F station profiles at the measured integer offset."""
import numpy as np
import bootstrap as b
from coast import known_binary_runs


def prepare_reference(offset_km, out):
    cohort=[r for r in b.read_json(b.COHORT) if abs(float(r['latitude']))<60]
    if len(cohort)!=34 or len({r['id'] for r in cohort})!=34:
        raise ValueError('The frozen reference cohort must contain 34 unique members')
    if not 1<=offset_km<=250:
        raise ValueError('Measured offset is outside the stored 1..250 km reference profiles')
    landmasses=[]; segments=[]; sources=[]; total_codes={str(k):0 for k in (0,1,2,3,4,5,9)}
    for row in cohort:
        path=b.REFERENCE/(row['id']+'.npz')
        with np.load(path,allow_pickle=False) as z:
            distances=z['profile_distance_km']; hit=np.flatnonzero(distances==offset_km)
            if len(hit)!=1:raise ValueError('Missing requested profile distance')
            col=int(hit[0]); env=z['profile_env'][:,col]; water=z['profile_water'][:,col]
            code=np.where(water,env,9)
            ring_id=z['ring_id']; weight=z['weight_km']; station_s=z['s_km']
            metadata=__import__('json').loads(str(z['metadata_json']))
        if not np.isin(code,[0,1,2,3,4,5,9]).all() or not (weight>0).all():
            raise ValueError(f'Unexpected class or station weight: {row["id"]}')
        binary=np.full(len(code),-1,np.int8)
        binary[np.isin(code,[1,3,4])]=0; binary[code==2]=1
        known=binary>=0; deep=binary==1; shallow=binary==0
        if not known.any():raise ValueError(f'No known water endpoint for {row["id"]}')
        regime='mixed' if deep.any() and shallow.any() else ('all_deep' if deep.any() else 'all_shallow')
        lk=float(weight[known].sum()); ld=float(weight[deep].sum()); total=float(weight.sum())
        counts={k:int((code==int(k)).sum()) for k in total_codes}
        if sum(counts.values())!=len(code):raise ValueError('Station class counts do not reconcile')
        for k in counts:total_codes[k]+=counts[k]
        lm=dict(id=row['id'],name=row['name'],regime=regime,stations=len(code),known_stations=int(known.sum()),
                total_coast_km=total,known_coast_km=lk,known_coast_fraction=lk/total,
                deep_share_known_water=ld/lk,deep_share_all_coast=ld/total,code_counts=counts)
        landmasses.append(lm)
        for ring in metadata['rings']:
            sel=ring_id==ring['ring_id']; ds=float(ring['spacing_km'])
            if sel.sum()!=ring['n'] or not np.all(np.diff(station_s[sel])>0):
                raise ValueError('Reference ring stations must be complete and ordered along the coast')
            labels,rows,merges=known_binary_runs(binary[sel],ds,lmin=10.)
            for r in rows:
                segments.append(dict(landmass_id=row['id'],ring_id=ring['ring_id'],regime=regime,
                    environment='deep' if r['label'] else 'shallow',start_station=r['start'],
                    length_km=r['length_km'],censored=r['censored'],merge_count=merges,
                    used_for_fit=(regime=='mixed')))
        sources.append(dict(path=str(path),sha256=b.file_sha256(path),landmass_id=row['id']))
    quality=dict(population=34,offset_km=int(offset_km),source='frozen F profiles at 1 km spacing',
        regime_counts={k:sum(r['regime']==k for r in landmasses) for k in ('all_shallow','mixed','all_deep')},
        class_counts=total_codes,known_coast_fraction_mean=float(np.mean([r['known_coast_fraction'] for r in landmasses])),
        censored_length_rows=sum(r['censored'] for r in segments),
        complete_length_rows=sum(not r['censored'] for r in segments),
        fitted_complete_length_rows=sum(r['used_for_fit'] and not r['censored'] for r in segments),
        fitted_censored_length_rows=sum(r['used_for_fit'] and r['censored'] for r in segments),
        binary_definition={'shallow':[1,3,4],'deep':[2],'excluded':[0,5,9]},
        ratio_denominator='known marine endpoint coast length; all-coast numerator/denominator also retained',
        length_definition='binary shallow/deep runs on original outer rings, mixed landmasses; 10 km merging, unknowns remain barriers',
        limitations=['Geological/geomorphic class groups, not a bathymetric depth threshold.',
          'Unknown and non-water endpoints are excluded, never silently assigned shallow.',
          'Regime and ratio fits describe observed known endpoints; incomplete coverage is reported.',
          'Interrupted runs enter length fitting as lower bounds through a survival likelihood.',
          'Unknown gaps can split one underlying run into several bounds; dependence and geographic transfer remain limitations.',
          '10 km is inherited short-run processing, not the grid ocean-band width.'])
    b.write_json(out/'quality.json',quality)
    b.write_json(out/'landmasses.json',landmasses);b.write_csv(out/'landmasses.csv',landmasses)
    b.write_json(out/'segments.json',segments);b.write_csv(out/'segments.csv',segments)
    b.write_json(out/'sources.json',sources+[dict(path=str(b.COHORT),sha256=b.file_sha256(b.COHORT))])
    return landmasses,segments,quality
