"""Re-render saved geometry without consuming sampling streams."""
from common import ROOT,read_json
from render import draw_axis,plot_scale
def main():
    manifest=read_json(ROOT/'output/run_manifest.json')
    for item in manifest['samples']:draw_axis(read_json(ROOT/'output'/item['json']),ROOT/'output')
    plot_scale(read_json(ROOT/'tables/scale_model.json'),ROOT/'checks')
if __name__=='__main__':main()
