"""Create searchable text and link inventories from the downloaded public pages."""
from html.parser import HTMLParser
from workspace import ROOT, target, write_json

class Reader(HTMLParser):
    def __init__(self):
        super().__init__();self.skip=0;self.parts=[];self.links=[]
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style'): self.skip+=1
        if tag in ('p','h1','h2','h3','h4','li','tr','br'):self.parts.append('\n')
        if tag=='a':
            attrs=dict(attrs)
            if 'href' in attrs:self.links.append(attrs['href'])
    def handle_endtag(self,tag):
        if tag in ('script','style'):self.skip=max(0,self.skip-1)
        if tag in ('p','h1','h2','h3','h4','li','tr'):self.parts.append('\n')
    def handle_data(self,data):
        if not self.skip:self.parts.append(data)

def main():
    for folder in sorted((ROOT/'sources/new').iterdir()):
        for source in folder.glob('*.html'):
            reader=Reader();reader.feed(source.read_text(encoding='utf-8',errors='replace'))
            lines=[' '.join(x.split()) for x in ''.join(reader.parts).splitlines()]
            target(f'output/extracted/{folder.name}_{source.stem}.txt').write_text('\n'.join(x for x in lines if x)+'\n',encoding='utf-8')
            write_json(f'output/extracted/{folder.name}_{source.stem}_links.json',sorted(set(reader.links)))

if __name__=='__main__':main()
