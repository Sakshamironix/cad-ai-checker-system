import copy
import json
import socket
import ssl
from urllib.error import URLError
import pytest
from app.inspection_summary import (SummaryError,generate_summary,evidence_for_summary,
                                    provider_configuration,report_fingerprint)

@pytest.fixture
def report():
    return {'engine':'0.19.2-geometry','generated_at':'2026-11-06','comparison_mode':'nominal',
            'scope':'Assigned dimensions only','result':'NG','drawing':'private.dxf','model':'private.step',
            'drawing_sha256':'private-hash','model_sha256':'private-model-hash',
            'checks':[{'dimension':'DIM-001','view':'VIEW-01','kind':'linear','nominal':2.5,'measured':5.,
                       'lower':None,'upper':None,'result':'NG','reason':'Measured mismatch',
                       'nominal_result':'Mismatch','tolerance_result':'Not specified','tolerance_source':'Unavailable','features':[]}]}


def response(result='NG'):
    return {'result':result,'overview':'The assigned dimension differs from the model.',
            'overview_ja':'図面の寸法とモデルの測定値が異なります。',
            'findings':[{'dimension':'DIM-001','result':result,'explanation':'Review the stated dimension against the measured feature.',
                         'explanation_ja':'図面寸法と測定箇所を確認してください。'}],
            'next_steps':['Confirm the intended drawing dimension.'],
            'next_steps_ja':['意図した図面寸法を確認してください。']}


@pytest.mark.parametrize('provider',['Gemini','OpenAI','Open-source / compatible API'])
def test_summary_uses_final_evidence_excludes_files_and_keeps_report_immutable(report,provider,monkeypatch):
    monkeypatch.setenv('CAD_SUMMARY_BASE_URL','http://localhost:11434/v1')
    before=copy.deepcopy(report);calls=[]
    def transport(url,headers,payload):
        calls.append((url,headers,payload));assert 'private.' not in json.dumps(payload)
        assert 'private-hash' not in json.dumps(payload) and 'secret-key' not in json.dumps(payload)
        if provider=='Gemini':return {'candidates':[{'content':{'parts':[{'text':json.dumps(response())}]}}]}
        return {'choices':[{'message':{'content':json.dumps(response())}}]}
    summary=generate_summary(report,provider,'test-model','secret-key',transport=transport)
    assert len(calls)==1 and report==before and summary['result']=='NG'
    assert summary['report_fingerprint']==report_fingerprint(report)
    assert summary['overview_ja']==response()['overview_ja']
    assert 'secret-key' not in json.dumps(summary)
    if provider=='OpenAI':assert calls[0][2]['store'] is False


@pytest.mark.parametrize('change',[lambda p:p.update(result='OK'),
    lambda p:p['findings'][0].update(result='OK'),lambda p:p['findings'][0].update(dimension='DIM-999'),
    lambda p:p.update(overview=''),lambda p:p.update(next_steps='not a list'),
    lambda p:p.pop('overview_ja'),lambda p:p.update(next_steps_ja=[]),
    lambda p:p['findings'][0].pop('explanation_ja')])
def test_conflicting_or_invalid_summary_is_discarded(report,change):
    data=response();change(data)
    with pytest.raises(SummaryError):
        generate_summary(report,'OpenAI','test','test-key',transport=lambda *a:{'choices':[{'message':{'content':json.dumps(data)}}]})
    assert report['result']=='NG' and report['checks'][0]['measured']==5


def test_missing_configuration_makes_no_request(report,monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY',raising=False);monkeypatch.delenv('OPENAI_MODEL',raising=False)
    def no_request(*a):raise AssertionError('Must not call the API')
    with pytest.raises(SummaryError):generate_summary(report,'OpenAI',transport=no_request)


def test_no_credential_echo_on_provider_http_failure(monkeypatch):
    import app.inspection_summary as module
    from urllib.error import HTTPError
    class Opener:
        def open(self,*a,**kw):raise HTTPError('https://provider.invalid?key=secret',401,'secret-token',None,None)
    monkeypatch.setattr(module,'build_opener',lambda *a:Opener())
    with pytest.raises(SummaryError) as exc:module.post_json('https://provider.invalid',{}, {})
    assert '401' in str(exc.value) and 'secret' not in str(exc.value)


def test_only_server_configured_https_or_loopback_endpoints(monkeypatch):
    monkeypatch.setenv('CAD_SUMMARY_BASE_URL','http://remote.example/v1')
    with pytest.raises(SummaryError):provider_configuration('Open-source / compatible API','model')
    monkeypatch.setenv('CAD_SUMMARY_BASE_URL','https://server.example/v1')
    assert provider_configuration('Open-source / compatible API','model')[2]=='https://server.example/v1/chat/completions'


@pytest.mark.parametrize('failure,message',[
    (TimeoutError('private-timeout-detail'),'timed out'),
    (URLError(socket.gaierror('private-dns-detail')),'resolve'),
    (URLError(ssl.SSLError('private-tls-detail')),'verified HTTPS'),
    (ConnectionResetError('private-reset-detail'),'connection closed'),
])
def test_network_failures_are_distinguished_without_leaking_details(monkeypatch,failure,message):
    import app.inspection_summary as module
    class Opener:
        def open(self,*args,**kwargs):raise failure
    monkeypatch.setattr(module,'build_opener',lambda *a:Opener())
    with pytest.raises(SummaryError,match=message) as exc:
        module.post_json('https://provider.invalid',{}, {})
    assert 'private-' not in str(exc.value)


def test_gemini_allows_more_time_for_generation(report,monkeypatch):
    import app.inspection_summary as module
    def post(url,headers,payload,*,timeout_seconds):
        assert timeout_seconds>=90
        return {'candidates':[{'content':{'parts':[{'text':json.dumps(response())}]}}]}
    monkeypatch.setattr(module,'post_json',post)
    assert generate_summary(report,'Gemini','test','test-key')['result']=='NG'


def test_optional_button_no_auto_call_and_stale_summary_cleared(report,monkeypatch):
    import app.inspection_summary as module
    from streamlit.testing.v1 import AppTest
    calls=[]
    def generate(data,provider,model,api_key):
        calls.append(1)
        return {**response(),'provider':provider,'model':model,'report_fingerprint':report_fingerprint(data)}
    monkeypatch.setattr(module,'generate_summary',generate)
    app=AppTest.from_string('import streamlit as st\nfrom app.inspection_summary import render_summary_controls\nrender_summary_controls(st.session_state.report)\nst.write(st.session_state.report["result"])')
    app.session_state['report']=report
    app.run();assert not app.exception and calls==[]
    app.text_input[0].set_value('test-model');app.text_input[1].set_value('test-key');app.run()
    assert calls==[]
    app.button(key='generate_inspection_summary').click().run()
    assert not app.exception and len(calls)==1 and app.session_state['report']==report
    assert {response()['overview'],response()['overview_ja']} <= {item.value for item in app.text}
    app.run();assert len(calls)==1
    changed=copy.deepcopy(report);changed['generated_at']='new-inspection';app.session_state['report']=changed;app.run()
    assert not app.exception and 'inspection_ai_summary' not in app.session_state and len(calls)==1


def test_pdf_includes_ai_only_for_current_report(report,monkeypatch):
    from app.main import pdf_report
    from reportlab.pdfgen import canvas
    original=canvas.Canvas
    monkeypatch.setattr(canvas,'Canvas',lambda *args,**kwargs:original(*args,**{**kwargs,'pageCompression':0}))
    report={**report,'drawing_sha256':'hash','model_sha256':'hash','views':[]}
    summary={**response(),'provider':'Gemini','model':'test-model','report_fingerprint':report_fingerprint(report)}
    plain=pdf_report(report)
    included=pdf_report(report,summary)
    stale=pdf_report({**report,'generated_at':'new inspection'},summary)
    assert b'The assigned dimension differs from the model.' not in plain
    assert b'The assigned dimension differs from the model.' in included
    assert b'HeiseiKakuGo-W5' in included and b'HeiseiKakuGo-W5' not in plain
    assert b'The assigned dimension differs from the model.' not in stale
