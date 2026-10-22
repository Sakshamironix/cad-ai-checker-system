import io
import cadquery as cq
import ezdxf
import pytest
from fastapi.testclient import TestClient
from app.cad_api import app

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('CAD_API_KEY','a'*40)
    with TestClient(app) as client:
        yield client

@pytest.fixture
def files(tmp_path):
    doc=ezdxf.new();doc.units=4;m=doc.modelspace()
    for a,b in [((0,0),(80,0)),((80,0),(80,60)),((80,60),(0,60)),((0,60),(0,0))]:m.add_line(a,b)
    m.add_linear_dim(base=(0,-5),p1=(0,0),p2=(80,0),dimstyle='EZDXF',override={'dimtol':1,'dimtp':.1,'dimtm':.1}).render()
    stream=io.StringIO();doc.write(stream)
    path=tmp_path/'plate.step';cq.exporters.export(cq.Workplane('XY').box(80,60,10),str(path))
    return {'dxf':('plate.dxf',stream.getvalue().encode()),'step':('plate.step',path.read_bytes())}

AUTH={'Authorization':'Bearer '+'a'*40}

def test_auth_cors_limits(client):
    assert client.get('/health').status_code==401
    assert client.get('/health',headers=AUTH).json()['protocol']=='cad-checker-v1'
    response=client.options('/v1/analyze',headers={'Origin':'https://cad-checker-workbench.capable-creator.chatgpt.site','Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'authorization'})
    assert response.status_code==200
    assert response.headers['access-control-allow-origin']=='https://cad-checker-workbench.capable-creator.chatgpt.site'
    assert 'access-control-allow-origin' not in client.get('/health',headers={**AUTH,'Origin':'https://untrusted.example'}).headers
    assert client.post('/v1/analyze',headers={**AUTH,'Content-Length':'999999999'}).status_code==413

def test_real_geometry_roundtrip(client,files):
    import json
    analyzed=client.post('/v1/analyze',headers=AUTH,files=files)
    assert analyzed.status_code==200,analyzed.text
    data=analyzed.json();assert data['views']
    view={'view_id':data['views'][0]['view_id'],'dimensions':['DIM-001'],'mode':'Projection','source':'top','confirmed':True}
    options={'views':[view],'general_tolerance':.1}
    def request(operation):return client.post('/v1/'+operation,headers=AUTH,files=files,data={'settings':json.dumps(options)})
    preview=request('preview');assert preview.status_code==200,preview.text
    assert '<svg' in preview.json()['previews'][0]['svg']
    result=request('check');assert result.status_code==200,result.text
    assert result.json()['report']['result']=='OK'
    # Wrong STEP projection must not inherit the passing top view result.
    view['source']='right'
    result=request('check');assert result.json()['report']['result']=='NG'
    view['source']='top';view['confirmed']=False
    assert request('check').json()['report']['result']=='NG'
    # A real cut outside the solid has no usable intersection.
    view.update(mode='Section',axis='Z',offset=100)
    assert request('preview').status_code==422
    assert client.post('/v1/preview',headers=AUTH,files=files,data={'settings':'{"association": 0}'}).status_code==422
