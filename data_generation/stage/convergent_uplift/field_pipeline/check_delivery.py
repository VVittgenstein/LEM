from html.parser import HTMLParser
from context import *

class Links(HTMLParser):
    def __init__(self):super().__init__();self.refs=[]
    def handle_starttag(self,tag,attrs):
        for key,value in attrs:
            if key in ('href','src'):self.refs.append(value)

if __name__=='__main__':
    parser=Links();parser.feed((OUT/'gallery.html').read_text(encoding='utf-8'))
    missing=[p for p in parser.refs if not (OUT/p).resolve().exists()]
    if missing:raise ValueError(missing)
    current={p.name:sha(p) for p in MODELS.glob('*model.json')}
    if not all(jload(p)['model_hashes']==current for p in OUT.glob('seed*/metadata.json')):raise ValueError('Changed model after generation')
    jsave(CHECKS/'delivery_links.json',{'passed':True,'references_checked':len(parser.refs),'missing':[], 'sample_model_hashes_current':True})
    print('links',len(parser.refs),'PNG',len(list(OUT.glob('seed*/[AB].png'))),'SVG',len(list(OUT.glob('seed*/[AB].svg'))))
    from finish import finish
    finish()
