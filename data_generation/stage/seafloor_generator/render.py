"""Maps are direct array encodings; all reused masks stay unchanged."""
import numpy as np
from PIL import Image,ImageDraw
from scipy import stats
import bootstrap as b

PALETTE=np.array([(155,155,155),(112,188,226),(13,43,99)],dtype=np.uint8)
INK=(25,34,49)


def type_image(field):
    return Image.fromarray(PALETTE[np.flipud(field).astype(np.uint8)])


def save_sample(folder,sample,field,types,target,actual,metrics):
    primary=type_image(field);primary.save(folder/'seafloor.png')
    target_pic=type_image(np.where(sample['mask'],0,1))
    draw=ImageDraw.Draw(target_pic)
    for (x,y),deep in zip(sample['coast'].xy,target):
        draw.ellipse((x-1,500-y-1,x+1,500-y+1),fill=tuple(PALETTE[2 if deep else 1]))
    target_pic.save(folder/'coast_targets.png')
    borders=np.zeros(field.shape,bool)
    labels=sample['labels'];borders[1:]|=labels[1:]!=labels[:-1];borders[:,1:]|=labels[:,1:]!=labels[:,:-1]
    rgb=PALETTE[field].copy();rgb[borders]=(rgb[borders].astype(float)*.80).astype(np.uint8)
    partitions=Image.fromarray(np.flipud(rgb));partitions.save(folder/'partition_types.png')
    canvas=Image.new('RGB',(1596,638),'white');d=ImageDraw.Draw(canvas)
    d.text((24,10),f'种子 {sample["seed"]} · 海底类型分配 · 完整地块组合',font=b.font(25),fill=INK)
    for i,(title,pic) in enumerate(zip(('① 沿轮廓的函数目标','② 完整地块类型','③ 最终分类图'),(target_pic,partitions,primary))):
        x=24+i*524;d.text((x,51),title,font=b.font(21),fill=INK);canvas.paste(pic,(x,87))
    d.text((24,603),f'深海沿岸比例：目标 {metrics["target_deep_coast_fraction"]:.2%}，实际 {metrics["actual_deep_coast_fraction"]:.2%}；偏差 {metrics["ratio_error_pp"]:.2f} 个百分点',font=b.font(20),fill=INK)
    canvas.save(folder/'stages.png')


def save_overview(output,samples):
    canvas=Image.new('RGB',(1596,1324),'white');d=ImageDraw.Draw(canvas)
    distance=b.read_json(output/'distance.json')['observation_distance_km']
    d.text((24,12),'水下台地周边 · 六个种子的海底类型分配',font=b.font(30),fill=INK)
    d.text((24,55),f'统一观测距离 {distance} km · 512 分区 · 完整地块保留',font=b.font(19),fill=INK)
    for x,code,text in ((960,2,'深海'),(1150,1,'浅海'),(1340,0,'台地 mask')):
        d.rectangle((x,49,x+25,74),fill=tuple(PALETTE[code]));d.text((x+34,49),text,font=b.font(19),fill=INK)
    names={'mixed':'混合','all_shallow':'全浅海','all_deep':'全深海'}
    for k,row in enumerate(samples):
        x=24+(k%3)*524;y=102+(k//3)*612
        d.text((x,y),f'种子 {row["seed"]} · {names[row["regime"]]}',font=b.font(22),fill=INK)
        with Image.open(output/f'seed{row["seed"]}'/'seafloor.png') as pic:canvas.paste(pic,(x,y+35))
        d.text((x,y+543),f'深海沿岸：{row["actual_deep_coast_fraction"]:.1%} / 目标 {row["target_deep_coast_fraction"]:.1%}',font=b.font(18),fill=INK)
        d.text((x,y+566),f'台地面积 {row["platform_fraction"]:.1%} · 比例偏差 {row["ratio_error_pp"]:.2f} pp',font=b.font(17),fill=INK)
    canvas.save(output/'comparison.png')


def plot_fits(output,functions):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(2,2,figsize=(12,8),layout='constrained')
    data=b.read_json(output/'reference/landmasses.json');segments=b.read_json(output/'reference/segments.json')
    r=functions.record
    axes[0,0].bar(['All shallow','Mixed','All deep'],r['environment']['probabilities'],color=['#70bce2','#5281c8','#0d2b63'])
    axes[0,0].set(title='Function 1: fitted type probabilities',ylabel='Probability',ylim=(0,1))
    x=np.linspace(.001,.999,400);ratio=r['mixed_ratio']
    vals=[v['deep_share_known_water'] for v in data if v['regime']=='mixed']
    axes[0,1].hist(vals,bins=np.linspace(0,1,7),density=True,alpha=.35,color='#5281c8',label='Mixed references')
    axes[0,1].plot(x,stats.beta.pdf(x,ratio['alpha'],ratio['beta']),color='#0d2b63',label='Fitted beta')
    axes[0,1].set(title='Function 2: deep fraction in a mixed sample',xlabel='Deep / known marine coast length',ylabel='Density');axes[0,1].legend()
    for ax,typ,num in ((axes[1,0],'deep',3),(axes[1,1],'shallow',4)):
        rows=[z for z in segments if z['used_for_fit'] and z['environment']==typ]
        model=r[typ+'_length'];lengths=np.array([v['length_km'] for v in rows]);is_lower=np.array([v['censored'] for v in rows])
        hi=max(float(lengths.max()),float(np.exp(model['mu_log_km']+2*model['sigma_log'])))
        x=np.geomspace(max(.1,float(lengths.min())*.5),hi,400)
        ax.plot(x,stats.lognorm.cdf(x,model['sigma_log'],scale=np.exp(model['mu_log_km'])),label='Fitted CDF',color='#0d2b63')
        ax.scatter(lengths[~is_lower],np.full((~is_lower).sum(),.03),marker='|',alpha=.7,label='Complete run')
        ax.scatter(lengths[is_lower],np.full(is_lower.sum(),.08),marker='>',alpha=.35,label='Lower bound')
        ax.set(xscale='log',ylim=(0,1),title=f'Function {num}: {typ} run length (censor-aware)',xlabel='Length (km)',ylabel='Cumulative probability');ax.legend(fontsize=8)
    fig.suptitle(f'Fitted functions at {b.read_json(output/"distance.json")["observation_distance_km"]} km; 34 reference landmasses',fontsize=14)
    fig.savefig(output/'fitted_functions.png',dpi=150);plt.close(fig)


def write_report(output,samples,audit):
    distance=b.read_json(output/'distance.json');quality=b.read_json(output/'reference/quality.json')
    functions=b.read_json(output/'functions.json')
    lines=['# 海底比例与分配：六种子结果','',f'平均可用海域宽度 {distance["mean_width_km"]:.6f} km，统一参考观测距离 {distance["observation_distance_km"]} km。',
       '', '颜色：台地灰色，浅海浅蓝，深海深蓝。原尺寸图的每个像素对应1 km方格。',
       '', '| 种子 | 周边类型 | 深海目标比例 | 实际比例 | 偏差 pp | 深海目标/实际段数 | 浅海目标/实际段数 |',
       '|---|---|---:|---:|---:|---|---|']
    for s in samples:
        d=s['deep_segments'];h=s['shallow_segments']
        names={'all_shallow':'全浅海','mixed':'混合','all_deep':'全深海'}
        lines.append(f'| {s["seed"]} | {names[s["regime"]]} | {s["target_deep_coast_fraction"]:.3%} | {s["actual_deep_coast_fraction"]:.3%} | {s["ratio_error_pp"]:.3f} | {d["target_count"]}/{d["actual_count"]} | {h["target_count"]}/{h["actual_count"]} |')
    lines+=['','完整地块约束、原mask不变、PNG回读、分段长度还原及输入哈希核查：'+str(audit['passed']),
       '',f'参考总体：{quality["regime_counts"]}。平均已知海水端点岸长覆盖率 {quality["known_coast_fraction_mean"]:.2%}。',
       '', '比例拟合使用可确定深浅类别的海水端点岸长；全部岸长分母的结果也保存。未知类别不作为浅海。',
       '被未知段截断的长度使用生存似然作为下界。四个函数均由数据拟合参数，生成时使用新的随机数；没有选择某个真实陆块或重放其序列。',
       f'深海长度：{functions["deep_length"]["n_complete"]}条完整观测、{functions["deep_length"]["n_lower_bounds"]}条下界；浅海长度：{functions["shallow_length"]["n_complete"]}条完整观测、{functions["shallow_length"]["n_lower_bounds"]}条下界。浅海长度拟合对截断处理和函数族假设有较强依赖，尚未完成地学合理性验证。',
       '段长与比例在闭合轮廓上共同条件化，原始函数输出及缩放系数保存于 targets.json。完整地块组合造成的段数、段长和比例偏差保存于 metrics.json。',
       '每个混合样本保留同一组函数输出，比较沿轮廓的32个等距放置位置，再按比例、段长及段数的归一化误差选择。全部候选及评分保存在 targets.json 的 placement 字段。',
       '外侧无连通路径的内部空缺首版分类为浅海并单列；这是实现假设，未定义其实际深度。',
       '本轮不生成高程、不运行侵蚀沉积、不修改掩膜。技术检查不构成全部地学合理性验收。',
       '', '参考来源与输入哈希：reference/sources.json、input_masks.json、manifest.json。',
       '计算代码与完整方法：[README](../../../data_generation/stage/seafloor_generator/README.md)。','',
       '| 种子 | 类型 | 目标段长 km | 实际段长 km | 段长分布距离 km |',
       '|---|---|---|---|---:|']
    for s in samples:
        if s['regime']!='mixed':continue
        for key,name in (('deep_segments','深海'),('shallow_segments','浅海')):
            r=s[key]
            lines.append(f'| {s["seed"]} | {name} | {r["target_lengths_km"]} | {r["actual_lengths_km"]} | {r["wasserstein_error_km"]:.2f} |')
    lines+=['','目标与实际长度各自按轮廓起点排列；逐段位置见各样本的 target_segments.json 与 actual_segments.json。表中的分布距离为一阶 Wasserstein 距离，单位 km，用于比较两组段长分布。','']
    (output/'REPORT.md').write_text('\n'.join(lines),encoding='utf-8')
    cards=[]
    for s in samples:
        seed=s['seed'];cards.append(f'<section><h2>种子 {seed}</h2><a href="seed{seed}/seafloor.png"><img alt="种子{seed}海底类型分配" src="seed{seed}/seafloor.png" width="500" height="500"></a><p>深海沿岸比例：目标 {s["target_deep_coast_fraction"]:.2%}，实际 {s["actual_deep_coast_fraction"]:.2%}，偏差 {s["ratio_error_pp"]:.2f} 个百分点</p><p><a href="seed{seed}/stages.png">三个可见阶段</a> · <a href="seed{seed}/metrics.json">目标与实际指标</a> · <a href="seed{seed}/targets.json">函数输出</a></p></section>')
    page='<!doctype html><meta charset="utf-8"><title>海底比例与分配</title><style>body{font-family:system-ui;margin:28px;background:#edf2f7;color:#18283e}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(510px,1fr));gap:20px}section{padding:16px;background:white;border-radius:12px}img{max-width:100%;height:auto;image-rendering:pixelated}a{color:#154e89}</style>'
    page+=f'<h1>海底比例与分配</h1><p>深海深蓝 · 浅海浅蓝 · 台地mask灰色。全部类型按完整分区分配。</p><p>平均海域宽度 {distance["mean_width_km"]:.3f} km，采用 {distance["observation_distance_km"]} km 重算参考统计。</p><p>参考浅海段只有 {functions["shallow_length"]["n_complete"]} 条完整长度，另有 {functions["shallow_length"]["n_lower_bounds"]} 条截断下界。当前段长函数对截断处理假设有较强依赖。</p><p><a href="REPORT.md">计算说明</a> · <a href="fitted_functions.png">四个拟合函数</a> · <a href="audit.json">核查记录</a></p><main>'+''.join(cards)+'</main>'
    (output/'report.html').write_text(page,encoding='utf-8')
