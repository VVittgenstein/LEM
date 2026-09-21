"""Targeted scientific-data checks derived from inspected source semantics."""
from __future__ import annotations
import csv
import hashlib
import json
import zipfile
from collections import Counter
from workspace import ROOT, read_csv, write_json

def main():
    out={}
    w=read_csv(ROOT/'sources/new/N01/WSM_Database_2025.csv')
    missing=[r for r in w if not r['LAT'] or not r['LON']]
    out['WSM']=dict(missing_coordinate_rows=len(missing),missing_coordinate_qualities=dict(Counter(r['QUALITY'] for r in missing)),
                    no_orientation_999=sum(r['AZI']=='999' for r in w),
                    abc_nf_fms_fraction=sum(r['QUALITY'] in ['A','B','C'] and r['REGIME']=='NF' and r['TYPE']=='FMS' for r in w)/sum(r['QUALITY'] in ['A','B','C'] and r['REGIME']=='NF' for r in w),
                    interpretation='Missing coordinates in Xmi records and AZI=999 are retained as missing; 999 is documented in TR25-01 Table 2-1.')
    m={}
    for kind in ['faults','sections','multifaults']:
        features=json.loads((ROOT/f'sources/new/N02/MSSM_{kind}.geojson').read_text(encoding='utf-8'))['features']
        bad=[]
        for f in features:
            p=f['properties']
            if all(k in p for k in ['dip_lower','dip_int','dip_upper']) and not p['dip_lower']<=p['dip_int']<=p['dip_upper']:
                bad.append({k:p.get(k) for k in ['MSSM_id','fault_name','sec_name','dip_lower','dip_int','dip_upper']})
        m[kind]=dict(dip_order_failures=bad)
    out['MSSM']=m
    with zipfile.ZipFile(ROOT/'sources/new/N03/fault_statistics.zip') as z:
        prefix='Extracted fault statistics/Geometric_relationships/Appended_relationships_Model'
        b,e=z.read(prefix+'B.xlsx'),z.read(prefix+'E.xlsx')
        out['Pan_B_E']=dict(equal_bytes=b==e,sha256_B=hashlib.sha256(b).hexdigest(),sha256_E=hashlib.sha256(e).hexdigest(),
                           status='原因未查明',treatment='Retain originals; do not treat these two geometry workbooks as distinct model evidence.')
    obs=read_csv(ROOT/'output/tables/Pan_Pan2022_geometric_moment.csv')
    out['Pan_dip']=dict(total_rows=len(obs),values_above_90=sum(float(r['dip'])>90 for r in obs),
                        minimum=min(float(r['dip']) for r in obs),maximum=max(float(r['dip']) for r in obs),
                        status='Field meaning unresolved. Exclude this column from dip-angle fitting; do not silently reinterpret it as dip direction.')
    b=read_csv(ROOT/'output/tables/Pan_Appended_relationships_ModelB.csv')
    out['Pan_time']=dict(workbook_B_max_age=max(float(r['age']) for r in b),
                         supplement_statement='Supplement p12: 1.25 mm/yr output extends to 10 Myr.',
                         author_script_statement='results_concat.py age=timestep/2.5; results_to_strain_time.py timestep_to_age=2.5, final step 50.',
                         status='Workbook/script reach 20 Myr; supplementary text states 10 Myr. Cause unresolved; do not use this age column for duration fitting.')
    t=read_csv(ROOT/'sources/existing/tables/T01_rift_catalogue.csv')
    out['T01']=dict(unreviewed_qualifiers=sum(r['width_qualifier']=='unreviewed_in_original_table' for r in t),
                    zero_width_records=[{k:r[k] for k in ['catalogue_record_id','Name','Width','width_qualifier']} for r in t if r['width_numeric_original']=='0.0'])
    # Integrity checks assert expected source versions; data findings remain findings.
    assert len(w)==100842
    assert len(t)==657
    assert out['Pan_B_E']['equal_bytes']
    assert len(m['faults']['dip_order_failures'])==1
    assert len(m['sections']['dip_order_failures'])==4
    assert out['Pan_time']['workbook_B_max_age']==20
    write_json('output/checks/quality_findings.json',out)
    print(json.dumps(out,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
