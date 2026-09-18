"""Artifact links, portable figure counts, and final delivery completeness."""
from html.parser import HTMLParser
from urllib.parse import unquote,urlsplit
import re, zipfile
from tcontext import *

class Links(HTMLParser):
    def __init__(self):super().__init__();self.paths=[]
    def handle_starttag(self,tag,attrs):
        for key,value in attrs:
            if key in ('href','src') and value:self.paths.append(value)

def main():
    parser=Links();parser.feed((OUT/'gallery.html').read_text(encoding='utf-8'));checked=[]
    for link in parser.paths:
        if link.startswith('#') or urlsplit(link).scheme:continue
        p=(OUT/unquote(link.split('#')[0])).resolve();assert p.is_file(),(link,str(p));checked.append(str(p))
    batch=load(OUT/'batch.json');expected=len(batch['events'])
    for ext in ('png','svg'):
        with zipfile.ZipFile(OUT/f'all_E_{ext}.zip') as z:assert len(z.namelist())==expected
        with zipfile.ZipFile(OUT/f'all_ABCDE_{ext}.zip') as z:assert len(z.namelist())==5*expected
    first_count=sum(bool(s['events']) for s in load(OUT/'schedules.json'))
    with zipfile.ZipFile(OUT/'eight_first_E_png.zip') as z:assert len(z.namelist())==first_count
    for item in batch['events']:
        p=OUT/f"seed{item['seed']}/event{item['event_index']:02d}";svg=(p/'E.svg').read_text(encoding='utf-8')
        assert '<svg' in svg and 'data:image/png;base64,' in svg
        geometry=load(p/'E_geometry.json');assert '现代' in svg
        assert svg.count('id="scale_')==len(geometry['panels'])
    save(CHECKS/'links.json',dict(passed=True,local_links=len(checked),all_E_per_archive=expected,all_ABCDE_per_archive=5*expected,first_activity_archive=first_count))
    print('links and archives checked',len(checked),flush=True)

if __name__=='__main__':main()
