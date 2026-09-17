"""Equal-geometry E frames plus two physically aligned time axes."""
import importlib.util, math, shutil, sys
from tcontext import *
from spatial_binding import binding,field_directory,window_directory,render_spatial

NUMBERS=list('①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳')
STAGE_COLORS={'上升':'#dd9b48','维持':'#60a58d','下降':'#8e91bf'}
GEO_COLORS=['#f8d292','#f4dfa2','#f6ebba','#e0e9c2','#cde1db','#b9d6ee']

def palette():
    spec=importlib.util.spec_from_file_location('time_fem',SOURCES/'viewer_colormaps.py');m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
    return m.banded_colors('fem',12)/255

def stage_label(frame):
    labels=frame['labels']
    return ' / '.join(f"{r['stage']}{r['elapsed_fraction']*100:.0f}%" if not frame['modern'] else f"{r['stage']}{r['elapsed_fraction']*100:.1f}%" for r in labels)

def draw_axes(ax,event,frames):
    from matplotlib.patches import Rectangle
    end=event['natural_end_sim_Myr'];start=event['start_sim_Myr'];maximum=max(48.,end)
    margin=max(1.,maximum*.025);ax.set_xlim(-margin,maximum+margin);ax.set_ylim(-.6,2.25);ax.axis('off')
    if end>48:
        ax.axvspan(48,end,facecolor='#e7e9ec',alpha=.65,zorder=0)
        ax.text(48+(end-48)/2,2.12,'模拟时段外的剩余生命周期',ha='center',va='center',fontsize=9,color='#59616b')
    for i,(_,cn,old,young) in enumerate(EPOCHS):
        a=48-old;b=48-young
        ax.add_patch(Rectangle((a,.10),b-a,.30,facecolor=GEO_COLORS[i],edgecolor='white',lw=.5))
        if b-a>=3.:
            ax.text((a+b)/2,.25,cn,ha='center',va='center',fontsize=9)
    # The short epochs retain exact physical widths, with externally placed labels.
    for i in (3,4,5):
        _,cn,old,young=EPOCHS[i];mid=48-(old+young)/2
        label_x=maximum*(.68+.115*(i-3))
        ax.annotate(cn,xy=(mid,.10),xytext=(label_x,-.43),ha='center',fontsize=9,
                    arrowprops={'arrowstyle':'-','color':'#78818b','lw':.65})
    for age in (48,40,30,20,10,0):
        t=48-age;ax.plot([t,t],[.04,.10],color='#52616b',lw=.8)
        ax.text(t,-.035,'现代' if age==0 else f'{age:g} Ma',ha='center',va='top',fontsize=8.5)
    ax.text(0,.54,'地质时间轴 · 距今年代',fontsize=9,color='#374757')
    positions=[start,event['rise_end_sim_Myr'],event['hold_end_sim_Myr'],end]
    segments=[]
    for name,a,b in zip(('上升','维持','下降'),positions[:-1],positions[1:]):
        if b<=a:continue
        ax.add_patch(Rectangle((a,1.10),b-a,.28,facecolor=STAGE_COLORS[name],edgecolor='white',lw=.6))
        if b-a>maximum*.035:ax.text((a+b)/2,1.24,name,ha='center',va='center',fontsize=9)
        segments.append(dict(stage=name,start=a,end=b))
    if end>48:
        ax.add_patch(Rectangle((48,1.10),end-48,.28,fill=False,hatch='////',edgecolor='#91979e',lw=.5))
    ax.text(min(start,maximum*.48),1.90,f"完整活动时间轴 · 自然总寿命 {event['duration_Myr']:.2f} Myr",fontsize=10)
    ax.text(start,.94,'已历 0',ha='left',va='top',fontsize=8)
    ax.text(end,.94,f"已历 {event['duration_Myr']:.2f} Myr",ha='right',va='top',fontsize=8)
    # Dots use exact time coordinates. Labels may be displaced with leader lines.
    marker_times=np.array([f['sim_Myr'] for f in frames]);label_positions=marker_times.copy();gap=maximum*.020
    for i in range(1,len(label_positions)):label_positions[i]=max(label_positions[i],label_positions[i-1]+gap)
    if len(label_positions) and label_positions[-1]>maximum:
        label_positions-=label_positions[-1]-maximum
    for i,(frame,label_x) in enumerate(zip(frames,label_positions)):
        t=frame['sim_Myr'];color='#bd3545' if frame['modern'] else '#243949'
        ax.plot(t,1.43,'o',ms=3.5,c=color,zorder=5)
        ax.annotate(NUMBERS[i],xy=(t,1.43),xytext=(label_x,1.66),ha='center',va='center',fontsize=10,color=color,
                    arrowprops={'arrowstyle':'-','lw':.55,'color':color})
    ax.axvline(48,ymin=.12,ymax=.91,c='#b63445',lw=1,ls='--',zorder=4)
    ax.text(48,.75,'现代截断位置',ha='right',fontsize=8.5,color='#b63445')
    return dict(xlim=list(ax.get_xlim()),event_segments=segments,geological_interval=[0.,48.],activity_interval=[start,end],
                point_times=marker_times.tolist(),point_label_positions=label_positions.tolist(),modern_sim_Myr=48.)

def render_event(seed,index,edges):
    plt=plotting();from matplotlib.colors import ListedColormap,BoundaryNorm
    from matplotlib.ticker import MaxNLocator
    from matplotlib import patheffects as pe
    directory=OUT/f'seed{seed}/event{index:02d}';event=load(directory/'event.json');frames=load(directory/'frames.json')
    fp=field_directory(seed,index);wp=window_directory(seed,index)
    data=dict(np.load(directory/'native_frames.npz'));full=dict(np.load(fp/'field.npz'))
    meta=load(fp/'metadata.json');axis=load(fp/'axis.json')
    geometry=load(wp/'display_geometry.json');selection=load(wp/'selection.json')
    limits=geometry['common_extent_km'];cmap=ListedColormap(palette());norm=BoundaryNorm(edges,12,clip=True)
    rows=int(math.ceil(len(frames)/3));width=14.0;panel=3.62;left=.88;bottom=3.95;gap_x=.66;gap_y=.77
    height=bottom+rows*panel+(rows-1)*gap_y+1.55
    fig=plt.figure(figsize=(width,height),dpi=160);records=[];stat=load(directory/'summary.json')['frame_statistics']
    for i,frame in enumerate(frames):
        row,col=divmod(i,3);x0=left+col*(panel+gap_x);y0=bottom+(rows-1-row)*(panel+gap_y)
        ax=fig.add_axes([x0/width,y0/height,panel/width,panel/height]);ax.set_facecolor(palette()[0])
        ax.set_xlim(limits[:2]);ax.set_ylim(limits[2:]);ax.set_aspect('equal',adjustable='box')
        im=ax.imshow(data['u_m_per_yr'][i]*1000,origin='lower',extent=meta['array_bounds_km'],cmap=cmap,norm=norm,interpolation='nearest')
        ax.contour(full['x_km'],full['y_km'],full['support'].astype(float),levels=[.5],colors=['#b4bed5'],linewidths=.35,linestyles='dashed',alpha=.55)
        for j,xy in enumerate(axis['edges']):
            xy=np.asarray(xy);line,=ax.plot(xy[:,0],xy[:,1],c='#192f3e',lw=.55,
                  path_effects=[pe.Stroke(linewidth=1.30,foreground='white'),pe.Normal()]);line.set_gid(f'aux_{seed}_{j}_frame{i}')
        corners=np.array(selection['corners_source_km']);ax.plot(corners[:,0],corners[:,1],c='#f14343',lw=.8,alpha=.8)
        ax.xaxis.set_major_locator(MaxNLocator(4));ax.yaxis.set_major_locator(MaxNLocator(4));ax.tick_params(labelsize=8)
        ax.set_xlabel('x（km）',fontsize=8,labelpad=1);ax.set_ylabel('y（km）',fontsize=8,labelpad=1)
        age='现代 · 0 Ma' if frame['modern'] else f"距今 {frame['age_Ma']:.3f} Ma"
        ax.set_title(f"{NUMBERS[i]} {stage_label(frame)}\n{age}",fontsize=10.5,pad=7,color='#a52b3c' if frame['modern'] else '#213344')
        span=limits[1]-limits[0];scale=geometry['panels'][1]['scale_bar_km'];bx=limits[0]+.06*span;by=limits[2]+.07*span
        line,=ax.plot([bx,bx+scale],[by,by],c='white',lw=1.8);line.set_gid(f'scale_{scale:g}km')
        ax.text(bx+scale/2,by+.022*span,f'{scale:g} km',color='white',ha='center',fontsize=8)
        ax.text(.98,.015,f"峰值 {stat[i]['peak_mm_yr']:.2f}",transform=ax.transAxes,color='white',ha='right',fontsize=7.5)
        records.append((ax,frame,scale))
    cax=fig.add_axes([13.13/width,(bottom+.55)/height,.16/width,max(1.8,rows*panel*.43)/height])
    cb=fig.colorbar(im,cax=cax,boundaries=edges,ticks=np.linspace(0,edges[-1],6));cb.set_label('抬升速率（mm/yr）',fontsize=9);cb.ax.tick_params(labelsize=8)
    fig.text(left/width,1-.38/height,f'E  汇聚抬升事件的时空演化 · 样本 {seed} · 事件 {index+1}',fontsize=17,color='#182d3e')
    subtitle=f"上升 {event['rise_Myr']:.2f} / 维持 {event['hold_Myr']:.2f} / 下降 {event['fall_Myr']:.2f} Myr   |   自然总寿命 {event['duration_Myr']:.2f} Myr"
    fig.text(left/width,1-.78/height,subtitle,fontsize=10,color='#506273')
    fig.text(left/width,1-1.10/height,'阶段百分比为已历时间；各位置允许连续波动。细线为本事件辅助线，红框为本事件独立选定的500×500 km窗口。',fontsize=9,color='#506273')
    tax=fig.add_axes([left/width,.73/height,11.92/width,2.55/height]);axis_record=draw_axes(tax,event,frames)
    fig.text(left/width,.31/height,'时间轴：橙色上升、绿色维持、紫色下降；两轴共用时间比例。画面截止现代。灰虚线为完整参考场边界。',fontsize=9,color='#506273')
    fig.canvas.draw();panels=[]
    for ax,f,scale in records:
        panels.append(dict(number=f['number'],sim_Myr=f['sim_Myr'],bbox_px=list(map(float,ax.get_window_extent().bounds)),
              xlim=list(ax.get_xlim()),ylim=list(ax.get_ylim()),scale_bar_km=scale,
              transform=ax.transData.get_affine().get_matrix().tolist()))
    axis_record['time_to_pixel']=tax.transData.get_affine().get_matrix().tolist()
    save(directory/'E_geometry.json',dict(panels=panels,timeline=axis_record,color_edges_mm_yr=edges.tolist(),
          colors_rgba_uint8=np.round(palette()*255).astype(int).tolist(),canvas_px=list(fig.canvas.get_width_height()),
          common_extent_km=limits,palette='FEM',native_resolution_km=1.))
    fig.savefig(directory/'E.png',dpi=160);fig.savefig(directory/'E.svg',metadata={'Date':None,'Creator':'LEM convergent temporal pipeline'})
    plt.close(fig)
    from PIL import Image
    with Image.open(directory/'E.png') as image:
        image.thumbnail((1200,2000));image.save(directory/'preview.png')
    if index==0:
        shutil.copyfile(directory/'E.png',directory.parent/'E.png');shutil.copyfile(directory/'E.svg',directory.parent/'E.svg')
    print('E rendered',seed,index,len(frames),'frames',flush=True)

def model_figure():
    from fit_models import distribution
    from timing import increment
    plt=plotting();duration=load(MODELS/'duration.json');trigger=load(MODELS/'trigger.json');spec=duration['selected']
    d=distribution(spec['family'],spec['parameters']);fig,axes=plt.subplots(1,2,figsize=(12,4.3),dpi=160)
    xx=np.linspace(0,d.ppf(.995),500);axes[0].plot(xx,d.pdf(xx),c='#275c80',lw=2)
    for p in (.1,.5,.9):
        q=d.ppf(p);axes[0].axvline(q,color='#c88939',lw=.8,ls='--');axes[0].text(q,d.pdf(q),f' P{int(p*100)}={q:.1f}',rotation=90,va='bottom',fontsize=8)
    axes[0].set(title='案例约束的自然持续时间分布',xlabel='持续时间（Myr）',ylabel='概率密度（1/Myr）');axes[0].set_ylim(0,d.pdf(xx).max()*1.6)
    wait=np.linspace(0,24,300)
    for i,e in enumerate(trigger['epochs']):axes[1].plot(wait,[-np.expm1(-increment(0,t,i,trigger)) for t in wait],label=e['name'])
    axes[1].set(title='固定各世系数时的等待函数对照',xlabel='累计允许等待时间（Myr）',ylabel='累计触发概率',ylim=(0,1));axes[1].legend(fontsize=8,ncol=2)
    fig.text(.07,.02,'时长使用4个案例组的阶段代理与持续下限；触发绝对基准、维持及波动参数包含明确设计取值。',fontsize=9,color='#546271')
    fig.tight_layout(rect=(0,.06,1,1));fig.savefig(OUT/'model_overview.png');fig.savefig(OUT/'model_overview.svg',metadata={'Date':None});plt.close(fig)

def main():
    batch=load(OUT/'batch.json');maximum=max((max(e['frame_peak_mm_yr'],binding(e['seed'],e['event_index'])['reference_peak_mm_yr']) for e in batch['events']),default=0.);top=max(15.,math.ceil(maximum/5)*5)
    edges=np.linspace(0,top,13);save(OUT/'color_scale.json',dict(edges_mm_yr=edges.tolist(),all_displayed_frames_peak_mm_yr=maximum,
               reason='Common FEM palette and numeric scale across every E frame; scale extended to include all displayed temporal peaks without clipping.'))
    for event in batch['events']:
        render_spatial(event['seed'],event['event_index'],edges)
        render_event(event['seed'],event['event_index'],edges)
    model_figure()

if __name__=='__main__':main()
