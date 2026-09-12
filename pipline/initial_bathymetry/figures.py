"""Contour maps and quantitative sections from the saved bathymetry arrays."""
from pathlib import Path
import html
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap,SymLogNorm
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter
from scipy.ndimage import map_coordinates,binary_erosion,distance_transform_edt
import context as c
from profiles import from_parameters
from roughness import local_std

plt.rcParams.update({'font.family':'Microsoft YaHei','axes.unicode_minus':False,
    'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'savefig.facecolor':'white'})
LEVELS=np.array([-4000,-3750,-3500,-3250,-3000,-2750,-2500,-2250,-2000,-1750,-1500,-1250,-1000,
                 -750,-500,-453,-400,-350,-300,-250,-200,-150,-100,-80,-60,-40,-20,0.],float)
LABEL_LEVELS=np.array([-3750,-3000,-2000,-1000,-500,-453,-300,-200,-100,-60,-40],float)
CMAP=LinearSegmentedColormap.from_list('initial_seafloor',['#103866','#3b7ca4','#9dc7da','#e2edf0','#f8f8f4'])
NORM=SymLogNorm(linthresh=100.,linscale=1.,vmin=-4000,vmax=0)
COORD=np.arange(500)+.5
STRUCTURE_STYLE=(('platform_edge','台地边缘','#7f0000',1.35),
                 ('shelf_break','坡折线','#b2182b',1.2),
                 ('slope_foot','坡脚线','#df5b5b',1.2),
                 ('sea_boundary','深浅海分区边界','#f4a1a1',1.1))


def structure_legend(fig):
    handles=[Line2D([0],[0],color=color,lw=width,label=label) for _,label,color,width in STRUCTURE_STYLE]
    fig.legend(handles=handles,loc='outside lower center',ncols=4,frameon=False,fontsize=10)


def structure_lines(ax,mask,types,distance,params):
    """Reference break/foot positions within the original assigned sea types."""
    result=[]
    for kind,label,color,width in STRUCTURE_STYLE:
        sources=[]
        if kind=='platform_edge':sources=[(mask.astype(float),.5,None,'platform_mask')]
        elif kind=='sea_boundary':
            if (types==1).any() and (types==2).any():
                sources=[(np.ma.masked_where(mask,(types==2).astype(float)),.5,None,'deep_type_indicator')]
        else:
            for code,name in ((1,'shallow'),(2,'deep')):
                p=from_parameters(params,name)
                level=p.width_km if kind=='shelf_break' else p.foot_km
                sources.append((np.ma.masked_where(types!=code,distance),level,name,'distance_km'))
        item=dict(kind=kind,label=label,color=color,parts=[])
        for field,level,environment,field_name in sources:
            values=np.ma.asarray(field).compressed()
            if not len(values) or not values.min()<level<values.max():continue
            cs=ax.contour(COORD,COORD,field,levels=[level],colors=[color],linewidths=width,
                          linestyles='solid',corner_mask=False,zorder=5)
            lines=[s.tolist() for s in cs.allsegs[0] if len(s)>=2 and np.isfinite(s).all()]
            item['parts'].append(dict(environment=environment,field=field_name,level=float(level),lines=lines))
        result.append(item)
    return result


def map_panel(ax,z,mask,types,distance,params,title,export=False):
    # Continuous shading provides depth context without offshore contour bands.
    filled=ax.imshow(z,origin='lower',extent=(0,500,0,500),cmap=CMAP,norm=NORM,interpolation='bilinear')
    lines=[]
    if export:
        raw=ax.contour(COORD,COORD,z,levels=LEVELS,colors='none')
        for height,segs in zip(raw.levels,raw.allsegs):
            keep=[s.tolist() for s in segs if len(s)>=2 and np.isfinite(s).all()]
            lines.append(dict(elevation_m=float(height),lines=keep))
        raw.remove()
    inside=np.ma.masked_where(~mask,z)
    contours=ax.contour(COORD,COORD,inside,levels=LEVELS,colors='#28506b',linewidths=.48,
                        alpha=.85,linestyles='solid',corner_mask=False)
    active=[v for v in LABEL_LEVELS if z[mask].min()<v<z[mask].max()]
    if active:ax.clabel(contours,levels=active,fmt=lambda v:f'{v:.0f}',fontsize=7,inline=True,inline_spacing=3)
    boundaries=structure_lines(ax,mask,types,distance,params)
    ax.set(xlim=(0,500),ylim=(0,500),aspect='equal',title=title,xlabel='东西向距离（km）',ylabel='南北向距离（km）')
    ax.set_xticks(np.arange(0,501,100));ax.set_yticks(np.arange(0,501,100))
    ax.grid(alpha=.15,linewidth=.5)
    return filled,lines,boundaries


def save_map(folder,sample,arrays,params,export_raw=False):
    fig,ax=plt.subplots(figsize=(9.4,8.6),layout='constrained')
    fill,lines,boundaries=map_panel(ax,arrays['elevation'],sample['mask'],sample['sea_type'],
        arrays['distance_km'],params,f'种子 {sample["seed"]} · 台地等高线与海底分界',export=export_raw)
    cb=fig.colorbar(fill,ax=ax,fraction=.042,pad=.035,ticks=[-3750,-3000,-2000,-1000,-453,-200,-100,-60,0],format=FuncFormatter(lambda v,p:f'{v:g}'))
    cb.set_label('相对初始海平面的高程（m）')
    structure_legend(fig)
    fig.savefig(folder/'contours.png',dpi=180);plt.close(fig)
    c.write_json(folder/'boundary_lines.json',dict(coordinate_system='local Cartesian kilometres, x right/y up',
        definitions='break/foot: distance equals the fixed profile parameter, clipped to its original assigned sea type; reference positions in blended regions',
        boundaries=boundaries))
    if export_raw:
        c.write_json(folder/'contour_lines.json',dict(coordinate_system='local Cartesian kilometres, x right/y up',
            grid_cell_centres='0.5..499.5 km',source_array='elevation.npy',contours=lines))
    return boundaries


def read_line(arrays,xy):
    positions=[xy[:,1]-.5,xy[:,0]-.5]
    return {name:map_coordinates(arrays[name],positions,order=1,mode='nearest') for name in
            ('elevation','base_elevation','roughness','distance_km','deep_weight')}


def ray_sections(sample,arrays,params):
    mask=sample['mask'];types=sample['sea_type']
    _,nearest=distance_transform_edt(~mask,return_indices=True)
    result=[]
    for kind,code in (('shallow',1),('deep',2)):
        target=from_parameters(params,kind).foot_km+8
        eligible=types==code
        if not eligible.any():continue
        score=abs(arrays['distance_km']-target)
        candidate_ids=np.flatnonzero(eligible)
        ordered=candidate_ids[np.argsort(score.ravel()[candidate_ids],kind='stable')]
        # Deterministic, spatially distributed candidates. Select by category
        # continuity, then by length relative to the fixed profile footprint.
        candidates=ordered[np.linspace(0,min(len(ordered)-1,5000),min(160,len(ordered))).astype(int)]
        best=None
        for flat in candidates:
            y,x=np.unravel_index(flat,mask.shape);py,px=nearest[:,y,x]
            start=np.array([px+.5,py+.5]);end=np.array([x+.5,y+.5])
            direction=end-start;length=float(np.linalg.norm(direction))
            if length<2:continue
            direction/=length
            start=start+direction*.5/np.max(abs(direction));length=float(np.linalg.norm(end-start))
            d=np.linspace(0,length,max(3,int(length*2)+1));xy=start+d[:,None]*direction
            ij=np.clip(np.floor(xy).astype(int),0,499);code_path=types[ij[:,1],ij[:,0]]
            fraction=float(np.mean(code_path[2:]==code))
            rank=(fraction,-abs(length-target),-int(flat))
            if best is None or rank>best[0]:best=(rank,d,xy,int(flat),fraction)
        if best is None:raise ValueError('No valid sea section could be selected')
        _,d,xy,flat,fraction=best
        result.append(dict(kind=kind,selection_rule='nearest-platform straight segment; maximize same-type fraction, then approach fixed-profile foot + 8 km',
             candidate_count=len(candidates),endpoint_flat_index=flat,same_type_fraction=fraction,
             available_km=float(d[-1]),distance_km=d,xy_km=xy,source='accepted mask and sea types',
             end_reason='selected section endpoint, not necessarily the data-domain boundary'))
    if len(result)==2:return result
    # An all-shallow sample also displays a confined-water example.
    path=c.SEA_BATCH/'distance'/f'seed{sample["seed"]}'/'measurement.npz'
    with np.load(path,allow_pickle=False) as z:
        points=z['xy_km'];normals=z['normals'];widths=z['width_km']
    owners=sample['coast'].sea_regions;types=sample['region_types'][owners]
    ids=np.flatnonzero((types==1)&(widths>=3));threshold=np.percentile(widths[ids],10.)
    i=int(ids[np.argmin(abs(widths[ids]-threshold))])
    d=np.linspace(0,max(.5,float(widths[i])-.5),max(3,int(widths[i]*2)))
    xy=points[i]+d[:,None]*normals[i]
    result.append(dict(kind='shallow',station_index=i,selection_rule='浅海射线宽度约第10百分位的位置',
        available_km=float(widths[i]),distance_km=d,xy_km=xy,source=str(path),end_reason='domain edge or intervening platform'))
    return result


def save_sample(folder,sample,arrays,params,stat):
    z=arrays['elevation'];mask=sample['mask'];seed=sample['seed']
    ray=ray_sections(sample,arrays,params)
    xline=np.column_stack([COORD,np.full(500,250.)]);yline=np.column_stack([np.full(500,250.),COORD])
    save_map(folder,sample,arrays,params,export_raw=True)
    records=[]
    fig,axes=plt.subplots(2,2,figsize=(13.5,9.0),layout='constrained')
    for ax,name,xy in zip(axes[0],('A：东西向，y = 250 km','B：南北向，x = 250 km'),(xline,yline)):
        data=read_line(arrays,xy);distance=np.arange(len(xy))+.5
        ax.plot(distance,data['elevation'],color='#125d86',lw=1.1,label='含起伏的初始高程')
        ax.plot(distance,data['base_elevation'],color='#343b43',lw=1.,ls='--',label='基础剖面')
        ax.axhline(0,color='#777777',lw=.6)
        ax.set(title=name,xlabel='域内位置（km）',ylabel='高程（m）',xlim=(0,500))
        ax.grid(alpha=.2);ax.legend(fontsize=8)
        records.append(dict(name=name,xy_km=xy.tolist(),axis_km=distance.tolist(),values={k:v.tolist() for k,v in data.items()}))
    for i,(ax,r) in enumerate(zip(axes[1],ray)):
        p=from_parameters(params,r['kind']);name=('浅海' if r['kind']=='shallow' else '深海')
        data=read_line(arrays,r['xy_km']);d=r['distance_km']
        xmax=max(float(d[-1]),p.foot_km+8);ideal=np.linspace(0,xmax,1500)
        ax.plot(ideal,-p.depth(ideal),color='#bb714c',lw=1.,ls=':',label='同类型固定一维剖面')
        ax.plot(d,data['elevation'],color='#125d86',lw=1.2,label='实际含起伏高程')
        ax.plot(d,data['base_elevation'],color='#343b43',lw=1.,ls='--',label='实际基础剖面')
        if d[-1]<xmax:ax.axvspan(d[-1],xmax,color='#e1e4e8',alpha=.65,label='所选测线之外')
        ax.axvline(p.width_km,color='#8f7855',alpha=.55,lw=.8)
        ax.set(title=f'{chr(67+i)}：{name}方向，剖面长 {r["available_km"]:.1f} km',
               xlabel='从台地边缘沿射线的距离（km）',ylabel='高程（m）',xlim=(0,xmax))
        ax.grid(alpha=.2);ax.legend(fontsize=7.5)
        records.append({k:v for k,v in r.items() if k not in ('xy_km','distance_km')} | dict(name=chr(67+i),
                 xy_km=r['xy_km'].tolist(),axis_km=d.tolist(),values={k:v.tolist() for k,v in data.items()}))
    fig.suptitle(f'种子 {seed} · 剖面检查',fontsize=16)
    fig.savefig(folder/'profiles.png',dpi=165);plt.close(fig)
    c.write_json(folder/'sections.json',dict(seed=seed,sections=records,
         interpretation='1D templates use distance along the chosen straight segment; the actual surface also uses closest-platform distance and shallow/deep blending'))
    save_roughness(folder,sample,arrays,stat)


def save_roughness(folder,sample,arrays,stat):
    noise=arrays['roughness'];q=arrays['noise_deep_weight'];typ=sample['sea_type'];sd=local_std(noise)
    fig,axes=plt.subplots(1,2,figsize=(12.7,5.2),layout='constrained')
    levels=np.array([-120,-80,-40,-20,-10,-5,0,5,10,20,40,80,120.])
    cs=axes[0].contour(COORD,COORD,noise,levels=levels,linewidths=.55,cmap='RdBu_r')
    axes[0].contour(COORD,COORD,sample['mask'].astype(float),levels=[.5],colors='#666666',linewidths=.7,linestyles='dashed')
    axes[0].set(title='叠加起伏的等高线（m）',aspect='equal',xlabel='东西向距离（km）',ylabel='南北向距离（km）')
    fig.colorbar(cs,ax=axes[0],fraction=.04,pad=.03,label='相对基础剖面的高程偏差（m）')
    colors=['#777f85','#3e92b6','#142f63']
    for (code,name,target),color in zip(((0,'台地',2.),(1,'浅海',2.),(2,'深海',8.3)),colors):
        interior=binary_erosion((typ==code)&((q>=.995) if code==2 else (q<=.005)),structure=np.ones((3,3)))
        values=sd[interior]
        if not len(values):continue
        axes[1].hist(values/target,bins=np.linspace(0,3,50),histtype='step',density=True,color=color,lw=1.6,
               label=f'{name}：中位 {np.median(values):.2f} m / 目标 {target:.1f} m')
    axes[1].axvline(1,color='#ad5d30',ls='--',lw=1.)
    axes[1].set(title='内部3 km窗口起伏统计',xlabel='窗口标准差 / 对应目标值',ylabel='概率密度',xlim=(0,3))
    axes[1].legend(fontsize=9);axes[1].grid(alpha=.18)
    fig.suptitle(f'种子 {sample["seed"]} · 起伏检查',fontsize=15)
    fig.savefig(folder/'roughness.png',dpi=160);plt.close(fig)


def save_fixed_profiles(output,params):
    fig,axes=plt.subplots(1,2,figsize=(12.8,4.8),layout='constrained')
    for ax,kind,name,color in zip(axes,('shallow','deep'),('浅海方向','深海方向'),('#267fa5','#14346a')):
        p=from_parameters(params,kind);x=np.linspace(0,p.foot_km+12,2000)
        ax.plot(x,-p.depth(x),color=color,lw=2.)
        ax.axvspan(0,p.width_km,color='#d6e6ee',alpha=.65)
        ax.scatter([0,p.width_km,p.foot_km],[-53,-p.break_depth_m,-p.bottom_depth_m],color=color,s=22,zorder=3)
        ax.annotate(f'坡折：{p.width_km:.2f} km\n水深 {p.break_depth_m:.2f} m',xy=(p.width_km,-p.break_depth_m),
                    xytext=(p.width_km*.45,-p.bottom_depth_m*.55),arrowprops=dict(arrowstyle='-',color='#555555'),fontsize=10)
        ax.set(title=f'{name}：坡折后每公里下降 {p.steep_m_per_km:.2f} m',xlabel='从台地边缘向外的距离（km）',
               ylabel='高程（m）',xlim=(0,p.foot_km+12),ylim=(-p.bottom_depth_m*1.08,0))
        ax.grid(alpha=.2)
        ax.text(.03,.05,f'目标底深 {p.bottom_depth_m:.0f} m\n达到目标位置 {p.foot_km:.2f} km',transform=ax.transAxes,fontsize=10)
    fig.suptitle('全部种子共用的两类固定剖面',fontsize=16)
    fig.savefig(output/'fixed_profiles.png',dpi=180);plt.close(fig)


def save_overview(output,seeds,params):
    n=len(seeds);fig,axes=plt.subplots(int(np.ceil(n/3)),3,figsize=(17,11.7),layout='constrained',squeeze=False)
    fill=None
    for ax,seed in zip(axes.ravel(),seeds):
        z=np.load(output/f'seed{seed}'/'elevation.npy',allow_pickle=False)
        sample=c.load_input(seed)
        distance=np.load(output/f'seed{seed}'/'distance_km.npy',allow_pickle=False)
        fill,_,_=map_panel(ax,z,sample['mask'],sample['sea_type'],distance,params,f'种子 {seed}')
    for ax in axes.ravel()[n:]:ax.set_visible(False)
    cb=fig.colorbar(fill,ax=axes.ravel().tolist(),fraction=.018,pad=.018,ticks=[-3750,-2000,-1000,-453,-200,-100,-60,0],format=FuncFormatter(lambda v,p:f'{v:g}'))
    cb.set_label('高程（m），初始海平面为0 m')
    fig.suptitle('六种子初始海底 · 台地等高线与海底分界',fontsize=17)
    structure_legend(fig)
    fig.savefig(output/'comparison_contours.png',dpi=170);plt.close(fig)


def save_report(output,rows,params):
    lines=['# 初始海底高程：六种子结果','',
      '固定基准高程：台地−53 m、浅海−453 m、深海−3746 m；初始海平面0 m。','',
      '显示：台地内保留等高线；台地外以由深到浅的红色依次标出台地边缘、坡折线、坡脚线、深浅海分区边界。坡折、坡脚按对应类型固定剖面参数与距离场定位，融合区显示参数参考位置。背景色表示实际高程。','',
      '| 方向 | 坡折宽度 km | 坡折水深 m | 坡折后坡度 m/m | 平滑后达到目标底深的距离 km | 有效陆块 | 有效站点 |',
      '|---|---:|---:|---:|---:|---:|---:|']
    for kind,name in (('shallow','浅海'),('deep','深海')):
        p=params['profiles'][kind];d=p['derived']
        lines.append(f'| {name} | {p["width_km"]:.6f} | {p["break_depth_m"]:.6f} | {p["steep_slope_m_per_m"]:.8f} | {d["foot_km"]:.6f} | {p["landmasses"]} | {p["valid_stations"]} |')
    lines+=['','宽度从台地边缘量到开始转入陡坡的位置。坡折后20 km为原资料的坡度测量范围。各陆块内先对同一组有效剖面求均值，再对贡献陆块等权平均；分类距离95 km。',
       '固定宽度、坡折深度和坡度在全部种子中相同。缓坡、陡坡与底面以高程和一阶导数连续的曲线连接，数据域仅截取所覆盖部分。深浅海交界使用当地两类剖面高差和深海坡度控制平滑带宽。',
       '', '| 种子 | 高程范围 m | 台地3 km起伏 m | 浅海3 km起伏 m | 深海内部3 km起伏 m | 深海内部窗口数 |',
       '|---|---|---:|---:|---:|---:|']
    for row in rows:
        r=row['roughness'];ds=r['deep']['pure_interior_windows'];fmt=lambda x:'无对应区域' if x is None else f'{x:.3f}'
        lines.append(f'| {row["seed"]} | {row["elevation_m"]["min"]:.2f} 至 {row["elevation_m"]["max"]:.2f} | {fmt(r["platform"]["pure_interior_windows"]["median"])} | {fmt(r["shallow"]["pure_interior_windows"]["median"])} | {fmt(ds["median"])} | {ds["n"]} |')
    lines+=['','起伏统计为扣除基础剖面后的3×3窗口标准差中位数；内部窗口排除跨类型与起伏强度混合带。过渡带的幅度连续变化，全部同类窗口及内部窗口分别记录在metrics.json。',
      '3 km窗口统计约束局部起伏强度；不同窗口的平均高程仍可变化，整体起伏范围另行保存。所有数组均保留了这种空间相关起伏。',
      f'高斯滤波固定尺度：台地/浅海 {params["roughness"]["shallow"]["gaussian_filter_sigma_km"]:.4f} km，深海 {params["roughness"]["deep"]["gaussian_filter_sigma_km"]:.4f} km；依据3、5、10 km窗口的配对尺度比拟合。25至100 km统计保留作参考，当前简单随机场没有声称拟合全部尺度。',
      '', '| 种子 | 浅海未达到固定剖面底部的位置占比 | 深海未达到固定剖面底部的位置占比 |',
      '|---|---:|---:|']
    for row in rows:
        value=lambda kind:'无对应区域' if row['space'][kind]['fraction_before_target_foot'] is None else f'{row["space"][kind]["fraction_before_target_foot"]:.2%}'
        lines.append(f'| {row["seed"]} | {value("shallow")} | {value("deep")} |')
    lines+=['','上表按各格点至最近台地边缘的距离与固定剖面底部距离比较。窄海域与内部空缺保留实际可计算部分；深浅海融合及随机起伏会进一步改变实际高程。',
      '混合样本的狭窄深海区域中，两侧融合带可能重叠，实际剖面因此偏离单一类型的一维曲线。sections.json保存测线、实际距离、混合权重和所用选线规则，剖面图同时显示实际基础高程与固定一维参考曲线。固定参数控制基础剖面，二维实际坡度还受轮廓几何和交界融合影响。',
      '', '## 来源与适用范围','',
      '原F的W、坡折深度及20 km梯度统计只覆盖250 km内、在遇阻前找到的剖面。未取得值保持缺测。坡度是二维梯度模均值，本轮按已讨论的简化将其用作固定剖面坡度。',
      '真实海岸测得的宽度用于初始水下台地边缘，是本项目的构造用法。固定均值与曲线连接规则、短尺度高斯随机场均在代码说明中列明；自然性与演化效果仍需后续LEM检查。',
      '', '[代码与完整方法](../../../pipline/initial_bathymetry/README.md) · [参数](parameters.json) · [核查](audit.json) · [来源](reference/sources.json)','']
    (output/'REPORT.md').write_text('\n'.join(lines),encoding='utf-8')
    cards=[]
    for row in rows:
        seed=row['seed'];cards.append(f'<section><h2>种子 {seed}</h2><a href="seed{seed}/contours.png"><img alt="种子{seed}海底等高线" src="seed{seed}/contours.png"></a><p><a href="seed{seed}/profiles.png">剖面检查</a> · <a href="seed{seed}/roughness.png">起伏检查</a> · <a href="seed{seed}/metrics.json">全部统计</a></p></section>')
    page='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>初始海底等高线</title><style>body{font-family:system-ui;margin:24px;background:#eef2f5;color:#1c3246}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(450px,1fr));gap:20px}section{background:white;padding:16px;border-radius:12px}img{width:100%;height:auto}a{color:#195d88}</style>'
    page+='<h1>六种子初始海底</h1><p>台地内保留等高线；台地外的红线由深到浅依次表示台地边缘、坡折线、坡脚线、深浅海分区边界。</p><p>台地−53 m · 浅海−453 m · 深海−3746 m。固定剖面参数，数据域内按实际空间截取。</p><p><a href="fixed_profiles.png">共用固定剖面</a> · <a href="comparison_contours.png">六图总览</a> · <a href="REPORT.md">结果说明</a> · <a href="parameters.json">固定参数</a> · <a href="audit.json">核查记录</a></p><main>'+''.join(cards)+'</main></html>'
    (output/'report.html').write_text(page,encoding='utf-8')
