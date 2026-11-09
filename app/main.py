"""Focused Streamlit entry point for figure-based dimension verification."""
from __future__ import annotations
import csv
import hashlib
import io
import json
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import streamlit as st
import streamlit.components.v1 as components
from app.geometry_check import (ENGINE_VERSION, DimensionCheck, align_projection,
    check_dimension, drawing_primitives, load_drawing, load_solid, overall_result,
    project_visible, svg_overlay,unresolved_dimension,suggest_projection)
from app.dxf_reader import analyze_dxf_bytes
from app.view_segmentation import segment_views
from app.step_section import section_shape
from app.visual_workspace import header, comparison_panels, svg_projection_sheet
from app.inspection_summary import render_summary_controls, report_fingerprint, summary_sections

APP_NAME = 'CAD AI Checker'
APP_STAGE = 'Geometry-based dimension verification'

def get_app_status():
    return {'application': APP_NAME, 'stage': APP_STAGE, 'version': ENGINE_VERSION}


def pdf_report(payload, ai_summary=None):
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    import textwrap
    buffer = io.BytesIO(); c = canvas.Canvas(buffer, pagesize=A4)
    c.setTitle('CAD dimension verification')
    y = 805
    lines = [f"CAD dimension verification — {payload['result']}",
             f"Engine: {ENGINE_VERSION} | UTC: {payload['generated_at']}",
             f"Drawing: {payload['drawing']} | Model: {payload['model']}",
             'Check basis: '+payload.get('comparison_mode','limits'),
             'Scope: assigned dimensions only. Not full shape or GD&T certification.',
             f"DXF SHA256: {payload['drawing_sha256']}", f"STEP SHA256: {payload['model_sha256']}", '']
    for row in payload['checks']:
        lines.extend([f"{row['dimension']} | {row['view']} | {row['kind']} | {row['result']}",
                      f"Nominal: {row['nominal']}  Model: {row['measured']}  Limits: {row['lower']} to {row['upper']}",
                      f"Tolerance source: {row['tolerance_source']}",
                      f"Nominal comparison: {row.get('nominal_result','Not checked')} | Tolerance: {row.get('tolerance_result','Not checked')}",
                      f"Features: {', '.join(row['features'])}", row['reason'], ''])
    lines += ['View and section settings:', json.dumps(payload['views'], ensure_ascii=True)]
    def draw_line(line,font='Helvetica'):
        nonlocal y
        if y < 45: c.showPage(); y = 805
        c.setFont(font,8); c.drawString(30,y,line); y -= 12
    if ai_summary and ai_summary.get('report_fingerprint')==report_fingerprint(payload):
        lines += ['', 'Optional AI-generated explanation (review against measured evidence)',
                  f"Provider: {ai_summary['provider']} | Model: {ai_summary['model']}"]
    for text in lines:
        for line in textwrap.wrap(text, 100) or ['']:
            draw_line(line)
    if ai_summary and ai_summary.get('report_fingerprint')==report_fingerprint(payload):
        from reportlab.lib.textsplit import wordSplit
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        jp_font='HeiseiKakuGo-W5'
        for title,suffix,body in summary_sections(ai_summary):
            font=jp_font if suffix else 'Helvetica'
            if suffix and font not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(UnicodeCIDFont(font))
            draw_line('')
            draw_line(title,font)
            for paragraph in body:
                for source_line in paragraph.splitlines():
                    for _,line in wordSplit(source_line,A4[0]-60,font,8):
                        draw_line(line,font)
    c.save(); return buffer.getvalue()


def run_workspace():
    st.subheader('1. Select the two CAD files')
    st.caption('1. 2つのCADファイルを選択')
    a,b = st.columns(2)
    a.markdown('**2D DRAWING**  \n2D図面')
    b.markdown('**3D MODEL**  \n3Dモデル')
    dxf = a.file_uploader('2D drawing (.dxf)', type=['dxf'])
    step = b.file_uploader('3D model (.step / .stp)', type=['step','stp'])
    with st.expander('Comparison settings'):
        basis=st.radio('Check basis',['Nominal dimensions','Tolerance limits'],horizontal=True,
                       help='Nominal mode compares the stated dimension value. Tolerance mode requires explicit drawing limits or an enabled project rule.')
        use_general = st.checkbox('Apply project tolerance where the drawing has no explicit limit', value=False)
        general = st.number_input('Project tolerance ± mm', min_value=.0001, value=.1, format='%.4f', disabled=not use_general)
        association = st.number_input('Maximum anchor search distance (mm)', min_value=.001, max_value=10., value=1., format='%.3f')
        st.caption('Simple rectangles, concentric circles and clean capsule profiles use geometric feature roles, even when sizes differ. Other profiles use the anchor search distance. It is NOT the pass/fail tolerance; ambiguous features remain unresolved.')
    comparison_mode='nominal' if basis=='Nominal dimensions' else 'limits'
    st.caption('Check basis: '+basis+'. Nominal matching uses 0.000001 mm numerical precision; it does not certify tolerance compliance.')
    if not (dxf and step):
        for key in ('report','input_signature','cad_doc','cad_solid','cad_analysis','projection_cache'):
            st.session_state.pop(key,None)
        st.info('Upload both files. Select the corresponding view or cut plane, inspect alignment, then run the dimension check.')
        st.button('Run CAD Check / CAD照合を実行',type='primary',use_container_width=True,disabled=True)
        return
    drawing_data, model_data = dxf.getvalue(), step.getvalue()
    signature = hashlib.sha256(drawing_data+model_data+ENGINE_VERSION.encode()).hexdigest()
    if st.session_state.get('input_signature') != signature:
        st.session_state.pop('report', None)
        try:
            with st.spinner('Reading geometry…'):
                doc, solid = load_drawing(drawing_data), load_solid(model_data)
                analysis = analyze_dxf_bytes(drawing_data, dxf.name)
            st.session_state.update(input_signature=signature, cad_doc=doc, cad_solid=solid,
                                    cad_analysis=analysis, projection_cache={})
        except Exception as exc:
            st.error(f'Cannot read geometry: {exc}'); return
    doc, solid, analysis = (st.session_state[k] for k in ('cad_doc','cad_solid','cad_analysis'))
    if int(doc.header.get('$INSUNITS', 0)) == 0:
        st.warning('The DXF is unitless. Confirm that its geometry is in millimetres.')
        units_ok = st.checkbox('This DXF is in millimetres', key='units_'+signature)
    else: units_ok = True
    entities = list(doc.modelspace())
    dimensions = {f'DIM-{i:03d}': e for i,e in enumerate((e for e in entities if e.dxftype()=='DIMENSION'),1)}
    factors=sorted({float(e.override().get('dimlfac',1)) for e in dimensions.values() if float(e.override().get('dimlfac',1))!=1.})
    if factors:
        st.warning('DXF dimension display factor (DIMLFAC): '+', '.join(f'{factor:g}' for factor in factors)+'. Generated drawing labels use this factor; STEP measurements remain unscaled. Confirm any intended drawing/detail scale separately.')
    entity_dim = {i: key for i,e in enumerate(entities,1) for key,d in dimensions.items() if e is d}
    if not dimensions:
        st.error('NG — cannot verify: no native DXF DIMENSION entities. Exploded text/lines are not treated as dimensions.'); return
    with st.expander('Drawing layers and view separation'):
        layers = list(analysis.layers)
        excluded = st.multiselect('Exclude annotation, centreline, border, or construction layers', layers,
                                  default=[x for x in layers if any(s in x.upper() for s in ['DEFPOINTS','CENTER','CENTRE','BORDER','TITLE'])])
        gap = st.number_input('View separation gap (mm)', min_value=0., max_value=100., value=2.)
        st.caption('Check each preview. Exploded annotations on a geometry layer must be separated in the DXF before checking.')
    filtered = replace(analysis, entity_locations=tuple(x for x in analysis.entity_locations if x.layer not in excluded and x.entity_type in {'LINE','ARC','CIRCLE','LWPOLYLINE','POLYLINE','SPLINE','ELLIPSE'}))
    views = segment_views(filtered, gap_mm=gap)
    if not views:
        st.error('No comparable drawing views found.'); return
    with st.expander(f'Drawing dimensions detected: {len(dimensions)}',expanded=True):
        st.dataframe([{'Dimension':key,'Drawing nominal':unresolved_dimension(e,key,'Not measured yet.').nominal,
                       'Figure':next((v.view_id for v in views if any(entity_dim.get(i)==key for i in v.dimension_indexes)),'Unassigned')}
                      for key,e in dimensions.items()],hide_index=True,use_container_width=True)
    st.subheader('2. Match figures and dimensions')
    st.caption('Select the actual projection or section for each view. Dark grey: DXF. Amber: STEP. Alignment is rigid; no automatic resizing.')
    prepared=[]; selections=[]; assigned=[]; errors=[]
    box=solid.BoundingBox()
    for view in views:
        try: drawing = drawing_primitives(doc, set(view.entity_indexes), excluded)
        except ValueError as exc:
            st.error(f'Cannot prepare {view.view_id}: {exc}'); return
        if not drawing: continue
        with st.expander(view.view_id, expanded=True):
            default=[entity_dim[i] for i in view.dimension_indexes if i in entity_dim]
            chosen=st.multiselect('Dimensions belonging to this figure',list(dimensions),default=default,key=signature+view.view_id+'dims')
            c1,c2,c3=st.columns(3)
            mode=c1.selectbox('STEP geometry', ['Projection','Section'],key=view.view_id+'mode')
            offset=None; axis=None; hidden=False
            if mode=='Projection':
                names=['top','front','right','bottom','rear','left']
                suggested=suggest_projection(solid,drawing,st.session_state.projection_cache)
                name=c2.selectbox('View',names,index=names.index(suggested),key=signature+view.view_id+'source')
                st.caption('Initial view suggested from outline geometry. Inspect and confirm it; equal outlines do not establish feature correspondence.')
                hidden=c3.checkbox('Include hidden edges',key=view.view_id+'hidden')
            else:
                axis=c2.selectbox('Cut normal',list('XYZ'),key=view.view_id+'axis')
                lo,hi={'X':(box.xmin,box.xmax),'Y':(box.ymin,box.ymax),'Z':(box.zmin,box.zmax)}[axis]
                offset=c3.number_input(f'{axis} plane position (STEP mm)',value=float((lo+hi)/2),key=signature+view.view_id+axis+'offset')
                name=f'{axis} section at {offset:g} mm'
                st.caption('A real intersection with the solid at this absolute coordinate. Confirm that it matches the drawing cutting plane. Oblique/stepped sections are not supported.')
            r,t,u=st.columns(3)
            rotation=r.selectbox('Rotation (degrees)', [0,90,180,270],key=view.view_id+'rotation')
            dx=t.number_input('Alignment X offset (mm)',value=0.,key=view.view_id+'dx')
            dy=u.number_input('Alignment Y offset (mm)',value=0.,key=view.view_id+'dy')
            settings={'view':view.view_id,'mode':mode,'source':name,'axis':axis,'offset':offset,'hidden':hidden,'rotation':rotation,'dx':dx,'dy':dy,'dimensions':chosen,'excluded_layers':excluded,'gap':gap}
            confirmation_key=hashlib.sha256((signature+json.dumps(settings,sort_keys=True)).encode()).hexdigest()
            try:
                cache=st.session_state.projection_cache
                key=(mode,name,hidden)
                if key not in cache:
                    cache[key]=project_visible(solid,name,hidden) if mode=='Projection' else section_shape(solid,axis,offset)
                projection=align_projection(cache[key],drawing,rotation//90,dx,dy)
                comparison_panels(drawing,projection)
                st.caption('Confirm the corresponding figure and orientation, even if its dimensions differ. The STEP model is never resized to fit the drawing.')
                confirmed=st.checkbox('This view/section corresponds to the drawing figure; orientation and position are confirmed',key=confirmation_key)
                prepared.append((view.view_id,chosen,projection,drawing,confirmed and units_ok))
            except Exception as exc:
                st.error(f'Cannot generate this view: {exc}')
                if chosen: errors.extend(chosen)
            assigned.extend(chosen); selections.append(settings)
    st.caption(f'{len(dimensions)} dimensions found · {len(set(assigned))} assigned · {sum(p[4] for p in prepared)} of {len(prepared)} figure alignments confirmed.')
    st.info('Confirm the drawing units and each matching figure alignment for a verified judgement. Unconfirmed measurements are shown as preliminary.')
    run_signature=hashlib.sha256(json.dumps([signature,selections,comparison_mode,use_general,general,association,[(p[0],p[4]) for p in prepared]],sort_keys=True).encode()).hexdigest()
    if st.session_state.get('report_signature') != run_signature: st.session_state.pop('report',None)
    if st.button('Run CAD Check / CAD照合を実行',type='primary',use_container_width=True):
        checks=[]
        for view_id,chosen,projection,drawing,confirmed in prepared:
            for key in chosen:
                if assigned.count(key)>1: continue
                checks.append(check_dimension(dimensions[key],key,view_id,projection,drawing,association,general if use_general else None,confirmed,comparison_mode))
        checked={c.dimension for c in checks}
        for key in dimensions:
            if key not in checked:
                reason='Assigned to multiple views.' if assigned.count(key)>1 else 'View generation failed.' if key in errors else 'Not assigned to a usable drawing view.'
                checks.append(unresolved_dimension(dimensions[key],key,reason))
        payload={'engine':ENGINE_VERSION,'generated_at':datetime.now(timezone.utc).isoformat(),
                 'drawing':dxf.name,'model':step.name,'drawing_sha256':hashlib.sha256(drawing_data).hexdigest(),
                 'model_sha256':hashlib.sha256(model_data).hexdigest(),'result':overall_result(checks),
                 'scope':'Native assigned dimensions only; not full-shape or GD&T certification.',
                 'general_tolerance_mm':general if use_general else None,'association_mm':association,
                 'comparison_mode':comparison_mode,
                 'views':selections,'checks':[c.to_dict() for c in sorted(checks,key=lambda x:x.dimension)]}
        st.session_state.update(report=payload,report_signature=run_signature)
    report=st.session_state.get('report')
    if report:
        st.subheader('3. Dimension result: '+report['result'])
        total, passed, mismatch, unresolved = st.columns(4)
        rows = report['checks']
        total.metric('Dimensions', len(rows))
        passed.metric('Nominal matches' if report['comparison_mode']=='nominal' else 'Within limits',sum(r['result']=='OK' for r in rows))
        unresolved_count = sum(r['result']!='OK' and 'cannot verify' in r['reason'].lower() for r in rows)
        mismatch.metric('Measured NG', sum(r['result']!='OK' for r in rows)-unresolved_count)
        unresolved.metric('Cannot verify', unresolved_count)
        st.caption('NG distinguishes a measured mismatch from evidence that could not be verified. Undimensioned geometry is outside this result.')
        st.caption('Result basis: '+report['comparison_mode']+'. Missing limits are shown as Not specified; no tolerance is invented.')
        st.dataframe([{'Dimension':row['dimension'],'Figure':row['view'],'Type':row['kind'],
                       'Drawing nominal (mm)':row['nominal'],'Model measurement (mm)':row['measured'],
                       'Difference (mm)':row['measured']-row['nominal'] if row['measured'] is not None and row['nominal'] is not None else None,
                       'Nominal':row.get('nominal_result','Not checked'),'Tolerance':row.get('tolerance_result','Not checked'),
                       'Result':row['result'],'Reason':row['reason']} for row in report['checks']],use_container_width=True,hide_index=True)
        with st.expander('Matched features'):
            for view_id,chosen,projection,drawing,confirmed in prepared:
                evidence=[DimensionCheck(**row) for row in report['checks'] if row['view']==view_id]
                st.write(view_id); components.html(svg_overlay(drawing,projection,evidence),height=400)
            st.json(report)
        ai_summary=render_summary_controls(report)
        output=io.StringIO(); writer=csv.DictWriter(output,fieldnames=list(report['checks'][0]))
        writer.writeheader(); writer.writerows(report['checks'])
        x,y,z=st.columns(3)
        x.download_button('Download CSV',output.getvalue().encode('utf-8-sig'),'dimension-check.csv','text/csv')
        export_report={**report,**({'ai_summary':ai_summary} if ai_summary else {})}
        y.download_button('Download JSON',json.dumps(export_report,indent=2,ensure_ascii=False),'dimension-check.json','application/json')
        z.download_button('Download PDF',pdf_report(report,ai_summary),'dimension-check.pdf','application/pdf')


def main():
    st.set_page_config(page_title=APP_NAME, layout='wide')
    header(ENGINE_VERSION)
    run,model,drawing_tab=st.tabs(['Run CAD Check / CAD照合','Inspect 3D STEP/STP / 3D確認','Inspect 2D DXF / 2D確認'])
    with run:
        run_workspace()
    with model:
        st.subheader('3D model projections / 3Dモデルの投影')
        solid=st.session_state.get('cad_solid')
        if solid is None:st.info('Select the DXF and STEP files in Run CAD Check first.')
        else:
            st.caption('Six separate orthographic views at one common scale. The sheet layout does not change measurement coordinates.')
            try:
                cache=st.session_state.projection_cache
                projections=[]
                for name in ['front','right','rear','top','left','bottom']:
                    key=('Projection',name,False)
                    if key not in cache:cache[key]=project_visible(solid,name)
                    projections.append(cache[key])
                components.html(svg_projection_sheet(projections),height=560)
            except Exception as exc:st.error(f'Cannot inspect model: {exc}')
    with drawing_tab:
        st.subheader('2D drawing figures / 2D図面の図')
        doc=st.session_state.get('cad_doc');analysis=st.session_state.get('cad_analysis')
        if doc is None:st.info('Select the DXF and STEP files in Run CAD Check first.')
        else:
            filtered=replace(analysis,entity_locations=tuple(x for x in analysis.entity_locations if x.entity_type in {'LINE','ARC','CIRCLE','LWPOLYLINE','POLYLINE','SPLINE','ELLIPSE'}))
            from app.projection import StepProjection
            for view in segment_views(filtered,gap_mm=2):
                st.caption(view.view_id+' · Drawing geometry only; dimension annotations excluded')
                try:
                    primitives=drawing_primitives(doc,set(view.entity_indexes))
                    components.html(svg_overlay(primitives,StepProjection('DXF',0,0,())),height=400)
                except Exception as exc:st.error(str(exc))

if __name__=='__main__':
    main()
