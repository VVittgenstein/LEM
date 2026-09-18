"""Independent readback checks of the saved delivery and its replay images."""
from dataclasses import fields
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote,urlsplit
import json

import numpy as np
from PIL import Image

from common.contours import rasterize_contours
from common.io import array_sha256,file_sha256,read_json,utc_now,write_json
from .config import Settings
from .partitions import PartitionMap,generate_partitions
from .selection import generate_mask
from .render import decode_mask,selection_image


class LocalLinks(HTMLParser):
    def __init__(self):
        super().__init__();self.links=[];self.script_data=[];self.in_data=False

    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        for name in ('href','src'):
            if name in attrs:self.links.append(attrs[name])
        if tag=='script' and attrs.get('id')=='trace-data':self.in_data=True

    def handle_endtag(self,tag):
        if tag=='script':self.in_data=False

    def handle_data(self,data):
        if self.in_data:self.script_data.append(data)


def audit_cohort(output,counts,seeds,partition_replay=False):
    files_checked,frames_checked=0,0
    records=[]
    settings_names={f.name for f in fields(Settings)}
    with Image.open(output/'comparison.png') as image:
        comparison=np.asarray(image.convert('RGB'))
    for col,count in enumerate(counts):
        for row,seed in enumerate(seeds):
            directory=output/f'partitions_{count}/seed{seed}'
            config=read_json(directory/'config.json')
            settings=Settings(**{k:config[k] for k in settings_names})
            labels=np.load(directory/'partitions.npy',allow_pickle=False)
            mask=np.load(directory/'mask.npy',allow_pickle=False)
            assert array_sha256(labels)==config['partition_array_sha256']
            assert array_sha256(mask)==config['mask_array_sha256']
            assert np.array_equal(decode_mask(directory/'mask.png'),mask)
            assert np.array_equal(rasterize_contours(read_json(directory/'contours.json')),mask)
            with np.load(directory/'coarse_partitions.npz',allow_pickle=False) as coarse:
                points,coarse_labels=coarse['points_normalized'],coarse['labels_zero_based']
            with np.load(directory/'projection.npz',allow_pickle=False) as projection:
                dx,dy=projection['dx_km'],projection['dy_km']
            generation=read_json(directory/'partition_generation.json')
            partition=PartitionMap(settings,seed,labels,np.asarray(generation['seed_xy_km']),points,coarse_labels,generation,dx,dy)
            replay=generate_mask(partition,config['target_fraction'])
            saved=read_json(directory/'selection.json')
            assert replay.order==saved['order'] and replay.trace==saved['steps']
            assert np.array_equal(replay.mask,mask)
            layout=config['views']['four_stage_layout']
            with Image.open(directory/'four_stages.png') as board:
                for i,name in enumerate(config['views']['stage_files']):
                    rr,cc=divmod(i,2)
                    x=layout['margin']+cc*(500+layout['gap'])
                    y=layout['header']+rr*layout['row_height']+layout['tile_y_offset']
                    with Image.open(directory/name) as tile:
                        assert tile.size==(500,500)
                        assert np.array_equal(np.asarray(board.crop((x,y,x+500,y+500))),np.asarray(tile))
                        files_checked+=1
            positions=config['views']['label_positions_png_xy']
            for step in saved['steps']:
                expected=selection_image(labels,step['selected_regions'],positions,saved['initial_region'])
                with Image.open(directory/'steps'/f"{step['step']:03d}.png") as actual:
                    assert np.array_equal(np.asarray(expected),np.asarray(actual))
                frames_checked+=1
            x,y=24+col*524,110+row*574
            with Image.open(directory/'mask.png') as actual:
                assert np.array_equal(comparison[y:y+500,x:x+500],np.asarray(actual))
            replayed_partition=False
            if partition_replay and seed==seeds[0]:
                regenerated=generate_partitions(seed,settings)
                assert np.array_equal(regenerated.labels,labels)
                replayed_partition=True
            records.append({'seed':seed,'partition_count':count,'selection_trace_exact':True,
                'mask_and_contours_roundtrip':True,'four_stage_tiles_exact':True,
                'all_step_images_match_saved_choices':True,'partition_regenerated_and_matched':replayed_partition})
    html=(output/'report.html').read_text(encoding='utf-8')
    parser=LocalLinks();parser.feed(html)
    checked_links=0
    for link in parser.links:
        parsed=urlsplit(link)
        if not parsed.scheme and parsed.path:
            assert (output/unquote(parsed.path)).is_file(),link
            checked_links+=1
    payload=json.loads(''.join(parser.script_data))
    assert len(payload)==len(records)
    for key,steps in payload.items():
        p,s=key[1:].split('s')
        assert steps==read_json(output/f'partitions_{p}/seed{s}/selection.json')['steps']
    result={'created_utc':utc_now(),'passed':True,'sample_count':len(records),
            'stage_images_verified':files_checked,'replay_frames_verified':frames_checked,
            'local_html_links_verified':checked_links,'embedded_trace_sets_verified':len(payload),
            'records':records,'browser_interaction':'not performed; file URL access is blocked by the browser tool policy'}
    write_json(output/'delivery_checks.json',result)
    return result


def verify_manifest(output):
    record=read_json(output/'manifest.json')
    for entry in record['output_files']:
        assert file_sha256(output/entry['path'])==entry['sha256'],entry['path']
    for entry in record['code_files']:
        assert file_sha256(Path(entry['path']))==entry['sha256'],entry['path']
    return len(record['output_files'])
