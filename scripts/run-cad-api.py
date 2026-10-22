#!/usr/bin/env python
"""Start one authenticated CAD API on fixed port 8000 in Codespaces."""
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
LOGS=ROOT/'.logs'

def main():
    LOGS.mkdir(exist_ok=True)
    token_file=LOGS/'cad-api-key'
    if not token_file.exists():
        with open(token_file,'x',opener=lambda path,flags:os.open(path,flags,0o600)) as stream:
            stream.write(secrets.token_urlsafe(48))
    token=token_file.read_text().strip()
    if len(token)<32: raise RuntimeError('CAD API key file is invalid. Restore a valid key before starting.')
    url='http://127.0.0.1:8000/health'
    def healthy():
        try:
            request=urllib.request.Request(url,headers={'Authorization':'Bearer '+token})
            with urllib.request.urlopen(request,timeout=2) as response:
                return json.load(response).get('protocol')=='cad-checker-v1'
        except (OSError,ValueError): return False
    if healthy():
        print('CAD API already responds on port 8000.');return
    with socket.socket() as sock:
        if sock.connect_ex(('127.0.0.1',8000))==0:
            raise RuntimeError('Port 8000 is occupied by another service. No process was stopped.')
    environment={**os.environ,'CAD_API_KEY':token,
        'CAD_ALLOWED_ORIGINS':'https://cad-checker-workbench.capable-creator.chatgpt.site'}
    with (LOGS/'cad-api.log').open('ab') as log:
        process=subprocess.Popen([sys.executable,'-m','uvicorn','app.cad_api:app','--host','0.0.0.0',
            '--port','8000','--workers','1','--limit-concurrency','8'],cwd=ROOT,env=environment,
            stdout=log,stderr=log,stdin=subprocess.DEVNULL,start_new_session=True)
    (LOGS/'cad-api.pid').write_text(str(process.pid))
    for attempt in range(30):
        if healthy():
            print('CAD API responds on port 8000. The access token is stored only in .logs/cad-api-key.')
            print('Use the actual Codespaces Ports address after configuring its visibility.');return
        if process.poll() is not None:break
        time.sleep(.5)
    raise RuntimeError('CAD API did not start. See .logs/cad-api.log.')

if __name__=='__main__': main()
