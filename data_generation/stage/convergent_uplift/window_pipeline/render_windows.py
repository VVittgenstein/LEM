"""Four separately exported, geometrically linked panels for every sample."""
import argparse,importlib.util,sys
import numpy as np
from PIL import Image
from wcontext import *

LEVELS=np.array([-4000,-3750,-3500,-3250,-3000,-2750,-2500,-2250,-2000,-1750,-1500,-1250,-1000,-750,-500,-453,-400,-350,-300,-250,-200,-150,-100,-80,-60,-40,-20,0.])

def palette():
    spec=importlib.util.spec_from_file_location('window_viewer_palette',INPUT/'viewer_colormaps.py');m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m);return m

def bar_size(span):
    p=10**np.floor(np.log10(span/5));return float(max(t*p for t in (1,2,5,10) if t*p<=span/4))

def draw_base(ax,base,params):
    from matplotlib.colors import LinearSegmentedColormap,SymLogNorm
    colors=['#103866','#3b7ca4','#9dc7da','#e2edf0','#f8f8f4']
    ax.imshow(base['elevation_m'],origin='lower',extent=(0,500,0,500),cmap=LinearSegmentedColormap.from_list('copied_seafloor',colors),
       norm=SymLogNorm(linthresh=100.,linscale=1.,vmin=-4000,vmax=0),interpolation='nearest',zorder=0)

def base_lines(ax,base,params):
    coords=np.arange(500)+.5;mask=base['mask'];types=base['sea_type'];dist=base['distance_km']
    z=np.ma.masked_where(~mask,base['elevation_m'])
    cs=ax.contour(coords,coords,z,levels=LEVELS,colors='#3b5264',linewidths=.38,alpha=.58,zorder=3,corner_mask=False)
    active=[v for v in (-80.,-60.,-40.,-20.) if z.min()<v<z.max()]
    if active:ax.clabel(cs,levels=active,fmt=lambda v:f'{v:.0f}',fontsize=6,inline=True)
    ax.contour(coords,coords,mask.astype(float),levels=[.5],colors='#7f0000',linewidths=1.3,zorder=4,corner_mask=False)
    for code,name in ((1,'shallow'),(2,'deep')):
        if not np.any(types==code):continue
        p=params['profiles'][name]
        for value,color in ((p['width_km'],'#b2182b'),(p['derived']['foot_km'],'#df5b5b')):
            layer=np.ma.masked_where(types!=code,dist)
            if layer.count() and layer.min()<value<layer.max():ax.contour(coords,coords,layer,levels=[value],colors=[color],linewidths=.65,zorder=3,corner_mask=False)
    if np.any(types==1) and np.any(types==2):ax.contour(coords,coords,np.ma.masked_where(mask,(types==2).astype(float)),levels=[.5],colors=['#f4a1a1'],linewidths=.65,zorder=3)

def draw_sample(directory,field_directory=None,color_edges=None,label=None):
    plt=plotting()
    from matplotlib.colors import ListedColormap,BoundaryNorm
    from matplotlib import patheffects as pe
    from matplotlib.ticker import MaxNLocator
    p=Path(directory);s=load(p/'selection.json');seed=s['seed'];src=Path(field_directory) if field_directory is not None else FIELD/f'output/seed{seed}'
    axis=load(src/'axis.json');meta=load(src/'metadata.json');full=np.load(src/'field.npz');crop=np.load(p/'window.npz');base=np.load(BASE/f'seed{seed}/base.npz');params=load(INPUT/'bathymetry_parameters.json')
    x=full['x_km'];y=full['y_km'];u=full['u_m_per_yr']*1000;corners=np.array(s['corners_source_km']);native=meta['array_bounds_km']
    lower=np.minimum([native[0],native[2]],corners.min(axis=0));upper=np.maximum([native[1],native[3]],corners.max(axis=0));center=(lower+upper)/2;span=float(max(upper-lower)*1.04)
    common=[center[0]-span/2,center[0]+span/2,center[1]-span/2,center[1]+span/2]
    edges=np.asarray(color_edges) if color_edges is not None else np.array(load(src/'pair_geometry.json')['color_edges_mm_yr']);colors=palette().banded_colors('fem',12)/255;cmap=ListedColormap(colors);norm=BoundaryNorm(edges,12,clip=True)
    cmap.set_bad((0,0,0,0));records=[]
    titles={'A':'辅助极值线','B':'完整二维抬升场','C':'500×500 km截取窗口','D':'台地、初始海底与截取场'}
    for letter in 'ABCD':
        fig=plt.figure(figsize=(8,8),dpi=180);ax=fig.add_axes([.11,.17,.72,.72]);limits=common if letter!='D' else [0,500,0,500];panel_span=limits[1]-limits[0]
        ax.set_xlim(limits[:2]);ax.set_ylim(limits[2:]);ax.set_aspect('equal',adjustable='box');ax.set_xlabel('x（km）');ax.set_ylabel('y（km）')
        ax.xaxis.set_major_locator(MaxNLocator(5));ax.yaxis.set_major_locator(MaxNLocator(5));ax.grid(alpha=.18,lw=.5)
        if letter in 'BC':
            ax.set_facecolor(colors[0]);im=ax.imshow(u,origin='lower',extent=native,cmap=cmap,norm=norm,interpolation='nearest',zorder=0)
            ax.contour(x,y,full['support'].astype(float),levels=[.5],colors=['#e4f0fa'],linewidths=.65,linestyles='dashed',zorder=2)
        elif letter=='D':
            draw_base(ax,base,params)
            masked=np.ma.masked_where(~crop['support'],crop['u_m_per_yr']*1000)
            im=ax.imshow(masked,origin='lower',extent=(0,500,0,500),cmap=cmap,norm=norm,interpolation='nearest',zorder=1)
            rgba=np.zeros((500,500,4));rgba[:,:,:3]=[1.,.25,.65];rgba[:,:,3]=crop['pink_overlap']*.23
            ax.imshow(rgba,origin='lower',extent=(0,500,0,500),interpolation='nearest',zorder=2)
            base_lines(ax,base,params)
        else:ax.set_facecolor('#fbfcfd')
        line_data=axis['edges'] if letter!='D' else s['axis_parts_local_km']
        for i,xy in enumerate(line_data):
            xy=np.asarray(xy);line,=ax.plot(xy[:,0],xy[:,1],c='#202a34',lw=1.1,zorder=5,solid_capstyle='round',path_effects=[pe.Stroke(linewidth=2.4,foreground='white'),pe.Normal()])
            line.set_gid(f'full_aux_{seed}_{i}' if letter!='D' else f'clipped_aux_{seed}_{i}')
        if letter=='C':
            line,=ax.plot(corners[:,0],corners[:,1],c='#fa2200',lw=2.3,zorder=7,path_effects=[pe.Stroke(linewidth=3.2,foreground='white'),pe.Normal()]);line.set_gid(f'window_500km_{seed}')
        if letter=='D':
            witness=s['witness'];q=np.array(witness['axis_point_local_km']);z=np.array(witness['zero_point_local_km'])
            ax.plot([q[0],z[0]],[q[1],z[1]],'--',c='#293848',lw=1.,zorder=6,path_effects=[pe.Stroke(linewidth=2,foreground='white'),pe.Normal()])
            ax.scatter([z[0]],[z[1]],s=36,facecolor='white',edgecolor='#17232e',lw=1.1,zorder=7)
            offset=(-12,10) if z[0]>350 else (10,10);ha='right' if z[0]>350 else 'left'
            ax.annotate('U=0',z,xytext=offset,textcoords='offset points',ha=ha,fontsize=9,zorder=8,bbox={'fc':'white','ec':'none','alpha':.85,'pad':1.5})
        if letter!='A':
            cax=fig.add_axes([.867,.28,.026,.49]);cb=fig.colorbar(im,cax=cax,boundaries=edges,ticks=edges[::2]);cb.set_label('抬升速率（mm/yr）',fontsize=9)
        fig.text(.11,.958,f'{letter}  {titles[letter]}',fontsize=18)
        sample_label=label or f'种子 {seed}'
        subtitle=f'{sample_label}  ·  完整场与窗口共用坐标范围' if letter!='D' else f'{sample_label}  ·  500×500 km数据域  ·  同一U色标'
        fig.text(.11,.922,subtitle,fontsize=10,color='#465666')
        bar=bar_size(panel_span);w=.72*bar/panel_span;x0=.11;y0=.072
        fig.lines.append(plt.Line2D([x0,x0+w],[y0,y0],transform=fig.transFigure,color='#263747',lw=2.3))
        for xx in (x0,x0+w):fig.lines.append(plt.Line2D([xx,xx],[y0-.005,y0+.005],transform=fig.transFigure,color='#263747',lw=1.2))
        fig.text(x0+w/2,y0+.011,f'{bar:g} km',ha='center',fontsize=10)
        if letter=='C':caption=f"旋转 {s['rotation_deg']:.1f}°  |  红框每边500 km"
        elif letter=='D':caption=f"跨度X {s['span_x_km']:.0f} / Y {s['span_y_km']:.0f} km"
        else:caption=f"完整场峰值 {meta['peak_mm_yr']:.2f} mm/yr"
        fig.text(.83,.082,caption,ha='right',fontsize=9,color='#465666')
        note='A、B、C共用图幅、绘图区尺寸和比例尺。'
        if letter=='D':note=f"粉色：台地与作用范围交集；归零点余量 {s['witness']['margin_km']:.1f} km。"
        fig.text(.11,.027,note,fontsize=8.8,color='#526373')
        fig.canvas.draw();record={'panel':letter,'canvas_px':list(fig.canvas.get_width_height()),'axes_bbox_px':list(map(float,ax.get_window_extent().bounds)),
           'xlim':list(ax.get_xlim()),'ylim':list(ax.get_ylim()),'transform':ax.transData.get_affine().get_matrix().tolist(),'scale_bar_km':bar,'scale_bar_px':w*fig.get_figwidth()*fig.dpi}
        records.append(record);fig.savefig(p/f'{letter}.png',dpi=180);fig.savefig(p/f'{letter}.svg',metadata={'Date':None,'Creator':'LEM boundary-entry window pipeline'});plt.close(fig)
    sheet=Image.new('RGB',(2880,2880),'white')
    for k,letter in enumerate('ABCD'):
        with Image.open(p/f'{letter}.png') as im:sheet.paste(im.convert('RGB'),((k%2)*1440,(k//2)*1440))
    sheet.save(p/'ABCD.png');sheet.resize((1800,1800),Image.Resampling.LANCZOS).save(p/'preview.png')
    save(p/'display_geometry.json',{'panels':records,'common_extent_km':common,'window_side_km':500.,'palette':'FEM',
      'palette_source_sha256':sha(INPUT/'viewer_colormaps.py'),'color_edges_mm_yr':edges.tolist(),'colors_rgba_uint8':palette().banded_colors('fem',12).tolist(),
      'pink_rgba':[1.,.25,.65,.23],'pink_definition':'platform_mask AND cropped continuous uplift > 0',
      'elevation_contours_unit':'m','uplift_unit':'mm/yr','D_base_array_sha256':sha(BASE/f'seed{seed}/base.npz')})
    print('rendered ABCD',seed,flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',default='output');a=p.parse_args();out=(ROOT/a.output).resolve()
    if not out.is_relative_to(ROOT):raise ValueError('Output outside module')
    for row in load(out/'batch.json')['samples']:draw_sample(out/f"seed{row['seed']}")
