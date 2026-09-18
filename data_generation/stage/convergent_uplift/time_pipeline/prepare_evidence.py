"""Freeze case evidence and explicitly separated modeling assumptions."""
import shutil, urllib.request, datetime
from tcontext import *

SOURCES_META = [
 dict(id='C05', author='Tippett', year=1992, title='Uplift history and geomorphic development of the Southern Alps',
      url='https://researchcommons.waikato.ac.nz/entities/publication/1694bff7-cdef-4a78-85b3-636c574333b5',
      locator='Abstract; Chapter 6 Table 1, printed pp181-182',
      checked='Regional earliest rock-uplift onset 8 Ma; later local starts 5 and 3 Ma. Ongoing system. Significant acceleration since 1.3 +/-0.3 Ma. 45 eastern onset estimates share 14 underlying constraints.'),
 dict(id='W21', author='Waldner et al.', year=2021, title='Central Pyrenees Mountain Building: Constraints From New LT Thermochronological Data From the Axial Zone',
      url='https://agupubs.onlinelibrary.wiley.com/doi/10.1029/2020TC006614',
      locator='Section 6.3, sequential restoration; abstract uses rounded 70 instead of 71 Ma',
      checked='Two reconstructed collisional phases: distributed shortening 71-40 Ma, localized shortening and underplating 40-20 Ma; post-orogenic evolution after 20 Ma. These phase boundaries are temporal proxies for a generated activity, with no implication that all subsequent uplift vanishes.'),
 dict(id='M10', author='Merten et al.', year=2010, title='From nappe stacking to out-of-sequence postcollisional deformations',
      url='https://agupubs.onlinelibrary.wiley.com/doi/full/10.1029/2009TC002550',
      locator='Paragraphs 11, 61; Figure 8g',
      checked='SE Carpathian main nappe stacking starts 18-20 Ma and terminates around 11 Ma. A later basement-reverse-fault related uplift/exhumation stage starts 3-2 Ma. Earlier 5-6 Ma exhumation has competing tectonic and base-level explanations and is excluded from direct onset fitting.'),
 dict(id='S07', author='Simoes et al.', year=2007, title='Mountain building in Taiwan: A thermokinematic model',
      url='https://agupubs.onlinelibrary.wiley.com/doi/10.1029/2006JB004824',
      locator='Sections 5.9 and model discussion',
      checked='Model spans approximately 6-7 Ma to present; collision onset about 6.5 Ma. Changes in accretion/underplating at 4 and 1.5 Ma. Ongoing duration is lower-censored. The 6-7 Ma range is an approximate age range, without a reported probability density.'),
]

def main():
    init(); rows=[]
    def row(id, family, source, old, young, low, high, kind, weight, role, note):
        rows.append(dict(id=id,family=family,source=source,start_old_Ma=old,start_young_Ma=young,
                         duration_low_Myr=low,duration_high_Myr=high,kind=kind,weight=weight,
                         physical_role=role,note=note))
    row('PYR_distributed','Pyrenees','W21',71,71,31,31,'complete',.5,'shortening_phase_proxy',
        'Full 71-40 Ma phase retained for duration; onset predates simulation and does not enter epoch trigger counts.')
    row('PYR_localized','Pyrenees','W21',40,40,20,20,'complete',.5,'shortening_underplating_phase_proxy',
        '40-20 Ma; same study family as distributed phase; family total weight one.')
    row('CAR_main','SE_Carpathians','M10',20,18,7,9,'interval',.5,'main_thrusting_phase_proxy',
        '18-20 Ma to about 11 Ma; interval endpoints preserved; later uplift remains possible.')
    row('CAR_late','SE_Carpathians','M10',3,2,2,3,'ongoing',.5,'reverse_fault_uplift_phase_proxy',
        'Late stage onset 3-2 Ma. Conservative elapsed lower limit 2 Myr, 3 Myr sensitivity; same regional family.')
    row('NZ_alps','Southern_Alps','C05',8,8,8,8,'ongoing',1.,'rock_uplift',
        'Earliest regional start; 5 and 3 Ma local propagation points are excluded from independent duration counts.')
    row('TAIWAN','Taiwan','S07',7,6,6,7,'ongoing',1.,'mountain_growth_thermokinematic_proxy',
        'Conservative lower limit 6 Myr; upper-onset interpretation tested separately.')
    csvsave(SOURCES/'duration_evidence.csv',rows)
    save(SOURCES/'verified_sources.json',{'checked_date':'2026-09-17','sources':SOURCES_META,
          'verification':'Primary publisher/university pages opened and passages checked. Checked strings are agent paraphrases.',
          'excluded_discovery':'Gagala2012, 35.3-11 Ma, discovered in search; primary page could not be opened in this run, excluded from fitting.'})
    repo_case=REPO/'references/2026-09-13-geological-activity-parameters'
    copies=[(repo_case/'sources/C05/thesis.pdf','Tippett1992.pdf'),
            (repo_case/'sources/C05/thesis.txt','Tippett1992.txt'),
            (repo_case/'tables/C05_Southern_Alps_paired_constraints.csv','C05_paired_constraints.csv'),
            (repo_case/'tables/activity_records.csv','previous_activity_records.csv'),
            (repo_case/'tables/timing_evidence.csv','previous_timing_evidence.csv'),
            (PARENT/'field_pipeline/models/DS5_model.json','DS5_model.json'),
            (PARENT/'field_pipeline/sources/viewer_colormaps.py','viewer_colormaps.py')]
    manifest=[]
    for src,name in copies:
        dst=SOURCES/name
        if not dst.exists():shutil.copyfile(src,dst)
        if sha(src)!=sha(dst):raise ValueError(f'Source changed: {src}')
        manifest.append(dict(original=str(src),copy=name,sha256=sha(dst),bytes=dst.stat().st_size))
    inputs=[]
    for seed in range(1001,1009):
        for sub,names in [('field_pipeline',('field.npz','axis.json','axis_field_parameters.json','metadata.json')),
                          ('window_pipeline',('window.npz','selection.json','display_geometry.json'))]:
            for name in names:
                src=PARENT/sub/f'output/seed{seed}'/name
                inputs.append(dict(path=str(src.relative_to(PARENT)),sha256=sha(src),bytes=src.stat().st_size))
    save(SOURCES/'manifest.json',{'copied':manifest,'spatial_inputs':inputs})
    # Keep publisher acquisition attempts inspectable. Tool-verified extraction above remains available.
    downloads=[]
    for src in SOURCES_META[1:]:
        path=SOURCES/(src['id']+'_publisher.html')
        try:
            if not path.exists():
                req=urllib.request.Request(src['url'],headers={'User-Agent':'Mozilla/5.0'})
                with urllib.request.urlopen(req,timeout=20) as response:body=response.read()
                if len(body)<5000 or b'captcha' in body[:1000].lower():raise ValueError('Publisher challenge/short response')
                path.write_bytes(body)
            downloads.append(dict(id=src['id'],status='saved',path=path.name,sha256=sha(path)))
        except Exception as exc:downloads.append(dict(id=src['id'],status='unavailable',detail=str(exc)))
    save(SOURCES/'download_status.json',downloads)
    print('evidence:',len(rows),'rows,',len(set(r['family'] for r in rows)),'families',flush=True)

if __name__=='__main__':main()
