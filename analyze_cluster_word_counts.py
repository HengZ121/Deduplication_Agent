"""Compare lengths with one observation per existing duplicate cluster.

Uses current aggregate membership CSVs, not older summary totals or cross-source
clusters. No model inference, reclustering, or source reconstruction is performed.
"""
from pathlib import Path
import hashlib
import json
import html
import numpy as np
import pandas as pd
from scipy.stats import mannwhitneyu
import plotly.graph_objects as go
from plotly.subplots import make_subplots

ROOT = Path('outputs')
OUT = ROOT/'cluster_word_counts'
GROUPS = ['Collapsed duplicate clusters', 'Standalone nodes']
COLORS = ['#237f85', '#bc7443']


def read_nodes():
    sources=[]; frames=[]
    for subset in ['body_en','body_fr','all_notes_en','all_notes_fr']:
        path=ROOT/f'kmt_dita_1_{subset}_kg_pipeline/kg_nodes.csv'
        d=pd.read_csv(path,keep_default_na=False)
        d['dataset']='KMT'; d['subset']=subset
        frames.append(d); sources.append(path)
    for lang in ['en','fr']:
        path=ROOT/f'ort_kmt_cross_deduplication/{lang}/cross_nodes.csv'
        d=pd.read_csv(path,keep_default_na=False)
        d=d[d.node_id.str.startswith('ORT:')].copy()
        d['dataset']='ORT'; d['subset']=lang
        frames.append(d); sources.append(path)
    nodes=pd.concat(frames,ignore_index=True)
    keys=['dataset','subset','node_id']
    assert not nodes.duplicated(keys).any(), 'Repeated node identity in inventory'
    memberships=[]
    for dataset in ['KMT','ORT']:
        path=ROOT/f'{dataset.lower()}_all_duplicate_cluster_files.csv'
        m=pd.read_csv(path,keep_default_na=False)
        assert (m.dataset==dataset).all()
        assert not m.duplicated(keys).any(), 'A node appears in multiple clusters'
        assert m.groupby(['subset','cluster_id']).size().ge(2).all()
        actual=m.groupby(['subset','cluster_id']).node_id.transform('size')
        assert (actual==m.cluster_size).all(), 'Cluster size mismatch'
        memberships.append(m); sources.append(path)
    membership=pd.concat(memberships,ignore_index=True)
    probe=membership.merge(nodes[keys],on=keys,how='left',indicator=True)
    assert (probe._merge=='both').all(), 'Cluster members missing from universe'
    nodes=nodes.merge(membership[keys+['cluster_id','file_content']],on=keys,how='left',validate='one_to_one')
    member=nodes.cluster_id.notna()
    # Aggregate CSV enrichment can resolve same-named note files in the wrong
    # language. Membership IDs remain useful; authoritative text/length comes
    # from the originating inventory, never from aggregate file_content.
    mismatch=member & nodes.text.ne(nodes.file_content)
    nodes.loc[mismatch,['dataset','subset','node_id','article_path','cluster_id','word_count']].to_csv(OUT/'aggregate_text_mismatches.csv',index=False)
    nodes['aggregate_text_mismatch']=mismatch
    nodes['cluster_id']=nodes.cluster_id.fillna('')
    nodes['clustered']=member
    nodes['eligible']=nodes.is_comparable.astype(str).str.lower().eq('true')
    nodes['word_count']=pd.to_numeric(nodes.word_count)
    assert nodes.word_count.gt(0).all()
    nodes['source_type']=np.where(nodes.dataset.eq('KMT'),
                                 np.where(nodes.subset.str.startswith('all_notes'),'notes','body'),
                                 nodes.article_path.str.split('/').str[1])
    # Singleton IDs cannot collide with duplicate IDs; subset remains part of identity.
    nodes['item_id']=np.where(member,'cluster:'+nodes.cluster_id,'singleton:'+nodes.node_id)
    return nodes,sources


def collapse(nodes, within_type=False):
    keys=['dataset','subset','item_id']+(['source_type'] if within_type else [])
    # Vectorized numeric aggregation avoids creating a DataFrame for every
    # singleton, which dominates this inventory and adds no analytical value.
    grouped=nodes.groupby(keys,sort=True)
    result=grouped.agg(clustered=('clustered','first'),cluster_id=('cluster_id','first'),
                       member_count=('node_id','size'),word_count=('word_count','median'),
                       mean_words=('word_count','mean'),min_words=('word_count','min'),
                       max_words=('word_count','max'),eligible=('eligible','all'))
    if not within_type:
        result['source_type']=grouped.source_type.agg(lambda values:'|'.join(sorted(set(values))))
    result=result.reset_index()
    result['group']=np.where(result.clustered,GROUPS[0],GROUPS[1])
    return result.drop(columns='clustered')


def compare(frame,label,view):
    a=frame.loc[frame.group.eq(GROUPS[0]),'word_count'].to_numpy()
    b=frame.loc[frame.group.eq(GROUPS[1]),'word_count'].to_numpy()
    if not len(a) or not len(b): return None
    # Descriptive probability of shorter, counting ties as one half; no causal claim.
    prob=1-mannwhitneyu(a,b,method='asymptotic').statistic/(len(a)*len(b))
    return dict(view=view,stratum=label,clusters=len(a),standalone_nodes=len(b),
                cluster_median=float(np.median(a)),standalone_median=float(np.median(b)),
                median_ratio=float(np.median(a)/np.median(b)),
                median_difference=float(np.median(a)-np.median(b)),
                probability_cluster_shorter=float(prob))


def box_figure(panels,title):
    cols=2; rows=(len(panels)+1)//2
    fig=make_subplots(rows=rows,cols=cols,subplot_titles=[p[0] for p in panels],vertical_spacing=min(.10,.3/rows))
    for i,(label,d) in enumerate(panels):
        row,col=i//cols+1,i%cols+1
        for j,group in enumerate(GROUPS):
            values=d.loc[d.group.eq(group),'word_count'].to_numpy()
            fig.add_trace(go.Box(y=values,name=('Clusters' if j==0 else 'Standalone'),
                legendgroup=group,showlegend=i==0,marker_color=COLORS[j],boxpoints='outliers',
                marker_size=3,line_width=1.5,quartilemethod='linear',
                hovertemplate=f'{group}<br>Words: %{{y}}<extra></extra>'),row=row,col=col)
            if len(values):
                fig.add_annotation(x=j,y=.96,xref=f'x{i+1 if i else ""}',yref=f'y{i+1 if i else ""} domain',
                    text=f'n={len(values):,}; median={np.median(values):g}',showarrow=False,font_size=11,bgcolor='rgba(255,255,255,0.9)')
        fig.update_yaxes(type='log',title_text='Words (log scale)',row=row,col=col)
        fig.update_xaxes(categoryorder='array',categoryarray=['Clusters','Standalone'],row=row,col=col)
    log={f'yaxis{n if n>1 else ""}.type':'log' for n in range(1,len(panels)+1)}
    linear={f'yaxis{n if n>1 else ""}.type':'linear' for n in range(1,len(panels)+1)}
    for n in range(1,len(panels)+1):
        key=f'yaxis{n if n>1 else ""}.title.text'
        log[key]='Words (log scale)';linear[key]='Words (linear scale)'
    fig.update_layout(title_text=title,height=390*rows+100,template='plotly_white',
                      margin=dict(t=130,b=60,l=70,r=35),legend=dict(orientation='h',y=1.17),
                      updatemenus=[dict(type='buttons',direction='right',x=1,xanchor='right',y=1.17,
                                       buttons=[dict(label='Log scale',method='relayout',args=[log]),dict(label='Linear scale',method='relayout',args=[linear])])])
    return fig


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    nodes,sources=read_nodes(); items=collapse(nodes)
    assert len(items)==nodes.loc[~nodes.clustered].shape[0]+nodes.loc[nodes.clustered].groupby(['dataset','subset','cluster_id']).ngroups
    assert items.member_count.sum()==len(nodes)
    labels={'body_en':'KMT bodies · English','body_fr':'KMT bodies · French',
            'all_notes_en':'KMT notes · English','all_notes_fr':'KMT notes · French',
            'en':'ORT · English','fr':'ORT · French'}
    overview=[(dataset,items[items.dataset.eq(dataset)]) for dataset in ['KMT','ORT']]
    detail=[(label,items[items.subset.eq(subset)]) for subset,label in labels.items()]
    eligible=[(label,d[d.eligible]) for label,d in detail]
    typed=collapse(nodes,within_type=True)
    orttypes=[(f'ORT {kind} · EN + FR',typed[typed.dataset.eq('ORT') & typed.source_type.eq(kind)])
              for kind in sorted(nodes.loc[nodes.dataset.eq('ORT'),'source_type'].unique())]
    comparisons=[]
    for view,panels in [('pooled',overview),('by_subset',detail),('eligible_only',eligible),('ORT_within_type',orttypes)]:
        for label,d in panels:
            r=compare(d,label,view)
            if r:comparisons.append(r)
    stats=pd.DataFrame(comparisons)
    # Sensitivity to how the cluster is collapsed, with every cluster still weighted once.
    sensitivity=[]
    for method in ['min_words','word_count','mean_words','max_words']:
        alternative=items.copy();alternative['word_count']=alternative[method]
        for dataset in ['KMT','ORT']:
            r=compare(alternative[alternative.dataset.eq(dataset)],dataset,method)
            sensitivity.append(r)
    pd.DataFrame(sensitivity).to_csv(OUT/'collapse_sensitivity.csv',index=False)
    stats.to_csv(OUT/'comparison_statistics.csv',index=False)
    items.to_csv(OUT/'collapsed_items.csv',index=False)
    nodes[['dataset','subset','node_id','article_path','source_type','cluster_id','clustered','eligible','word_count','item_id']].to_csv(OUT/'node_membership_word_counts.csv',index=False)
    quantiles=[]
    for subset,g in items.groupby('subset'):
        for group,d in g.groupby('group'):
            q=d.word_count.quantile([.25,.5,.75]);iqr=q.loc[.75]-q.loc[.25]
            quantiles.append(dict(subset=subset,group=group,n=len(d),min=d.word_count.min(),q1=q.loc[.25],median=q.loc[.5],q3=q.loc[.75],max=d.word_count.max(),
                                  lower_whisker=d.loc[d.word_count.ge(q.loc[.25]-1.5*iqr),'word_count'].min(),
                                  upper_whisker=d.loc[d.word_count.le(q.loc[.75]+1.5*iqr),'word_count'].max()))
    pd.DataFrame(quantiles).to_csv(OUT/'boxplot_statistics.csv',index=False)
    figures=[box_figure(overview,'Collapsed clusters versus standalone nodes'),
             box_figure(detail,'Separate language and KMT content type'),
             box_figure(eligible,'Sensitivity: matching-eligible items only'),
             box_figure(orttypes,'ORT: comparison within source type')]
    texts=[]
    for r in comparisons:
        if r['view'] in ['pooled','by_subset','eligible_only']:
            texts.append(f"| {r['view']} | {r['stratum']} | {r['clusters']:,} | {r['standalone_nodes']:,} | {r['cluster_median']:g} | {r['standalone_median']:g} | {r['median_ratio']:.2f} | {r['probability_cluster_shorter']:.1%} |")
    methodology='''Each existing duplicate cluster contributes one observation: the median stored word_count of its members. Each standalone node contributes its own count. We do not sum member lengths, count a cluster once per member, or choose a final master copy. A fractional value can arise from an even-sized cluster.

Membership comes from outputs/kmt_all_duplicate_cluster_files.csv and outputs/ort_all_duplicate_cluster_files.csv. These are separate within-source cluster inventories, not ORT–KMT cross-source clusters. ORT uses the internal-run membership (3,753 clusters), not the older reviewed-run summary (4,350 clusters). All members were matched by node ID to their originating inventories. KMT uses the four cleaned kmt_dita_1 body/all_notes inventories; ORT uses the ORT rows of cross_nodes.csv, the universe used by its internal clustering script. Data-quality check: 2,902 KMT English note rows have aggregate file_content that differs from inventory text (the inspected example contains French text). We use inventory word_count, not aggregate file_content. Mismatch IDs are listed in aggregate_text_mismatches.csv; other subsets have no text mismatches.

Lengths are the saved pipeline word_count values of extracted node text, using the pipeline word-token definition rather than character count. They measure what was available to that run. They do not restore omitted conref tables/notes or measure the complete original publication. Existing cluster labels are pipeline decisions, not validated safe-reuse groups; KMT and ORT membership was produced by different runs/review policies.

Boxes span the 25th–75th percentiles; the line is the median; whiskers reach the furthest observation within 1.5 IQR; points beyond them are retained as outliers. Quartiles and fences are computed on original word counts; the default log axis only changes display. Linear scale is available. All positive-length items are included initially. The eligibility sensitivity view uses saved is_comparable and retains a cluster only if all members are eligible. Eligibility does not prove a node was compared against every possible partner. Unclustered means not assigned to an existing cluster, not proven unique.

Language and KMT body/note panels prevent a pooled result from hiding different populations. ORT source-type panels collapse a cluster separately within each type it contains; a mixed-type cluster can appear in several panels, so those panels must not be summed. English/French are pooled in those source-type panels only.

The probability column is P(cluster length < standalone length) + 0.5 × P(tie), computed over all cross-group comparisons. It is descriptive, not a causal effect or a significance test. A median ratio below 1 indicates shorter typical collapsed-cluster length. This does not establish that the classifier prefers short text: retrieval thresholds, content type, template structure, and review policy also affect cluster membership. Collapse sensitivity reports minimum, median, mean and maximum member length, with equal cluster weighting throughout.'''
    findings='''ORT clusters are shorter at the median: 81.5 words versus 98 for standalone nodes (16.8% lower), with the same direction in English and French. KMT is only slightly shorter when pooled: 50 versus 54 words (7.4% lower). That pooled KMT result hides opposite patterns: body clusters are longer (English 94 versus 81; French 122.25 versus 93), while note clusters are shorter (English 28 versus 32; French 33 versus 37). These directions persist in the matching-eligible sensitivity view. Therefore “clustered nodes have fewer words” is supported descriptively for ORT and KMT notes, but not for KMT bodies.

The distributions overlap substantially: a randomly selected collapsed cluster is shorter than a standalone node, with ties half-counted, in 54.8% of ORT and 51.3% of pooled KMT comparisons. Word count alone is consequently a weak separator. ORT source-type results vary, and the policy panel has only one cluster: do not generalize its median. A higher prevalence of short repetitive notes can explain an overall pattern without a universal short-text bias.

The collapsing rule matters most for KMT: using each cluster's longest member instead of its median reverses the pooled comparison (59 versus 54 words). ORT remains shorter under minimum, median, mean and maximum member-length choices. These are sensitivity checks, not recommendations to select the shortest or longest member as the master copy.'''
    report='# Word counts of collapsed duplicate clusters\n\n'+findings+'\n\n## Method and limitations\n\n'+methodology+'\n\n| View | Dataset | Clusters | Standalone | Cluster median | Standalone median | Median ratio | Probability shorter |\n|---|---|---:|---:|---:|---:|---:|---:|\n'+'\n'.join(texts)
    (OUT/'REPORT.md').write_text(report,encoding='utf-8')
    table=stats.round(3).to_html(index=False,classes='stats')
    page='<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Cluster word-count box plots</title><style>body{font:16px/1.6 Arial;margin:24px auto;max-width:1250px;padding:0 20px;color:#203243}p{max-width:1050px}table{border-collapse:collapse;font-size:13px}td,th{padding:6px;border-bottom:1px solid #ccd3da;text-align:right}.table{overflow-x:auto}a{color:#006a83}</style></head><body><h1>Are clustered nodes shorter?</h1><p>One observation per duplicate cluster (median member length), compared with one observation per standalone node. The charts use saved pipeline text lengths; they do not measure reconstructed full documents.</p>'
    page+=''.join('<p>'+html.escape(p)+'</p>' for p in findings.split('\n\n'))
    for i,fig in enumerate(figures):
        if i==2:page+='<p>Matching-eligible items only: removes nodes excluded by the saved comparability flag; clusters are retained only when all members are eligible.</p>'
        if i==3:page+='<p>Within-type sensitivity: mixed-type clusters contribute once within each represented source type. These panel counts are not additive.</p>'
        page+=fig.to_html(full_html=False,include_plotlyjs=True if i==0 else False,config={'responsive':True,'displaylogo':False})
    page+='<h2>Statistics and method</h2><div class="table">'+table+'</div>'+''.join('<p>'+html.escape(p)+'</p>' for p in methodology.split('\n\n'))
    page+='<p><a href="collapsed_items.csv">Every collapsed observation</a> · <a href="node_membership_word_counts.csv">Node membership and lengths</a> · <a href="comparison_statistics.csv">Comparison statistics</a> · <a href="collapse_sensitivity.csv">Collapse sensitivity</a> · <a href="REPORT.md">Report</a></p></body></html>'
    (OUT/'boxplots.html').write_text(page,encoding='utf-8')
    manifest=[dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sources+[Path(__file__)]]
    (OUT/'input_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    validation=dict(nodes=len(nodes),collapsed_items=len(items),cluster_members=int(nodes.clustered.sum()),clusters=int(items.group.eq(GROUPS[0]).sum()),standalone=int((~nodes.clustered).sum()),
                    mixed_ORT_clusters=int(items.loc[items.dataset.eq('ORT') & items.group.eq(GROUPS[0]),'source_type'].str.contains('|',regex=False).sum()),
                    aggregate_text_mismatches=int(nodes.aggregate_text_mismatch.sum()),
                    checks=['No repeated node IDs within dataset/subset','All cluster members resolve','Cluster sizes agree','Aggregate text mismatches recorded; authoritative inventory counts used','Collapsed counts reconcile','All word counts positive'])
    (OUT/'validation.json').write_text(json.dumps(validation,indent=2),encoding='utf-8')
    print(stats.to_string(index=False));print(json.dumps(validation,indent=2))


if __name__=='__main__':main()
