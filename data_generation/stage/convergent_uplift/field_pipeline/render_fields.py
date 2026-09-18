"""A/B images share the exact canvas, axes rectangle, extent, and line paths."""
import importlib.util, math, argparse
import numpy as np
from PIL import Image, ImageDraw
from context import *

def palette_module():
    spec=importlib.util.spec_from_file_location('frozen_viewer_palette',RAW/'viewer_colormaps.py')
    mod=importlib.util.module_from_spec(spec)
    import sys
    sys.modules[spec.name]=mod;spec.loader.exec_module(mod)
    return mod

def nice_bar(span):
    p=10**np.floor(np.log10(span/5));return float(max(v*p for v in [1,2,5,10] if v*p<=span/4))

def draw_one(directory,vmax):
    plt=plotting()
    from matplotlib.colors import ListedColormap, BoundaryNorm
    from matplotlib import patheffects as pe
    from matplotlib.ticker import MaxNLocator
    path=Path(directory);meta=jload(path/'metadata.json');axis=jload(path/'axis.json');data=np.load(path/'field.npz')
    x=data['x_km'];y=data['y_km'];u=data['u_m_per_yr']*1000;support=data['support'];seed=meta['seed']
    xmin,xmax,ymin,ymax=meta['array_bounds_km'];span=max(xmax-xmin,ymax-ymin);cx=(xmin+xmax)/2;cy=(ymin+ymax)/2
    extent=[cx-span/2,cx+span/2,cy-span/2,cy+span/2]
    palette=palette_module();colors=palette.banded_colors('fem',12)/255.;cmap=ListedColormap(colors)
    levels=np.linspace(0,vmax,13);norm=BoundaryNorm(levels,cmap.N,clip=True);bar=nice_bar(span);records=[]
    for kind in ('A','B'):
        fig=plt.figure(figsize=(8,8),dpi=170)
        ax=fig.add_axes([.11,.17,.72,.72]);ax.set_xlim(extent[:2]);ax.set_ylim(extent[2:]);ax.set_aspect('equal',adjustable='box')
        ax.set_xlabel('x（km）');ax.set_ylabel('y（km）');ax.xaxis.set_major_locator(MaxNLocator(5));ax.yaxis.set_major_locator(MaxNLocator(5))
        if kind=='B':
            im=ax.imshow(u,extent=[xmin,xmax,ymin,ymax],origin='lower',cmap=cmap,norm=norm,interpolation='nearest',zorder=0)
            # Match the outside of a rectangular array to its zero-valued background.
            ax.set_facecolor(colors[0]);ax.contour(x,y,support.astype(float),levels=[.5],colors=['#e6f3ff'],linewidths=.65,linestyles='dashed',zorder=2)
            cax=fig.add_axes([.865,.28,.026,.49]);cb=fig.colorbar(im,cax=cax,boundaries=levels,ticks=levels[::2]);cb.set_label('抬升速率（mm/yr）',fontsize=9)
        else:ax.set_facecolor('#fbfcfd')
        for i,p in enumerate(axis['edges']):
            p=np.asarray(p);line,=ax.plot(p[:,0],p[:,1],color='#202a34',lw=1.05,zorder=4,solid_capstyle='round',
                path_effects=[pe.Stroke(linewidth=2.35,foreground='white'),pe.Normal()])
            line.set_gid(f'aux_seed{seed}_edge{i}')
        ax.grid(color='#7e8d9d',alpha=.22,lw=.55)
        fig.text(.11,.958,f'{kind}  '+('辅助极值线' if kind=='A' else '完整二维抬升场'),fontsize=19)
        fig.text(.11,.922,f"种子 {seed}  ·  辅助线长边 {meta['axis_extent_km']:,.0f} km  ·  同一完整场范围",fontsize=10,color='#465666')
        # Explicit scale bar in figure coordinates, identical for both images.
        x0=.11;y0=.073;w=.72*bar/span
        fig.lines.append(plt.Line2D([x0,x0+w],[y0,y0],transform=fig.transFigure,color='#263747',lw=2.4))
        for end in (x0,x0+w):fig.lines.append(plt.Line2D([end,end],[y0-.006,y0+.006],transform=fig.transFigure,color='#263747',lw=1.2))
        fig.text(x0+w/2,y0+.011,f'{bar:g} km',ha='center',fontsize=10)
        fig.text(.83,.081,f"峰值 {meta['peak_mm_yr']:.2f} mm/yr  |  格距 1 km",ha='right',fontsize=9,color='#465666')
        note='两图共用坐标范围、绘图区尺寸、比例尺和辅助线。'
        if kind=='B':note='FEM统一色标；虚线表示生成作用边界，边界外U为0。'
        fig.text(.11,.025,note,fontsize=9,color='#526373')
        fig.canvas.draw();bbox=ax.get_window_extent();matrix=ax.transData.get_affine().get_matrix()
        records.append({'kind':kind,'canvas_px':list(fig.canvas.get_width_height()),'axes_bbox_px':list(map(float,bbox.bounds)),
            'xlim':list(ax.get_xlim()),'ylim':list(ax.get_ylim()),'data_to_display':matrix.tolist(),'scale_bar_km':bar,
            'scale_bar_px':float(w*fig.get_figwidth()*fig.dpi),'edge_lengths':[len(p) for p in axis['edges']],
            'axis_source_sha256':sha(path/'axis.json')})
        fig.savefig(path/f'{kind}.png',dpi=170)
        fig.savefig(path/f'{kind}.svg',metadata={'Date':None,'Creator':'LEM DS5 field pipeline'})
        plt.close(fig)
    pair=Image.new('RGB',(2720,1360),'white')
    for i,k in enumerate(('A','B')):
        with Image.open(path/f'{k}.png') as im:pair.paste(im.convert('RGB'),(i*1360,0))
    pair.save(path/'pair.png')
    assert records[0]['axes_bbox_px']==records[1]['axes_bbox_px']
    assert records[0]['data_to_display']==records[1]['data_to_display']
    assert records[0]['scale_bar_px']==records[1]['scale_bar_px']
    jsave(path/'pair_geometry.json',{'A':records[0],'B':records[1],'identical_geometry':True,
      'view_extent_km':extent,'palette':'terrain_viewer / lem_viewer FEM, 12 exact bands',
      'palette_source_sha256':sha(RAW/'viewer_colormaps.py'),'vmin_mm_yr':0.,'vmax_mm_yr':vmax,
      'color_edges_mm_yr':levels.tolist(),'colors_rgba_uint8':palette.banded_colors('fem',12).tolist(),
      'SVG_field_encoding':'embedded raster with vector axes and exact auxiliary line coordinates'})
    print('rendered',seed,flush=True)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',default='output');args=ap.parse_args();out=(ROOT/args.output).resolve()
    if not out.is_relative_to(ROOT):raise ValueError('Output outside module')
    batch=jload(out/'batch.json');vmax=float(np.ceil(max(r['peak_mm_yr'] for r in batch['samples'])))
    for r in batch['samples']:draw_one(out/f"seed{r['seed']}",vmax)
    # Contact sheets are review-only scaled copies; per-pair originals keep exact geometry.
    for k in range(0,len(batch['samples']),2):
        subset=batch['samples'][k:k+2];sheet=Image.new('RGB',(1600,800*len(subset)),'white')
        for j,r in enumerate(subset):
            with Image.open(out/f"seed{r['seed']}/pair.png") as im:sheet.paste(im.resize((1600,800),Image.Resampling.LANCZOS),(0,j*800))
        sheet.save(out/f'contact_{k//2+1:02d}.png')

if __name__=='__main__':main()
