"""Authenticated, bounded CAD processing bridge for the Sites dashboard."""
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import BoundedSemaphore
from typing import Literal
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile, Depends
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from pydantic import BaseModel, Field, ConfigDict, ValidationError
from app.runtime_limits import load_runtime_limits

CAPACITY = BoundedSemaphore(2)

class ViewSetting(BaseModel):
    model_config = ConfigDict(extra='forbid',allow_inf_nan=False)
    view_id: str = Field(max_length=50)
    dimensions: list[str] = Field(default_factory=list,max_length=10000)
    mode: Literal['Projection','Section'] = 'Projection'
    source: Literal['top','front','right','bottom','rear','left'] = 'top'
    hidden: bool = False
    axis: Literal['X','Y','Z'] = 'Z'
    offset: float = 0
    rotation: Literal[0,90,180,270] = 0
    dx: float = 0
    dy: float = 0
    confirmed: bool = False

class Settings(BaseModel):
    model_config = ConfigDict(extra='forbid',allow_inf_nan=False)
    gap: float = Field(default=2,ge=0,le=100)
    excluded_layers: list[str] | None = Field(default=None,max_length=5000)
    association: float = Field(default=1,ge=.001,le=10)
    general_tolerance: float | None = Field(default=None,gt=0,le=100)
    units_confirmed: bool = False
    views: list[ViewSetting] = Field(default_factory=list,max_length=50)

@asynccontextmanager
async def lifespan(app):
    if len(os.environ.get('CAD_API_KEY','')) < 32:
        raise RuntimeError('Set CAD_API_KEY to a random secret of at least 32 characters.')
    yield

app = FastAPI(title='CAD Checker processing API',version='1.0',lifespan=lifespan,docs_url=None,redoc_url=None)
@app.middleware('http')
async def request_guard(request, call_next):
    if request.method != 'OPTIONS':
        expected = os.environ.get('CAD_API_KEY','')
        if len(expected)<32 or not secrets.compare_digest(request.headers.get('authorization',''),'Bearer '+expected):
            return JSONResponse({'detail':'Valid CAD API bearer token required.'},status_code=401)
        if request.method == 'POST':
            limits=load_runtime_limits()
            try: size=int(request.headers.get('content-length','-1'))
            except ValueError: size=-1
            if size<0: return JSONResponse({'detail':'Content-Length required.'},status_code=411)
            if size>limits.max_dxf_bytes+limits.max_step_bytes+1000000:
                return JSONResponse({'detail':'Request exceeds CAD upload limits.'},status_code=413)
    response=await call_next(request)
    response.headers['Cache-Control']='no-store'
    return response

app.add_middleware(CORSMiddleware,
    allow_origins=[o.strip() for o in os.environ.get('CAD_ALLOWED_ORIGINS','https://cad-checker-workbench.capable-creator.chatgpt.site').split(',') if o.strip()],
    allow_methods=['GET','POST'],allow_headers=['Authorization','Content-Type'])

def authorize(authorization: str = Header(default='')):
    expected = os.environ.get('CAD_API_KEY','')
    if len(expected)<32 or not secrets.compare_digest(authorization,'Bearer '+expected):
        raise HTTPException(401,'Valid CAD API bearer token required.')

@app.get('/health',dependencies=[Depends(authorize)])
def health():
    return {'status':'ok','protocol':'cad-checker-v1','operations':['analyze','preview','check']}

@app.post('/v1/{operation}',dependencies=[Depends(authorize)])
def run(operation: Literal['analyze','preview','check'], dxf: UploadFile=File(...), step: UploadFile=File(...), settings: str=Form('{}')):
    limits=load_runtime_limits()
    if len(settings)>500000: raise HTTPException(413,'Settings too large.')
    try: options=Settings.model_validate_json(settings).model_dump()
    except ValidationError: raise HTTPException(422,'Invalid CAD settings.')
    if not str(dxf.filename).lower().endswith('.dxf') or not str(step.filename).lower().endswith(('.step','.stp')):
        raise HTTPException(422,'Expected a DXF drawing and STEP/STP model.')
    if not CAPACITY.acquire(blocking=False): raise HTTPException(429,'CAD engine busy. Try again shortly.')
    try:
        drawing=dxf.file.read(limits.max_dxf_bytes+1); model=step.file.read(limits.max_step_bytes+1)
        if not drawing or not model or len(drawing)>limits.max_dxf_bytes or len(model)>limits.max_step_bytes:
            raise HTTPException(413,'Empty CAD file or configured upload limit exceeded.')
        with TemporaryDirectory(prefix='cad-api-') as directory:
            folder=Path(directory)
            (folder/'drawing.dxf').write_bytes(drawing); (folder/'model.step').write_bytes(model)
            names={'drawing':Path(dxf.filename).name[:255],'model':Path(step.filename).name[:255]}
            (folder/'request.json').write_text(json.dumps({'operation':operation,'settings':options,'names':names}))
            try:
                subprocess.run([sys.executable,'-m','app.cad_service',str(folder)],cwd=Path(__file__).resolve().parents[1],
                    timeout=limits.cad_processing_timeout_seconds,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            except subprocess.TimeoutExpired: raise HTTPException(504,'CAD processing timed out. Reduce model complexity.')
            except subprocess.CalledProcessError: raise HTTPException(422,'CAD worker could not process these files.')
            result=json.loads((folder/'response.json').read_text())
            if 'error' in result: raise HTTPException(422,result['error'])
            return result['data']
    finally:
        dxf.file.close(); step.file.close(); CAPACITY.release()
