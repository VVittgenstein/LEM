"""Five standalone vector SVGs; all quantitative marks come from saved arrays."""
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
import numpy as np
from scipy.ndimage import map_coordinates
import matplotlib
matplotlib.use("Agg")
from matplotlib import pyplot as plt, colors, font_manager
import context as c
import spatial

SVG = "http://www.w3.org/2000/svg"
FONT = font_manager.FontProperties(fname="C:/Windows/Fonts/msyh.ttc")
plt.rcParams.update({"font.family": FONT.get_name(), "svg.fonttype": "path",
                     "axes.unicode_minus": False, "svg.hashsalt": "LEM-background-uplif-v1"})


def svg_paths(out):
    return [out/f"uplift_interval{i:02d}.svg" for i in range(1,6)]


def render(out):
    fits = c.read_json(out/"fitted_models.json")
    reference = np.load(out/"reference_window.npz")
    saved = {(seed,i):np.load(out/f"seed{seed}/interval{i:02d}_rate_m_per_yr.npy")*1e6
             for seed in c.SEEDS for i in range(1,6)}
    lo = float(np.floor(min(f.min() for f in saved.values())))
    hi = float(np.ceil(max(f.max() for f in saved.values())))
    lo,hi = min(lo,-1.),max(hi,1.)
    levels = int(round((hi-lo)*2))  # common 0.5 m/Myr bands, palette interpolation matches the viewer
    scale = c.BandedScale(lo,hi,levels,"fem")
    edges = scale.edges
    cmap = colors.ListedColormap(scale.colors[:,:3]/255.)
    norm = colors.BoundaryNorm(edges,levels)
    lookup = {colors.to_hex(rgb[:3]/255.):i for i,rgb in enumerate(scale.colors)}
    c.write_json(out/"color_scale.json",{"vmin":lo,"vmax":hi,"levels":levels,"edges":edges,
                 "rgba":scale.colors,"units":"m/Myr","palette":"lem_viewer.colormaps.PALETTES['fem']",
                 "source_hash":c.file_sha256(c.ROOT/"viewer/lem_viewer/colormaps.py")})
    draw_records = []
    for model in fits["models"]:
        i = model["interval"]
        fig,axs = plt.subplots(2,3,figsize=(18,12),dpi=72)
        fig.subplots_adjust(left=.055,right=.88,bottom=.10,top=.84,wspace=.20,hspace=.25)
        fig.suptitle(f"背景垂向速率 · 模拟第 {int(model['start_elapsed_Myr']*100)} 至 "
                     f"{int(model['end_elapsed_Myr']*100)} 万年",fontsize=23,y=.965)
        fig.text(.055,.913,f"M2对应时段参考：平均 {model['rate_mean_m_per_Myr']:+.3f}，"
                 f"标准差 {model['rate_std_m_per_Myr']:.3f} m/百万年 · 六个新随机分布",fontsize=13)
        fig.text(.055,.878,"正值抬升，负值沉降；以下为台地区块圈层衰减后的最终速率场。",fontsize=12)
        panels = []
        for ax,seed in zip(axs.flat,c.SEEDS):
            field = saved[(seed,i)]
            sample = c.load_mask(seed)
            coords = np.arange(-.5,501.,1.)
            filled = ax.contourf(coords,coords,np.pad(field,1,mode="edge"),levels=edges,
                                 cmap=cmap,norm=norm,antialiased=False)
            filled.set_gid(f"field_seed{seed}")
            for component in sample["contours"]["components"]:
                for ring in [component["outer"],*component["holes"]]:
                    xy=np.asarray(ring)
                    ax.plot(xy[:,0],xy[:,1],color="white",linewidth=1.3)
                    ax.plot(xy[:,0],xy[:,1],color="#303030",linewidth=.45)
            ax.set(xlim=(0,500),ylim=(0,500),aspect="equal",
                   xticks=(0,100,200,300,400,500),yticks=(0,100,200,300,400,500),
                   xlabel="东西向距离 (km)",ylabel="南北向距离 (km)")
            ax.set_title(f"种子 {seed} · 全域平均 {field.mean():+.3f}",fontsize=12,pad=9)
            ax.tick_params(labelsize=9)
            for spine in ax.spines.values():spine.set_color("#777777")
            panels.append((seed,ax))
        cbax=fig.add_axes([.913,.205,.019,.555])
        sm=plt.cm.ScalarMappable(norm=norm,cmap=cmap)
        ticks=sorted(set([lo,hi,0.,*np.arange(np.ceil(lo/2)*2,hi,2.)]))
        cb=fig.colorbar(sm,cax=cbax,ticks=ticks,spacing="proportional")
        cb.set_label("垂向速率 (m/百万年)",fontsize=12,labelpad=12)
        cb.ax.tick_params(labelsize=10)
        fig.text(.055,.04,"台地内部100% · 台地外圈75% · 海域第1圈50% · 第2圈25% · 第3圈及外侧0%；交界连续过渡。",
                 fontsize=11)
        fig.text(.055,.014,"线条为初始台地轮廓；数据域500 km×500 km，格距1 km。M2 PlateFrame，73°E / 41°N附近选定窗口。",
                 fontsize=10,color="#555555")
        fig.canvas.draw()
        record={"interval":i,"file":f"uplift_interval{i:02d}.svg","units":"m/Myr",
                "vmin":lo,"vmax":hi,"palette":"fem","edges":edges.tolist(),"color_to_band":lookup,
                "panels":[]}
        for seed,ax in panels:
            record["panels"].append({"seed":seed,"group":f"field_seed{seed}",
               "sx":float(ax.bbox.width/500),"tx":float(ax.bbox.x0),
               "sy":float(-ax.bbox.height/500),"ty":float(fig.bbox.height-ax.bbox.y0),
               "array_sha256":c.file_sha256(out/f"seed{seed}/interval{i:02d}_rate_m_per_yr.npy")})
        fig.savefig(out/record["file"],metadata={"Date":None,"Creator":"LEM"})
        fig.savefig(out/f"uplift_interval{i:02d}.png",dpi=130)
        plt.close(fig)
        draw_records.append(record)
    c.write_json(out/"svg_geometry.json",draw_records)
    diagnostics(out,fits,reference)


def diagnostics(out,fits,reference):
    fig,axs=plt.subplots(2,3,figsize=(17,10),layout="constrained")
    for ax,model in zip(axs.flat,fits["models"]):
        i=model["interval"]
        target=np.array(model["target_variogram"])
        for axis,offset,style in (("东西",0,"-"),("南北",4,"--")):
            distance=model["native_lags_x_km" if offset==0 else "native_lags_y_km"]
            ax.plot(distance,target[offset:offset+4],style,color="black",marker="o",label=f"M2 {axis}")
            for k,seed in enumerate(c.SEEDS):
                cfg=c.read_json(out/f"seed{seed}/config.json")
                measured=cfg["intervals"][i-1]["variogram"][offset:offset+4]
                ax.plot(distance,measured,style,color="#1766a2",alpha=.45,label=f"生成场 {axis}" if k==0 else None)
        ax.set(title=f"时段{i}：衰减前的空间变化",xlabel="两位置距离 (km)",ylabel="归一化半方差")
        ax.legend(fontsize=8);ax.grid(alpha=.2)
    axs.flat[-1].axis("off")
    axs.flat[-1].text(.02,.9,"黑线：选定M2窗口的对应时段\n蓝线：六个种子\n\n同一距离、同一方向分别比较。\n每段单独拟合空间相关尺度。\n\n相关尺度大于窗口时，\n窗口之外的衰减未得到观测约束。",
                      fontsize=14,va="top",transform=axs.flat[-1].transAxes)
    fig.savefig(out/"spatial_diagnostics.png",dpi=140);plt.close(fig)
    fig,axs=plt.subplots(2,3,figsize=(16,10),layout="constrained")
    for ax,seed in zip(axs.flat,c.SEEDS):
        w=np.load(out/f"seed{seed}/taper_weight.npy")
        im=ax.imshow(w,origin="lower",extent=(0,500,0,500),vmin=0,vmax=1,cmap="Greys_r")
        ax.set(title=f"种子{seed}：圈层衰减权重",xlabel="东西向距离 (km)",ylabel="南北向距离 (km)")
    fig.colorbar(im,ax=axs.ravel().tolist(),label="权重",ticks=(0,.25,.5,.75,1),shrink=.8)
    fig.savefig(out/"taper_weights.png",dpi=130);plt.close(fig)


def check_svgs(out):
    """Read actual coloured polygon coordinates back from SVG, invert axes, sample arrays."""
    records=c.read_json(out/"svg_geometry.json")
    rows=[]
    for rec in records:
        root=ET.parse(out/rec["file"]).getroot()
        byid={e.attrib.get("id"):e for e in root.iter()}
        max_error=0.;vertices=0;paths=0
        for panel in rec["panels"]:
            arrpath=out/f"seed{panel['seed']}/interval{rec['interval']:02d}_rate_m_per_yr.npy"
            if c.file_sha256(arrpath)!=panel["array_sha256"]:raise ValueError("Plot input changed")
            field=np.load(arrpath)*1e6
            group=byid[panel["group"]]
            for node in group.iter(f"{{{SVG}}}path"):
                if not node.attrib.get("d"):
                    continue
                style=node.attrib.get("style","")
                match=re.search(r"fill:\s*(#[0-9a-fA-F]{6})",style)
                if not match:continue
                colour=match.group(1).lower()
                if colour not in rec["color_to_band"]:raise ValueError("SVG field colour outside viewer palette")
                band=rec["color_to_band"][colour]
                d=node.attrib["d"]
                if re.search(r"[CQASTHVcqast hv]",re.sub(r"[eE][+-]?\d+","",d).replace(" ","")):
                    raise ValueError("Unexpected curved field polygon")
                numbers=np.array([float(v) for v in re.findall(r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?",d)])
                xy=numbers.reshape(-1,2)
                x=(xy[:,0]-panel["tx"])/panel["sx"];y=(xy[:,1]-panel["ty"])/panel["sy"]
                use=(x>.50001)&(x<499.49999)&(y>.50001)&(y<499.49999)
                if use.any():
                    z=map_coordinates(field,np.array([y[use]-.5,x[use]-.5]),order=1,mode="nearest")
                    error=np.minimum(abs(z-rec["edges"][band]),abs(z-rec["edges"][band+1]))
                    max_error=max(max_error,float(error.max()))
                    vertices+=int(use.sum())
                paths+=1
        external=[e.attrib for e in root.iter() if e.tag.endswith("image")]
        row={"file":rec["file"],"panels":len(rec["panels"]),"field_paths":paths,
             "checked_isoband_vertices":vertices,"max_rate_backread_error_m_per_Myr":max_error,
             "embedded_or_external_raster_images":len(external),"common_scale":[rec["vmin"],rec["vmax"]],
             "passed":len(rec["panels"])==6 and vertices>0 and max_error<1e-4 and not external}
        rows.append(row)
    result={"files":rows,"passed":all(r["passed"] for r in rows)}
    c.write_json(out/"svg_checks.json",result)
    print("SVG backread passed:",result["passed"],flush=True)
    return result


def delivery(out):
    fits=c.read_json(out/"fitted_models.json")
    audit=c.read_json(out/"audit.json") if (out/"audit.json").exists() else {}
    lines=["# 背景垂向运动：五时段六种子", "",
           "每张SVG为一个时段的六种子最终速率场，统一FEM色标；正值抬升、负值沉降，图中单位m/百万年。", "",
           "| 时段（模拟百万年） | SVG | PNG预览 |", "|---|---|---|"]
    for m in fits["models"]:
        i=m["interval"]
        lines.append(f"| {m['start_elapsed_Myr']:g}至{m['end_elapsed_Myr']:g} | [SVG](uplift_interval{i:02d}.svg) | [PNG](uplift_interval{i:02d}.png) |")
    lines+=["","[空间统计对照](spatial_diagnostics.png) · [圈层权重](taper_weights.png) · [逐样本统计](sample_statistics.csv)",
            "","## 参考统计","",
            "| 时段 | 平均速率 m/百万年 | 标准差 m/百万年 | 拟合尺度x/y km |",
            "|---|---:|---:|---|"]
    for m in fits["models"]:
        lines.append(f"| {m['interval']} | {m['rate_mean_m_per_Myr']:+.6f} | {m['rate_std_m_per_Myr']:.6f} | {m['sigma_x_km']:.2f} / {m['sigma_y_km']:.2f} |")
    lines+=["","## 数据与检查","",
            "- source/ 为本次冻结的原始M2 PlateFrame网格、来源说明与许可；reference_window.npz保留99个原始格点和逐时段差分。",
            "- 每个seed目录保存未衰减和衰减后的m/yr数组、圈层权重及schedule.npz；这些数组尚未接入LEM。",
            f"- 数组与复现检查：{audit.get('passed','尚未运行')}。完整结果见audit.json，SVG坐标与数组核对见svg_checks.json。",
            "- 随机场在衰减前匹配每段的平均值、标准差和原网格距离上的空间变化；衰减后的全域平均及标准差另列。",
            "- 相关模型、空间提议选择和圈间过渡为本项目工程实现。窗口之外的相关尺度、跨时段空间协方差和后续LEM响应尚未验证。",
            "- 拟合尺度是随机场滤波尺度；其两倍只表示无限域高斯模型的理论1/e距离。当前有限窗口生成场的实测相关长度需另行解释。",
            "- 各时段使用独立随机流，未单独约束分布偏度、极值或跨时段协方差；参考均值为正的时段可能出现局部负值。详细规则见上一级README.md。",
            ""]
    if (out/"distribution_diagnostics.json").exists():
        distributions=c.read_json(out/"distribution_diagnostics.json")["intervals"]
        for row in distributions:
            fraction=max(r["fraction_of_whole_domain"] for r in row["final_negative_fractions"])
            if row["reference_rate_min_m_per_Myr"]>0 and fraction>0:
                lines.append(f"本批差异：第{row['interval']}时段M2原窗口全部为正值，生成最终场存在局部负值，"
                             f"最多占全域{fraction*100:.4f}%。分布与符号检查见[逐段记录](distribution_diagnostics.json)。")
                lines.append("")
    (out/"delivery.md").write_text("\n".join(lines),encoding="utf-8")
