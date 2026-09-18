"""Four-panel data views in the user's requested layout."""
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

from common.render import font as load_font

BACKGROUND = (30,30,30)
LAND = (82,129,200)
INK = (20,20,20)
PALETTE = [(197,216,243),(203,232,234),(210,238,218),(250,230,204),
           (248,238,201),(245,216,231),(222,214,240),(223,236,205),
           (203,225,236),(247,216,208),(232,225,207),(215,237,233)]
font = lru_cache(maxsize=16)(load_font)


def mask_image(mask):
    palette = np.asarray([BACKGROUND,LAND],np.uint8)
    return Image.fromarray(palette[np.flipud(mask).astype(np.uint8)])


def decode_mask(path):
    with Image.open(path) as image:
        pixels = np.asarray(image.convert("RGB"))
    land = np.all(pixels == LAND,axis=2)
    sea = np.all(pixels == BACKGROUND,axis=2)
    if not np.all(land | sea):
        raise ValueError("mask PNG contains an unexpected color")
    return np.flipud(land).copy()


def region_colors(adjacency):
    choices = [-1]*len(adjacency)
    for i in sorted(range(len(adjacency)),key=lambda j:(-len(adjacency[j]),j)):
        occupied = {choices[j] for j in adjacency[i]}
        choices[i] = next(c for c in range(len(PALETTE)) if c not in occupied)
    return np.asarray([BACKGROUND]+[PALETTE[c] for c in choices],np.uint8)


def label_positions(labels):
    positions=[]
    for region in range(1,int(labels.max())+1):
        distance=ndi.distance_transform_edt(np.pad(labels == region,1))[1:-1,1:-1]
        row,col=np.unravel_index(np.argmax(distance),labels.shape)
        positions.append((float(col)+.5,labels.shape[0]-(float(row)+.5)))
    return positions


def boundary_pixels(labels):
    boundary=np.zeros(labels.shape,bool)
    boundary[1:] |= labels[1:] != labels[:-1]
    boundary[:,1:] |= labels[:,1:] != labels[:,:-1]
    return boundary & (labels>0)


def add_labels(image, positions, ids, root=None):
    draw=ImageDraw.Draw(image)
    size=16 if len(positions)>35 else 20
    for rid in ids:
        x,y=positions[rid-1]
        draw.text((x,y),str(rid),font=font(size),fill=INK,anchor="mm")
        if rid==root:
            radius=18 if size==16 else 22
            draw.ellipse((x-radius,y-radius,x+radius,y+radius),outline=INK,width=2)
    return image


def selection_image(labels, selected_ids, positions, root):
    lookup=np.zeros(int(labels.max())+1,bool);lookup[selected_ids]=True
    selected=lookup[labels]
    colors=np.zeros((len(lookup),3),np.uint8);colors[:]=BACKGROUND
    for rid in selected_ids:
        offset=(rid%5-2)*3
        colors[rid]=np.clip(np.array([166,191,228])+offset,0,255)
    rgb=colors[labels]
    borders=boundary_pixels(labels)&selected
    rgb[borders]=(rgb[borders].astype(float)*.91).astype(np.uint8)
    image=Image.fromarray(np.flipud(rgb))
    return add_labels(image,positions,selected_ids,root)


def render_sample(partitions,result,directory:Path,make_frames=True):
    labels=partitions.labels
    count=partitions.settings.partition_count
    colors=region_colors(result.geometry.adjacency)
    positions=label_positions(labels)
    seed_image=Image.new("RGB",(500,500),BACKGROUND)
    draw=ImageDraw.Draw(seed_image)
    draw.rectangle((10,10,489,489),outline=(65,65,65),width=1)
    for rid,(x,y) in enumerate(partitions.seeds_xy,1):
        y=500-y
        draw.ellipse((x-5,y-5,x+5,y+5),fill=tuple(colors[rid]))
        tx=max(12,min(482,float(x)+8));ty=max(12,min(485,float(y)-8))
        draw.text((tx,ty),str(rid),font=font(14),fill=tuple(colors[rid]),anchor="mm")
    rgb=colors[labels]
    edges=boundary_pixels(labels)
    rgb[edges]=(rgb[edges].astype(float)*.85).astype(np.uint8)
    partition_image=add_labels(Image.fromarray(np.flipud(rgb)),positions,list(range(1,count+1)))
    chosen_image=selection_image(labels,result.order,positions,result.order[0])
    final_image=mask_image(result.mask)
    stages=[seed_image,partition_image,chosen_image,final_image]
    stage_names=["01_seeds.png","02_partitions.png","03_selection.png","04_mask.png"]
    for name,image in zip(stage_names,stages):
        image.save(directory/name)
    final_image.save(directory/"mask.png")
    if make_frames:
        steps=directory/"steps";steps.mkdir(exist_ok=True)
        for index in range(len(result.order)):
            selection_image(labels,result.order[:index+1],positions,result.order[0]).save(steps/f"{index:03d}.png")
    width,margin,gap,header,row_h=1078,24,30,82,608
    canvas=Image.new("RGB",(width,header+row_h*2+24),"white")
    draw=ImageDraw.Draw(canvas)
    draw.text((margin,10),f"World Orogen 平面改造 · 种子 {partitions.seed} · {count} 个分区",font=font(25),fill=INK)
    draw.text((margin,47),f"位置权重 {partitions.settings.center_weight:g} · 成片权重 {partitions.settings.connection_weight:g} · 工程试验",font=font(17),fill=INK)
    titles=["① 放置分区种子","② 分区扩展完成","③ 组合台地区域","④ 提取二值范围"]
    captions=[("编号对应分区起点","外圈 10 格为海洋带"),
              (f"不同颜色区分分区，共 {count} 个","全部分区已分配，编号与起点一致"),
              (f"完整加入 {len(result.order)}/{count} 个分区",f"圆圈标出唯一的起始分区 {result.order[0]}"),
              (f"目标偏好 {result.target_fraction:.2%} · 实际 {result.mask.mean():.2%}",
               f"连通部分 {result.statistics['region_component_count']} · 面积中心偏移 {result.statistics['centroid_offset_km']:.1f} km")]
    for i,(title,picture,caption) in enumerate(zip(titles,stages,captions)):
        row,col=divmod(i,2)
        x,y=margin+col*(500+gap),header+row*row_h
        draw.text((x,y),title,font=font(29),fill=INK)
        canvas.paste(picture,(x,y+46))
        draw.rectangle((x-1,y+45,x+500,y+546),outline=(215,215,215),width=1)
        for j,line in enumerate(caption):
            draw.text((x,y+554+j*25),line,font=font(17),fill=INK)
    canvas.save(directory/"four_stages.png")
    return {"stage_files":stage_names,"palette":colors.tolist(),"label_positions_png_xy":positions,
            "raw_mask_colors":{"ocean":list(BACKGROUND),"platform":list(LAND)},
            "four_stage_layout":{"size":list(canvas.size),"tile_size":500,"margin":margin,"gap":gap,"header":header,"row_height":row_h,"tile_y_offset":46}}


def comparison(output:Path,samples:list[dict],counts,seeds):
    tile,margin,gap,head,row_h=500,24,24,110,574
    image=Image.new("RGB",(margin*2+len(counts)*tile+(len(counts)-1)*gap,head+len(seeds)*row_h+20),"white")
    draw=ImageDraw.Draw(image)
    draw.text((margin,14),"同种子、同目标占比：分区数量对照",font=font(28),fill=INK)
    for col,count in enumerate(counts):
        draw.text((margin+col*(tile+gap),65),f"{count} 个分区",font=font(24),fill=INK)
    by={(s['seed'],s['partition_count']):s for s in samples}
    for row,seed in enumerate(seeds):
        for col,count in enumerate(counts):
            sample=by[(seed,count)]
            x,y=margin+col*(tile+gap),head+row*row_h
            with Image.open(output/sample['relative_path']/"mask.png") as source:
                image.paste(source,(x,y))
            m=sample['metrics']
            draw.text((x,y+508),f"种子 {seed} · 实际 {m['fraction']:.2%} · 连通部分 {m['components_4']}",font=font(19),fill=INK)
            draw.text((x,y+538),f"最大块占台地 {m['largest_component_fraction']:.1%} · 中心偏移 {m['centroid_offset_km']:.1f} km",font=font(16),fill=INK)
    image.save(output/"comparison.png")


def weight_comparison(output:Path,seeds):
    from common.io import read_json,write_json
    other=output/'weight_comparison_96_32'
    if not all((other/f'partitions_56/seed{s}/metrics.json').is_file() and
               (output/f'partitions_56/seed{s}/metrics.json').is_file() for s in seeds):
        return False
    margin,gap,tile,head,row_h=24,24,500,110,574
    image=Image.new('RGB',(margin*2+tile*2+gap,head+len(seeds)*row_h+20),'white')
    draw=ImageDraw.Draw(image)
    draw.text((margin,14),'相同56分区图、相同种子：选择权重对照',font=font(28),fill=INK)
    records=[]
    for row,seed in enumerate(seeds):
        configs=[]
        for col,folder in enumerate((output,other)):
            directory=folder/f'partitions_56/seed{seed}'
            config=read_json(directory/'config.json');configs.append(config)
            metrics=read_json(directory/'metrics.json')
            x,y=margin+col*(tile+gap),head+row*row_h
            if row==0:
                draw.text((x,65),f"位置权重 {config['center_weight']:g} · 成片权重 {config['connection_weight']:g}",font=font(23),fill=INK)
            with Image.open(directory/'mask.png') as source:image.paste(source,(x,y))
            draw.text((x,y+508),f"种子 {seed} · 实际 {metrics['fraction']:.2%} · 连通部分 {metrics['components_4']}",font=font(19),fill=INK)
            draw.text((x,y+538),f"最大块占台地 {metrics['largest_component_fraction']:.1%} · 均方根中心距离 {metrics['rms_distance_to_preferred_center_km']:.1f} km",font=font(15),fill=INK)
        same=configs[0]['partition_array_sha256']==configs[1]['partition_array_sha256']
        target=configs[0]['target_fraction']==configs[1]['target_fraction']
        if not same or not target:raise ValueError('weight comparison requires identical partitions and target fractions')
        records.append({'seed':seed,'identical_partition_arrays':same,'identical_target_fraction':target})
    image.save(output/'weight_comparison.png')
    write_json(output/'weight_comparison.json',{'pairs':records,'all_pairs_match':True})
    return True
