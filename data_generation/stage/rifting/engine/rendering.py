from __future__ import annotations
import os,math,argparse,time,shutil
from pathlib import Path
os.environ.setdefault('MPLCONFIGDIR',str(Path(__file__).resolve().parents[1]/'output'/'matplotlib-cache'))
import numpy as np
from PIL import Image,ImageDraw,ImageFont
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap,BoundaryNorm
from matplotlib.patches import Rectangle,Patch
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from .common import ROOT,OUT,load,save,stress_display
from .products import Run,mask_coverage
from .forcing import score_windows,amplitude
from .faults import geometry_at
from reporting.viewer_palette import banded_colors

Image.MAX_IMAGE_PIXELS=None
plt.rcParams.update({'font.family':'Microsoft YaHei','axes.unicode_minus':False,'font.size':10,'savefig.facecolor':'white'})
COLORS=banded_colors()[:,:3]
CMAP=ListedColormap(COLORS/255.)
NAMES={'far':'大尺度应力场','local':'小尺度应力场','total':'合并应力场'}
RUN=None

def init_worker(seed):
    global RUN
    RUN=Run(seed)

def norm_for(a,b):return BoundaryNorm(np.linspace(a,b,13),12,clip=True)
def font(size):return ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',size)
def band(values,vmin,vmax):return np.clip(np.floor((values-vmin)/max(vmax-vmin,1e-20)*12),0,11).astype(np.uint8)

def stress_rgb(values,limit,blank_zero=False):
    result=COLORS[band(values,0,limit)]
    if blank_zero:result[values==0]=255
    return result

def coverage(run,t):
    score,eligible=score_windows(run.basis,run.episodes,t,run.length,run.window['threshold'],run.window['minimum_distance_from_side_km'])
    return mask_coverage(eligible,run.length)

def mark_sources(ax,run,t,kind,origin=(0,0),size=None):
    size=size or run.length
    for e in run.episodes:
        if e['start_Myr']>t or (kind!='total' and e['kind']!=kind):continue
        pos=np.array(e['position_km'][:2])-origin;direction=np.array(e['direction'][:2]);strength=float(amplitude(e,t))
        if not (-size*.05<=pos[0]<=size*1.05 and -size*.05<=pos[1]<=size*1.05):continue
        color=('#dd6a19' if e['kind']=='far' else '#156b84') if strength>1e-8 else '#777777'
        ax.plot(*pos,'o',ms=4,color=color,zorder=8)
        if strength>1e-8:
            ax.annotate('',xy=pos+direction/max(np.linalg.norm(direction),1e-12)*size*.035,xytext=pos,
                arrowprops=dict(arrowstyle='-|>',lw=1.8,color=color),annotation_clip=False)
        offset=(5,-15 if pos[1]>size*.93 else 7)
        ax.annotate(e['id'],pos,xytext=offset,textcoords='offset points',fontsize=7,color=color,
            bbox=dict(facecolor='white',alpha=.85,edgecolor='none',pad=1),annotation_clip=False)

def stress_preview(run,frame,kind,mag,angle,green=None,window=False,limit_override=None):
    fig,ax=plt.subplots(figsize=(7.1,7.0),layout='constrained')
    fig.get_layout_engine().set(rect=(0,.045,1,.95))
    limit=limit_override or run.scale['stress_local_MPa_max' if kind=='local' else 'stress_MPa_max'];L=mag.shape[0]
    color_map=CMAP.copy();values=mag
    if kind=='local':
        color_map.set_bad('white');values=np.ma.masked_equal(mag,0)
    artist=ax.imshow(values,origin='lower',extent=[0,L,0,L],cmap=color_map,norm=norm_for(0,limit),interpolation='nearest')
    step=max(1,int(L/30));yy,xx=np.mgrid[step//2:L:step,step//2:L:step];a=angle[yy,xx]
    valid=mag[yy,xx]>1e-7
    ink=np.where(band(mag[yy,xx][valid],0,limit)<4,'#eeeeee','#222222')
    ax.quiver(xx[valid]+.5,yy[valid]+.5,np.cos(a[valid]),np.sin(a[valid]),headlength=0,headaxislength=0,headwidth=0,
        color=ink,pivot='middle',width=.0012,scale=42,zorder=4)
    if green is not None:
        rgba=np.zeros((*green.shape,4),np.float32);rgba[...,1]=.9;rgba[...,0]=.1;rgba[...,3]=green*.17
        ax.imshow(rgba,origin='lower',extent=[0,L,0,L],interpolation='nearest',zorder=3)
    if window:
        origin=run.window['origin_km'];ax.add_patch(Rectangle(origin,500,500,fill=False,edgecolor='#e3242b',lw=2.1,zorder=7))
    mark_sources(ax,run,frame['elapsed_Myr'],kind)
    ax.set(xlim=(-L*.055,L*1.055),ylim=(-L*.055,L*1.055),xlabel='X / km',ylabel='Y / km')
    ax.add_patch(Rectangle((0,0),L,L,fill=False,edgecolor='#303842',lw=.9))
    ax.set_title(f"{NAMES[kind]}\n模拟 {frame['elapsed_Myr']:.3f} Myr · 距今 {frame['age_Ma_BP']:.3f} Ma")
    if kind=='local':
        ax.set_title(ax.get_title()+'\n小尺度分量独立色标，范围跨时间固定')
        ax.legend(handles=[Patch(facecolor='white',edgecolor='#777777',label='0 MPa：白色')],loc='lower left',fontsize=7)
    elif limit_override:ax.set_title(ax.get_title()+'\n独立色标，范围跨时间固定')
    bar=fig.colorbar(artist,ax=ax,shrink=.78,pad=.025);bar.set_label('水平差应力 / MPa')
    fig.text(.5,.022,f'3D求解水平网格 {run.length/(run.basis.shape[1]-1):g} km；1 km查询格距；诊断深度10 km。',ha='center',fontsize=7)
    fig.text(.5,.003,'方向预览抽样显示；逐格原图保留每个1 km格子。作用箭头等长表示方向。',ha='center',fontsize=7)
    return fig

def glyph_table(p=12):
    glyph=[]
    for i in range(181):
        img=Image.new('1',(p,p));draw=ImageDraw.Draw(img);c=(p-1)/2
        if i==180:draw.ellipse((c-1,c-1,c+1,c+1),outline=1)
        else:
            theta=i*np.pi/180;dx=(p-3)/2*np.cos(theta);dy=-(p-3)/2*np.sin(theta)
            draw.line((c-dx,c-dy,c+dx,c+dy),fill=1,width=1)
        glyph.append(np.array(img,bool))
    return np.array(glyph)

def full_resolution(path,mag,angle,vmax,green=None,p=12,blank_zero=False):
    n=mag.shape[0];indices=band(mag,0,vmax);g=green
    if blank_zero:indices[mag==0]=255
    palette=np.zeros((256,3),np.uint8);palette[:12]=COLORS
    palette[12:24]=np.rint(COLORS*.82+np.array([30,210,65])*.18)
    palette[250]=[235,235,235];palette[251]=[24,29,38];palette[252]=[240,240,240];palette[255]=[255,255,255]
    direction=(np.rad2deg(angle)%180).astype(np.int16);direction[mag<=1e-7]=180
    glyph=glyph_table(p)
    raster=np.empty((n*p,n*p),np.uint8)
    for start in range(0,n,32):
        stop=min(n,start+32);idx=indices[n-stop:n-start][::-1].copy()
        if g is not None:idx+=12*g[n-stop:n-start][::-1].astype(np.uint8)
        dense=np.repeat(np.repeat(idx,p,axis=0),p,axis=1)
        signs=glyph[direction[n-stop:n-start][::-1]].transpose(0,2,1,3).reshape((stop-start)*p,n*p)
        if blank_zero:signs&=np.repeat(np.repeat(idx!=255,p,axis=0),p,axis=1)
        light=palette[idx].astype(float)@np.array([.2126,.7152,.0722])
        ink=np.repeat(np.repeat(np.where(light>110,251,252).astype(np.uint8),p,axis=0),p,axis=1)
        dense[signs]=ink[signs]
        dense[::p,:]=250;dense[:,::p]=250
        raster[start*p:stop*p]=dense
    image=Image.fromarray(raster);image.putpalette(palette.ravel().tolist())
    image.save(path,optimize=False,compress_level=1)
    del image,raster

def fault_surfaces(f,t,origin):
    trace=geometry_at(f,t)
    if not len(trace):return []
    dip=math.radians(f['dip_deg']);direction=np.array([math.cos(f['dip_direction_rad']),math.sin(f['dip_direction_rad'])])
    bottom=trace+direction*f['bottom_depth_km']/math.tan(dip)
    top=np.column_stack([trace-origin,np.zeros(len(trace))]);bottom=np.column_stack([bottom-origin,np.full(len(trace),f['bottom_depth_km'])])
    return [np.array([top[i],top[i+1],bottom[i+1],bottom[i]]) for i in range(len(trace)-1)]

def fault_plot_limits(run):
    origin=np.asarray(run.window['origin_km']);coordinates=[np.array([[0,0],[500,500]])]
    for f in run.faults:
        trace=np.asarray(f['trace_xy_km'])-origin
        direction=np.array([math.cos(f['dip_direction_rad']),math.sin(f['dip_direction_rad'])])
        coordinates.extend([trace,trace+direction*f['bottom_depth_km']/math.tan(math.radians(f['dip_deg']))])
    points=np.concatenate(coordinates)
    return [float(np.floor((points.min()-30)/50)*50),float(np.ceil((points.max()+30)/50)*50)]

def fault_figures(run,frame,rates,U,displacement,outdir):
    t=frame['elapsed_Myr'];origin=np.array(run.window['origin_km']);active=rates.max(axis=1)>1e-10
    limits=fault_plot_limits(run);exaggeration=(limits[1]-limits[0])*.5/25
    fig,ax=plt.subplots(figsize=(8.5,7.5),layout='constrained')
    ax.add_patch(Rectangle((0,0),500,500,facecolor='#f6f7f8',edgecolor='#e3242b',lw=1.5))
    for i,f in enumerate(run.faults):
        trace=geometry_at(f,t)-origin
        if not len(trace):continue
        color='#af4f18' if active[i] else '#787d84';ax.plot(trace[:,0],trace[:,1],'-' if active[i] else '--',color=color,lw=1.2)
        mid=trace[len(trace)//2];ax.text(*mid,f['id'],fontsize=7,bbox=dict(facecolor='white',alpha=.8,pad=1,edgecolor='none'))
        direction=np.array([math.cos(f['dip_direction_rad']),math.sin(f['dip_direction_rad'])])
        ax.arrow(*mid,*(direction*12),head_width=4,color=color,length_includes_head=True)
    ax.axhline(250,color='#477ca2',lw=.7,ls=':');ax.axvline(250,color='#477ca2',lw=.7,ls=':');ax.plot([0,500],[0,500],color='#477ca2',lw=.7,ls=':')
    for name,x,y in [('A',5,255),('B',255,490),('C',455,465)]:ax.text(x,y,name,color='#477ca2',fontsize=9)
    ax.set(xlim=limits,ylim=limits,aspect='equal',xlabel='数据域X / km',ylabel='数据域Y / km',title=f"断层 · 模拟 {t:.3f} Myr · 距今 {48-t:.3f} Ma\n实线：活动；虚线：已形成、当前未活动；箭头：倾向")
    fig.savefig(outdir/'06_faults.png',dpi=180);plt.close(fig)
    fig=plt.figure(figsize=(13,6),layout='constrained')
    for panel,(elev,azim) in enumerate([(27,-57),(16,30)]):
        ax=fig.add_subplot(1,2,panel+1,projection='3d')
        for i,f in enumerate(run.faults):
            polys=fault_surfaces(f,t,origin)
            if not polys:continue
            color='#e79556' if active[i] else '#b3b9c0'
            ax.add_collection3d(Poly3DCollection(polys,facecolor=color,alpha=.45,edgecolor='#4c5058',linewidth=.2))
            centre=np.array(f['centre_km'])-origin
            if active[i]:ax.text(*centre,0,f['id'],fontsize=7)
        ax.plot([0,500,500,0,0],[0,0,500,500,0],np.zeros(5),color='#e3242b',lw=1)
        ax.set(xlim=limits,ylim=limits,zlim=(25,0),xlabel='X / km',ylabel='Y / km',zlabel='深度 / km' if panel==0 else '')
        ax.set_box_aspect((1,1,.5));ax.view_init(elev=elev,azim=azim)
    fig.suptitle(f'三维断层面 · 模拟 {t:.3f} Myr · 垂向显示放大{exaggeration:g}倍，深度数值保持原单位')
    fig.text(.5,.015,'橙色面：当前活动，直接标注编号；灰色面：已有未活动断层，编号对应平面图与断层表。',ha='center',fontsize=8)
    fig.savefig(outdir/'06_faults_3d.png',dpi=160);plt.close(fig)
    fig,axes=plt.subplots(1,3,figsize=(15,4.6),layout='constrained')
    sections=[('A',[0,250],[1,0],500),('B',[250,0],[0,1],500),('C',[0,0],[2**-.5,2**-.5],500*2**.5)]
    for ax,(name,base,direction,length) in zip(axes,sections):
        base=np.array(base);direction=np.array(direction);normal=np.array([-direction[1],direction[0]])
        for i,f in enumerate(run.faults):
            polys=fault_surfaces(f,t,origin)
            label_position=None
            for poly in polys:
                distance=(poly[:,:2]-base)@normal;points=[]
                for j in range(4):
                    k=(j+1)%4
                    if distance[j]*distance[k]<0:
                        a=distance[j]/(distance[j]-distance[k]);point=poly[j]+a*(poly[k]-poly[j]);points.append(point)
                if len(points)==2:
                    pts=np.asarray(points);position=(pts[:,:2]-base)@direction
                    if max(position)<0 or min(position)>length:continue
                    ax.plot(position,pts[:,2],'-' if active[i] else '--',color='#b66729' if active[i] else '#888888',lw=1)
                    if label_position is None:label_position=(float(np.mean(position)),float(np.mean(pts[:,2])))
            if label_position is not None:ax.text(*label_position,f['id'],fontsize=6.5,bbox=dict(facecolor='white',alpha=.8,pad=.5,edgecolor='none'))
        ax.set(xlim=(0,length),ylim=(25,0),xlabel='剖面距离 / km',ylabel='深度 / km',title=f'{name}剖面')
        ax.grid(alpha=.15)
    fig.suptitle(f'固定剖面与断层交线 · 模拟 {t:.3f} Myr；剖面位置见平面图')
    fig.savefig(outdir/'06_sections.png',dpi=160);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(12.6,6),layout='constrained')
    for ax,values,key,title,unit in [(axes[0],U*1000,'U_mm_per_year','构造U','mm/yr'),(axes[1],displacement,'displacement_m','累计垂向位移','m')]:
        vmin,vmax=run.scale[key+'_min'],run.scale[key+'_max']
        im=ax.imshow(values,origin='lower',extent=[0,500,0,500],cmap=CMAP,norm=norm_for(vmin,vmax),interpolation='nearest')
        if values.min()<0<values.max():ax.contour(np.arange(500)+.5,np.arange(500)+.5,values,levels=[0],colors='#222222',linewidths=.45)
        if np.max(abs(values))<1e-12:ax.text(250,250,'全域为零',ha='center',bbox=dict(facecolor='white',edgecolor='none',alpha=.9))
        ax.set(xlabel='数据域X / km',ylabel='数据域Y / km',title=f'{title}\n当前范围 {values.min():.3g} 至 {values.max():.3g} {unit}')
        cb=fig.colorbar(im,ax=ax,shrink=.75,pad=.025);cb.set_label(unit);cb.ax.axhline(0,color='#111111',lw=1)
    fig.suptitle(f'正值抬升 · 负值沉降 · 黑线为零值边界\n模拟 {t:.3f} Myr · 距今 {48-t:.3f} Ma')
    fig.savefig(outdir/'07_U_displacement.png',dpi=170);plt.close(fig)

def render_frame(index,large=True):
    run=RUN;frame=run.timeline['frames'][index];t=frame['elapsed_Myr'];out=run.path/'images'/frame['frame_id'];out.mkdir(parents=True,exist_ok=True)
    receipt=out/'image_metadata.json';snapshot_path=run.path/'frames'/(frame['frame_id']+'.npz')
    if receipt.exists():
        old=load(receipt)
        required=['01_far.png','02_local.png','03_total.png','04_05_window.png','06_faults.png','06_faults_3d.png','06_sections.png','07_U_displacement.png','grid_U.png','grid_displacement.png','uniform_overlay.png']
        if old['time_year']==frame['time_year'] and old['large_images_written']==large and old.get('local_display_revision')==2 and receipt.stat().st_mtime>=max(snapshot_path.stat().st_mtime,(run.path/'scales.json').stat().st_mtime) and all((out/name).exists() for name in required):
            return frame['frame_id']+' cached'
    data=dict(np.load(run.path/'frames'/(frame['frame_id']+'.npz')));planes=dict(far=data['far'],local=data['local'],total=data['far']+data['local'])
    green=coverage(run,t)
    full=run.path/'full_resolution'/frame['frame_id'];full.mkdir(parents=True,exist_ok=True)
    for number,kind in enumerate(['far','local','total'],1):
        mag,angle=run.stress_grid(planes[kind])
        fig=stress_preview(run,frame,kind,mag,angle,green if kind=='far' else None)
        fig.savefig(out/f'0{number}_{kind}.png',dpi=160);plt.close(fig)
        limit=run.scale['stress_local_MPa_max' if kind=='local' else 'stress_MPa_max']
        if large:full_resolution(full/f'0{number}_{kind}.png',mag,angle,limit,green if kind=='far' else None,blank_zero=kind=='local')
        if kind=='local':
            shutil.copyfile(out/'02_local.png',out/'02_local_detail.png')
            Image.fromarray(stress_rgb(mag,limit,blank_zero=True)[::-1]).save(out/'grid_local_detail.png',compress_level=1)
        # Compact exact-grid colour base for interactive zoom; direction is evaluated per cell.
        image=Image.fromarray(stress_rgb(mag,limit,blank_zero=kind=='local')[::-1]);image.save(out/f'grid_{kind}.png',compress_level=1)
        del mag,angle
    mag,angle=run.stress_grid(planes['total'],run.window['origin_km'],500)
    fig,axes=plt.subplots(1,2,figsize=(13,6.1),layout='constrained')
    overview=np.asarray(Image.open(out/'grid_total.png'))
    axes[0].imshow(overview,extent=[0,run.length,0,run.length]);rgba=np.zeros((*green.shape,4),np.float32);rgba[...,1]=.8;rgba[...,3]=green*.20
    axes[0].imshow(rgba,origin='lower',extent=[0,run.length,0,run.length]);axes[0].add_patch(Rectangle(run.window['origin_km'],500,500,fill=False,edgecolor='red',lw=2))
    mark_sources(axes[0],run,t,'total')
    axes[0].set(title='均匀区覆盖与固定500 km红框',xlabel='全域X / km',ylabel='全域Y / km',xlim=(-.055*run.length,1.055*run.length),ylim=(-.055*run.length,1.055*run.length))
    im=axes[1].imshow(mag,origin='lower',extent=[0,500,0,500],cmap=CMAP,norm=norm_for(0,run.scale['stress_MPa_max']),interpolation='nearest')
    xx,yy=np.meshgrid(np.arange(10,500,20),np.arange(10,500,20));aa=angle[yy,xx];vv=mag[yy,xx]>1e-7
    ink=np.where(band(mag[yy,xx][vv],0,run.scale['stress_MPa_max'])<4,'#eeeeee','#222222')
    axes[1].quiver(xx[vv],yy[vv],np.cos(aa[vv]),np.sin(aa[vv]),headlength=0,headwidth=0,headaxislength=0,pivot='middle',scale=30,width=.0017,color=ink)
    axes[1].set(title=f"数据域放大 · 原点 {run.window['origin_km']} km",xlabel='数据域X / km',ylabel='数据域Y / km')
    fig.colorbar(im,ax=axes,shrink=.8,label='水平差应力 / MPa');fig.suptitle(f'取样与放大 · 模拟 {t:.3f} Myr · 距今 {48-t:.3f} Ma')
    fig.savefig(out/'04_05_window.png',dpi=165);plt.close(fig)
    if large:full_resolution(full/'05_window.png',mag,angle,run.scale['stress_MPa_max'])
    Image.fromarray(COLORS[band(mag,0,run.scale['stress_MPa_max'])][::-1]).save(out/'grid_window.png',compress_level=1)
    Image.fromarray((green[::-1]*255).astype(np.uint8)).save(out/'uniform_mask.png',compress_level=1)
    overlay=np.zeros((*green.shape,4),np.uint8);overlay[...,:3]=[25,205,65];overlay[...,3]=green*45
    Image.fromarray(overlay[::-1]).save(out/'uniform_overlay.png',compress_level=1)
    for name,values,key in [('U',data['U_m_per_year']*1000,'U_mm_per_year'),('displacement',data['displacement_m'],'displacement_m')]:
        rgb=COLORS[band(values,run.scale[key+'_min'],run.scale[key+'_max'])]
        Image.fromarray(rgb[::-1]).save(out/f'grid_{name}.png',compress_level=1)
    fault_figures(run,frame,data['slip_rates_m_per_year'],data['U_m_per_year'],data['displacement_m'],out)
    save(out/'image_metadata.json',dict(frame_id=frame['frame_id'],time_year=frame['time_year'],data_grid_spacing_km=1,
        full_resolution_pixels_per_cell=12,global_image_size=[int(run.length)*12]*2,window_origin_km=run.window['origin_km'],
        colors='fem 12 from frozen viewer implementation',large_images_written=large,geometry_revision=2,
        local_display_revision=2,local_color_limits_MPa=[0,run.scale['stress_local_MPa_max']],local_zero_style='white background; grid retained; no direction glyph',
        fault_plot_xy_limits_km=fault_plot_limits(run),vertical_display_exaggeration=(fault_plot_limits(run)[1]-fault_plot_limits(run)[0])*.5/25))
    return frame['frame_id']

def refresh_local_stress(index):
    run=RUN;frame=run.timeline['frames'][index];out=run.path/'images'/frame['frame_id'];full=run.path/'full_resolution'/frame['frame_id']
    data=dict(np.load(run.path/'frames'/(frame['frame_id']+'.npz')))
    mag,angle=run.stress_grid(data['local']);limit=run.scale['stress_local_MPa_max']
    fig=stress_preview(run,frame,'local',mag,angle);fig.savefig(out/'02_local.png',dpi=160);plt.close(fig)
    shutil.copyfile(out/'02_local.png',out/'02_local_detail.png')
    Image.fromarray(stress_rgb(mag,limit,blank_zero=True)[::-1]).save(out/'grid_local.png',compress_level=1)
    shutil.copyfile(out/'grid_local.png',out/'grid_local_detail.png')
    full_resolution(full/'02_local.png',mag,angle,limit,blank_zero=True)
    metadata=load(out/'image_metadata.json');metadata.update(local_display_revision=2,local_color_limits_MPa=[0,limit],local_zero_style='white background; grid retained; no direction glyph')
    save(out/'image_metadata.json',metadata)
    return frame['frame_id']

def refresh_fault_figures(index):
    run=RUN;frame=run.timeline['frames'][index];out=run.path/'images'/frame['frame_id']
    data=dict(np.load(run.path/'frames'/(frame['frame_id']+'.npz')))
    fault_figures(run,frame,data['slip_rates_m_per_year'],data['U_m_per_year'],data['displacement_m'],out)
    metadata=load(out/'image_metadata.json');metadata['geometry_revision']=2
    metadata['fault_plot_xy_limits_km']=fault_plot_limits(run);metadata['vertical_display_exaggeration']=(fault_plot_limits(run)[1]-fault_plot_limits(run)[0])*.5/25
    save(out/'image_metadata.json',metadata)
    return frame['frame_id']

def montage(seed,overview_only=False,kinds=None):
    run=Run(seed);dest=run.path/'nine_panels';dest.mkdir(exist_ok=True)
    overview=dict(page=0,frame_ids=[next(f['frame_id'] for f in run.timeline['frames'] if abs(f['elapsed_Myr']-t)<1e-8) for t in range(0,49,6)])
    pages=[overview] if overview_only else [overview]+run.timeline['nine_panel_pages']
    for page in pages:
        for kind in kinds or ['far','local','total']:
            number={'far':1,'local':2,'total':3}[kind]
            size=1100;canvas=Image.new('RGB',(size*3,size*3+320),'white');draw=ImageDraw.Draw(canvas)
            for j,fid in enumerate(page['frame_ids']):
                image=Image.open(run.path/'images'/fid/f'0{number}_{kind}.png').convert('RGB');image.thumbnail((size,size))
                canvas.paste(image,((j%3)*size,(j//3)*size))
            left=120;right=size*3-100;y=size*3+65;draw.line((left,y,right,y),fill='#313945',width=3)
            frames={x['frame_id']:x for x in run.timeline['frames']}
            for elapsed in range(0,49,6):
                x=left+(right-left)*elapsed/48;draw.line((x,y-10,x,y+10),fill='black',width=2)
                draw.text((x-38,y+15),f'{48-elapsed} Ma',fill='black',font=font(23))
            for fid in page['frame_ids']:
                f=frames[fid];x=left+(right-left)*f['elapsed_Myr']/48;draw.ellipse((x-6,y-6,x+6,y+6),fill='#b22835')
            label='全程总览' if page['page']==0 else f"第{page['page']}页"
            draw.text((left,y+70),f"{NAMES[kind]} · {label} · 红点为本页物理时刻；完整活动轴见时间图",fill='black',font=font(29))
            draw.text((left,y+120),'九宫格用于时间对照；逐格方向请打开原尺寸图或逐格查看器。',fill='#444444',font=font(25))
            suffix='overview' if page['page']==0 else f'{page["page"]:03d}'
            canvas.save(dest/f'{kind}_{suffix}.png',compress_level=1)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--seed',type=int,default=1001);ap.add_argument('--workers',type=int,default=3);ap.add_argument('--start',type=int,default=0);ap.add_argument('--end',type=int);ap.add_argument('--no-large',action='store_true');ap.add_argument('--montage-only',action='store_true');ap.add_argument('--overview-only',action='store_true');ap.add_argument('--geometry-only',action='store_true');ap.add_argument('--local-only',action='store_true');args=ap.parse_args()
    if args.overview_only:montage(args.seed,overview_only=True);return
    if args.montage_only:montage(args.seed);return
    from concurrent.futures import ProcessPoolExecutor,as_completed
    run=Run(args.seed);indices=range(args.start,args.end if args.end is not None else len(run.timeline['frames']))
    with ProcessPoolExecutor(max_workers=args.workers,initializer=init_worker,initargs=(args.seed,)) as pool:
        futures=[pool.submit(refresh_local_stress,i) if args.local_only else pool.submit(refresh_fault_figures,i) if args.geometry_only else pool.submit(render_frame,i,not args.no_large) for i in indices]
        for i,future in enumerate(as_completed(futures)):
            print('Rendered',future.result(),i+1,'/',len(futures),flush=True)
    if args.start==0 and args.end is None and not args.geometry_only:montage(args.seed,kinds=['local'] if args.local_only else None)

if __name__=='__main__':main()
