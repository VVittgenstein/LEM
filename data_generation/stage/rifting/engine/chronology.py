from __future__ import annotations
import numpy as np
from .rendering import plt
from .common import OUT,save
from .products import Run
from .forcing import amplitude

def dual_axis(ax,last):
    ax.set_xlim(0,last);ax.axvline(48,color='#aa2533',lw=1)
    if last>48:ax.axvspan(48,last,color='#eeeeee',hatch='///',alpha=.65)
    top=ax.secondary_xaxis('top',functions=(lambda x:48-x,lambda x:48-x))
    top.set_xlabel('距今年代 / Ma；0 Ma为现代');top.set_xticks([48,33.9,23.04,5.333,0])
    ax.set_xlabel('从48 Ma起算的经过时间 / Myr')

def main(seed=1001):
    run=Run(seed);dest=run.path/'chronology';dest.mkdir(exist_ok=True)
    last=max(48,max(e['natural_end_Myr'] for e in run.episodes));time=np.linspace(0,last,1401)
    colors={'far':'#c77835','local':'#257d91'}
    fig,axes=plt.subplots(2,1,figsize=(15,9),layout='constrained',height_ratios=[1,1.15])
    for i,e in enumerate(run.episodes):
        a,b,c,d=e['knots_Myr'];axes[0].barh(i,d-a,left=a,height=.62,color=colors[e['kind']],alpha=.24)
        axes[0].plot([a,b,c,d],[i-.27,i+.27,i+.27,i-.27],color=colors[e['kind']],lw=1)
    axes[0].set_yticks(range(len(run.episodes)),[e['id'] for e in run.episodes]);axes[0].invert_yaxis();axes[0].set_title('作用的完整生命周期：增强、维持与减弱')
    dual_axis(axes[0],last)
    for i,f in enumerate(run.faults):
        axes[1].plot([f['birth_Myr'],last],[i,i],color='#b9bec3',lw=.8)
        for part in f['active_intervals']:axes[1].barh(i,part['natural_end_Myr']-part['start_Myr'],left=part['start_Myr'],height=.65,color='#466f91')
    axes[1].set_yticks(range(len(run.faults)),[f['id'] for f in run.faults],fontsize=8);axes[1].invert_yaxis();axes[1].set_title('断层身份与活动：灰线保留结构，蓝色表示滑动区间')
    dual_axis(axes[1],last)
    fig.savefig(dest/'all_histories.png',dpi=170);plt.close(fig)
    for e in run.episodes:
        a,b,c,d=e['knots_Myr'];end=max(48,d);tt=np.linspace(0,end,1001);values=amplitude(e,tt)*e['reference_force_N']
        fig,axes=plt.subplots(2,1,figsize=(11,6),layout='constrained',height_ratios=[4,1])
        axes[0].plot(tt,values,color=colors[e['kind']]);axes[0].set_ylabel('施力幅值 / N');axes[0].set_title(e['id']+' · 完整时间过程')
        dual_axis(axes[0],end)
        for name,x,y in [('增强',a,b),('维持',b,c),('减弱',c,d)]:
            if y>x:axes[1].barh(0,y-x,left=x,color=colors[e['kind']],alpha=.3);axes[1].text((x+y)/2,0,name,ha='center',va='center',fontsize=9)
        points=[f['elapsed_Myr'] for f in run.timeline['frames'] if a<=f['elapsed_Myr']<=min(d,48)]
        axes[1].scatter(points,np.zeros(len(points)),s=8,color='#b42836');axes[1].set_yticks([]);axes[1].set_xlim(0,end);axes[1].set_xlabel('红点为实际出图时刻 / Myr')
        fig.savefig(dest/(e['id']+'.png'),dpi=165);plt.close(fig)
    for i,f in enumerate(run.faults):
        tt=run.history['times_Myr'];rates=run.history['slip_rates_m_per_year'][i]*1000;cum=run.history['cumulative_slip_m'][i]
        fig,axes=plt.subplots(2,1,figsize=(11,6.5),layout='constrained')
        for j,color in enumerate(['#5c83a5','#a76c32','#669579']):
            axes[0].plot(tt,rates[:,j],color=color,label=f'沿走向分段{j+1}')
            axes[1].plot(tt,cum[:,j],color=color)
        axes[0].set_ylabel('滑动速率 / mm/yr');axes[0].legend(loc='upper right',fontsize=8);axes[0].set_title(f['id']+' · 活动与累计滑动')
        axes[1].set_ylabel('累计滑动 / m')
        for ax in axes:dual_axis(ax,max(48,f['last_slip_Myr']))
        fig.savefig(dest/(f['id']+'.png'),dpi=165);plt.close(fig)
    print('Saved lifecycle figures for all forces and faults.',flush=True)

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--seed',type=int,default=1001);args=parser.parse_args();main(args.seed)
