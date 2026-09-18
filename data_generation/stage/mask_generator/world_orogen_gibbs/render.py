from functools import lru_cache
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
from scipy import ndimage as ndi
from common.render import font as font_loader,scalar_png,contour_png
from world_orogen.render import BACKGROUND,LAND,region_colors,boundary_pixels,mask_image

font=lru_cache(maxsize=20)(font_loader)
INK=(20,20,20)
FORBIDDEN=(65,65,65)


def positions(labels):
    values=[]
    for rid,sl in enumerate(ndi.find_objects(labels),1):
        local=labels[sl]==rid
        d=ndi.distance_transform_edt(np.pad(local,1))[1:-1,1:-1]
        y,x=np.unravel_index(d.argmax(),d.shape)
        values.append((x+sl[1].start+.5,labels.shape[0]-y-sl[0].start-.5))
    return values


def selected_image(labels,state,forbidden):
    colors=np.zeros((len(state)+1,3),np.uint8);colors[:]=BACKGROUND
    for i in range(len(state)):
        if state[i]:colors[i+1]=np.clip(np.array([166,191,228])+(i%5-2)*3,0,255)
        elif forbidden[i]:colors[i+1]=FORBIDDEN
    rgb=colors[labels]
    lines=boundary_pixels(labels)
    rgb[lines]=(rgb[lines].astype(float)*.78).astype(np.uint8)
    return Image.fromarray(np.flipud(rgb))


def render_sample(directory,g,xy,state,metrics,fields,combined,occurrence,contours,seed):
    directory=Path(directory);n=len(state)
    adjacency=[[j for j,length in ns] for ns in g.neighbors]
    colors=region_colors(adjacency);pos=positions(g.labels)
    seed_pic=Image.new('RGB',(500,500),BACKGROUND);draw=ImageDraw.Draw(seed_pic)
    for i,(x,y) in enumerate(xy):
        draw.ellipse((x-2,500-y-2,x+2,500-y+2),fill=FORBIDDEN if g.forbidden[i] else tuple(colors[i+1]))
    rgb=colors[g.labels].copy()
    rgb[g.forbidden[g.labels-1]]=FORBIDDEN
    borders=boundary_pixels(g.labels);rgb[borders]=(rgb[borders]*.75).astype(np.uint8)
    partition_pic=Image.fromarray(np.flipud(rgb))
    chosen=selected_image(g.labels,state,g.forbidden)
    mask=state[g.labels-1]
    pictures=[seed_pic,partition_pic,chosen,mask_image(mask)]
    names=['01_seeds.png','02_partitions.png','03_selection.png','04_mask.png']
    for name,pic in zip(names,pictures):pic.save(directory/name)
    pictures[-1].save(directory/'mask.png')
    # Dense partition IDs are legible in a separate enlarged, nearest-neighbor view.
    zoom=partition_pic.resize((2000,2000),Image.Resampling.NEAREST);draw=ImageDraw.Draw(zoom)
    seed_zoom=seed_pic.resize((2000,2000),Image.Resampling.NEAREST);sd=ImageDraw.Draw(seed_zoom)
    for i,((x,y),(sx,sy)) in enumerate(zip(pos,xy)):
        draw.text((4*x,4*y),str(i+1),font=font(15 if n>512 else 20),fill='white' if g.forbidden[i] else INK,anchor='mm')
        sd.text((4*sx,4*(500-sy)),str(i+1),font=font(15 if n>512 else 20),fill='white',anchor='mm')
    zoom.save(directory/'partition_ids.png');seed_zoom.save(directory/'seed_ids.png')
    margin,gap,header,rowh=24,30,82,608
    canvas=Image.new('RGB',(1078,1322),'white');draw=ImageDraw.Draw(canvas)
    draw.text((margin,10),f'World Orogen 整组选区 · 种子 {seed} · {n} 个分区',font=font(25),fill=INK)
    draw.text((margin,47),'可选入、可取消 · 中心无锁定 · 50% 至 60% 为同等面积偏好',font=font(17),fill=INK)
    titles=['① 放置分区种子','② 分区扩展完成','③ 组合台地区域','④ 提取二值范围']
    captions=[(f'完整域内 {n} 个种子','完整编号见 seed_ids.png'),
              (f'深灰禁选：外围 {g.boundary_layers} 层，共 {g.forbidden.sum()} 区','完整编号见 partition_ids.png'),
              (f'整块选中 {state.sum()} 个分区',f'初始中心分区 {g.center_id+1}：'+('选中' if state[g.center_id] else '未选中')),
              (f'实际占比 {mask.mean():.2%} · 连通部分 {metrics["components_4"]}',
               f'最大块占台地 {metrics["largest_component_fraction"]:.1%} · 偏移 {metrics["center_offset_km"]:.1f} km')]
    for i,(title,pic,caption) in enumerate(zip(titles,pictures,captions)):
        row,col=divmod(i,2);x=margin+col*(500+gap);y=header+row*rowh
        draw.text((x,y),title,font=font(28),fill=INK);canvas.paste(pic,(x,y+46))
        for j,line in enumerate(caption):draw.text((x,y+554+25*j),line,font=font(17),fill=INK)
    canvas.save(directory/'four_stages.png')
    for i,field in enumerate(fields):scalar_png(directory/f'field_{i+1}.png',field,'noise')
    scalar_png(directory/'field_combined.png',combined,'noise')
    scalar_png(directory/'selection_frequency.png',occurrence[g.labels-1],'envelope')
    contour_png(directory/'contours.png',mask,contours)
    return dict(stages=names,layout=dict(margin=margin,gap=gap,header=header,row_height=rowh,tile_y_offset=46),
                label_positions_png_xy=pos,palette=colors.tolist())


def comparison(output,samples,counts,seeds):
    canvas=Image.new('RGB',(48+524*len(counts)-24,110+568*len(seeds)+16),'white');draw=ImageDraw.Draw(canvas)
    layer_values=sorted({s['metrics'].get('excluded_boundary_layers',1) for s in samples})
    layer_text='、'.join(map(str,layer_values))
    title=f'{counts[0]} 分区 · 外围禁选 {layer_text} 层' if len(counts)==1 else f'外围禁选 {layer_text} 层 · 相同种子与随机场对照'
    draw.text((24,12),title,font=font(28),fill=INK)
    for col,count in enumerate(counts):draw.text((24+524*col,63),f'{count} 个分区',font=font(23),fill=INK)
    by={(s['seed'],s['partition_count']):s for s in samples}
    for row,seed in enumerate(seeds):
        for col,count in enumerate(counts):
            s=by.get((seed,count));x,y=24+524*col,110+568*row
            if not s:continue
            canvas.paste(Image.open(output/s['relative_path']/'mask.png'),(x,y));m=s['metrics']
            draw.text((x,y+505),f'种子 {seed} · 占比 {m["fraction"]:.2%} · 连通部分 {m["components_4"]}',font=font(18),fill=INK)
            draw.text((x,y+534),f'最大块 {m["largest_component_fraction"]:.1%} · 第二大块 {m["second_component_fraction"]:.1%}',font=font(17),fill=INK)
    canvas.save(output/'comparison.png')
