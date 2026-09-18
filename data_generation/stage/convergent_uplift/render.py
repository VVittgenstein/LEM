"""Render complete physical-scale axes as faithful SVG/PNG artifacts."""
import os
from pathlib import Path
from common import ROOT
os.environ['MPLCONFIGDIR']=str(ROOT/'checks/matplotlib_cache')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

plt.rcParams.update({'font.family':'Microsoft YaHei','axes.unicode_minus':False,'font.size':10,
    'svg.fonttype':'none','svg.hashsalt':'LEM_complete_axis_v1','path.simplify':False})

def draw_axis(record,out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True);seed=record['seed'];edges=[np.array(p) for p in record['edges']]
    p=np.vstack(edges);lo=p.min(axis=0);hi=p.max(axis=0);extent=max(hi-lo);center=(lo+hi)/2
    fig,ax=plt.subplots(figsize=(7.4,7.5),dpi=150)
    fig.subplots_adjust(left=.13,right=.97,bottom=.19,top=.85)
    for i,edge in enumerate(edges):
        line,=ax.plot(edge[:,0],edge[:,1],c='#17679d',lw=2.1,solid_capstyle='round');line.set_gid(f'axis_{seed}_edge_{i}')
    g=record['graph'];nodes=np.asarray(g['nodes']);deg=np.array(g['node_degrees'])
    if np.any(deg==1):ax.scatter(nodes[deg==1,0],nodes[deg==1,1],s=20,c='#173b55',zorder=3,label='生成端点')
    if np.any(deg==3):ax.scatter(nodes[deg==3,0],nodes[deg==3,1],s=22,facecolors='white',edgecolors='#9c394c',lw=1.25,zorder=4,label='共享连接点')
    # Full geometry, padded equal-scale view. No 500-km clipping or viewport acceptance filter.
    pad=.09*extent
    ax.set_xlim(center[0]-extent/2-pad,center[0]+extent/2+pad);ax.set_ylim(center[1]-extent/2-pad,center[1]+extent/2+pad)
    ax.set_aspect('equal');ax.set_xlabel('x（km）');ax.set_ylabel('y（km）');ax.grid(alpha=.19)
    ax.legend(loc='best',fontsize=8,framealpha=.92)
    fig.suptitle(f'种子 {seed} · 完整极值线',fontsize=18,y=.96)
    fig.text(.5,.91,f"抽样长边 {record['target_long_km']:,.1f} km   ·   实际长边 {record['actual_long_km']:,.1f} km",ha='center',fontsize=11)
    fig.text(.5,.11,f"总弧长 {record['total_arc_length_km']:,.1f} km   |   几何边 {len(edges)}   |   连通分量 {g['components']}",ha='center',fontsize=10)
    fig.text(.5,.078,f"三度连接点 {g['junctions']}   |   回路 {g['cycles']}   |   几何及代理参照检查通过",ha='center',fontsize=10,color='#435161')
    fig.text(.5,.039,'完整坐标按各图刻度显示；端点不由图框裁切。线宽仅为绘图样式。',ha='center',fontsize=9,color='#66717d')
    png=out/f'axis_seed{seed}.png';svg=out/f'axis_seed{seed}.svg'
    fig.savefig(png,dpi=150);fig.savefig(svg,metadata={'Date':None,'Creator':'LEM complete-axis pipeline'});plt.close(fig)
    return png,svg

def plot_scale(model,out):
    from scale_model import cdf,log_kde_logpdf
    x=np.array(model['training_values_km']);xx=np.geomspace(x.min()*.65,x.max()*1.4,600)
    fig,ax=plt.subplots(1,2,figsize=(12,4.6));fig.subplots_adjust(left=.075,right=.97,bottom=.2,top=.8,wspace=.3)
    ax[0].plot(xx,cdf(xx,model),label='拟合分布',c='#17679d');ax[0].step(np.sort(x),np.arange(1,len(x)+1)/len(x),where='post',label='15源分区经验分布',c='#a86735')
    ax[0].set(xscale='log',xlabel='完整源分区长边（km，对数坐标）',ylabel='累计概率');ax[0].legend(fontsize=9)
    if model['family']=='log_kde':ax[1].plot(xx,np.exp(log_kde_logpdf(xx,np.array(model['log_centers']),model['bandwidth_log'])),c='#17679d')
    ax[1].plot(x,np.zeros(len(x)),'|',c='#a86735',ms=12);ax[1].set(xscale='log',xlabel='完整源分区长边（km，对数坐标）',ylabel='概率密度（每km）')
    from matplotlib.ticker import FixedLocator,FixedFormatter,NullFormatter
    for a in ax:
        a.xaxis.set_major_locator(FixedLocator([200,500,1000,2000,4000]))
        a.xaxis.set_major_formatter(FixedFormatter(['200','500','1000','2000','4000']))
        a.xaxis.set_minor_formatter(NullFormatter())
        a.grid(alpha=.17)
    fig.suptitle('G数据尺度模型：完整源分区等权',fontsize=16)
    fig.text(.075,.055,'17条主总体记录合并为15个源分区；形状尺度映射属于模型近似。分布尾部为统计外推。',fontsize=10)
    fig.savefig(Path(out)/'scale_fit.svg',metadata={'Date':None});plt.close(fig)
