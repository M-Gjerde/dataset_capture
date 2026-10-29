"""Local dashboard gateway: supervised SSH tunnel and an independent Pi heartbeat."""
import argparse
import asyncio
import ipaddress
import json
import re
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from starlette.middleware.trustedhost import TrustedHostMiddleware

STATIC = Path(__file__).parent / 'static'
SAVE_LOCK = threading.Lock()


class LocalSave(BaseModel):
    capture_id: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_-]{0,95}$')
    destination: str = Field(min_length=1, max_length=4096)


def save_local_capture(connection, request):
    """Stage one archive, verify every checksum, then publish without overwriting."""
    from .host import verify_capture
    destination = Path(request.destination).expanduser()
    if not destination.is_absolute():
        raise ValueError('Enter an absolute desktop folder path.')
    with SAVE_LOCK:
        state = connection.snapshot()
        if state['state'] != 'online':
            raise ValueError('Reconnect the Pi before transferring this capture.')
        code, body, _ = connection.forward('GET', 'status', b'', '')
        if code != 200:
            raise ValueError('Could not read the Pi capture folder.')
        source = json.loads(body)['output']
        if not re.fullmatch(r'/[A-Za-z0-9_./-]+', source) or '..' in source.split('/'):
            raise ValueError('Unsupported Pi capture folder.')
        target = ConnectionTarget(**state['target'])
        destination.mkdir(parents=True, exist_ok=True)
        destination = destination.resolve()
        final = destination / request.capture_id
        staging = Path(tempfile.mkdtemp(prefix='.partial-transfer-', dir=destination))
        archive = staging / request.capture_id
        archive.mkdir()
        try:
            subprocess.run([
                'rsync', '-rt', '--checksum', '-e',
                'ssh -o BatchMode=yes -o ConnectTimeout=8 -o ServerAliveInterval=5 -o ServerAliveCountMax=3',
                '--', f'{target.username}@{target.address}:{source.rstrip("/")}/{request.capture_id}/',
                str(archive) + '/',
            ], check=True, capture_output=True, timeout=120)
            metadata = verify_capture(archive)
            if final.exists() or final.is_symlink():
                if final.is_symlink() or not final.is_dir():
                    raise ValueError('Destination already exists; choose a different folder.')
                existing = verify_capture(final)
                if existing != metadata:
                    raise ValueError('A different capture already uses this ID in the destination. Nothing was overwritten.')
            else:
                archive.rename(final)
            return {'capture_id': request.capture_id, 'path': str(final), 'verified': True}
        finally:
            shutil.rmtree(staging)


def connection_failure(stderr):
    if 'connect failed: Connection refused' in stderr:
        return 'service_unavailable', 'SSH connected, but the Pi camera service is not running on port 8000. Start dataset-capture on the Pi.'
    if 'Permission denied' in stderr:
        return 'authentication_failed', 'SSH sign-in failed. Check the Pi username and the desktop SSH key.'
    if 'Host key verification failed' in stderr or 'REMOTE HOST IDENTIFICATION HAS CHANGED' in stderr:
        return 'authentication_failed', 'SSH host verification failed. Check the Pi identity in your terminal.'
    return 'reconnecting', 'Waiting for the Pi connection. Retrying automatically.'


class ConnectionTarget(BaseModel):
    address: str = '10.42.0.141'
    username: str = 'cameramodule'

    @field_validator('address')
    @classmethod
    def local_address(cls, value):
        address = ipaddress.IPv4Address(value)
        if address not in ipaddress.IPv4Network('10.42.0.0/24') or address in (
                ipaddress.IPv4Address('10.42.0.0'), ipaddress.IPv4Address('10.42.0.1'), ipaddress.IPv4Address('10.42.0.255')):
            raise ValueError('Use the Pi address on the DatasetCapture hotspot (10.42.0.x)')
        return str(address)

    @field_validator('username')
    @classmethod
    def safe_username(cls, value):
        if not re.fullmatch(r'[a-z_][a-z0-9_-]{0,31}', value):
            raise ValueError('Enter a valid Pi username')
        return value


class PiConnection:
    def __init__(self, target=None):
        self.target = target or ConnectionTarget()
        self.lock = threading.RLock()
        self.process = None
        self.port = None
        self.desired = False
        self.state = 'disconnected'
        self.message = 'Connect your Raspberry Pi to begin.'
        self.last_seen = None
        self.latency_ms = None
        self.heartbeat = None
        self.stop = threading.Event()
        self.thread = None
        self.ssh_error = ''
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def start(self):
        self.thread = threading.Thread(target=self._monitor, daemon=True, name='pi-heartbeat')
        self.thread.start()

    def close(self):
        self.stop.set()
        self.disconnect()
        if self.thread:
            self.thread.join(timeout=6)

    def _terminate(self):
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
            self.process = None
        self.port = None

    def connect(self, target):
        with self.lock:
            self._terminate()
            self.target = target
            self.desired = True
            self.last_seen = self.heartbeat = self.latency_ms = None
            self.ssh_error = ''
            self.state, self.message = 'connecting', 'Connecting to your Pi…'
        return self.snapshot()

    def disconnect(self):
        with self.lock:
            self.desired = False
            self._terminate()
            self.state, self.message = 'disconnected', 'Disconnected. Files and any active capture series remain on the Pi.'
        return self.snapshot()

    def snapshot(self):
        with self.lock:
            age = None if self.last_seen is None else time.monotonic() - self.last_seen
            state = self.state
            if state == 'online' and (age is None or age > 6):
                state = 'reconnecting'
            return {'mode':'desktop', 'state':state, 'target':self.target.model_dump(),
                    'message':self.message, 'last_seen_seconds':age, 'latency_ms':self.latency_ms,
                    'pi':self.heartbeat, 'automatic_reconnect':self.desired}

    def _launch(self):
        # Let the OS choose a loopback-only port. SSH's ExitOnForwardFailure
        # rejects a race with another listener instead of silently using it.
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            self.port = sock.getsockname()[1]
        self.process = subprocess.Popen([
            'ssh', '-N', '-T', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
            '-o', 'ExitOnForwardFailure=yes', '-o', 'ConnectTimeout=6',
            '-o', 'ServerAliveInterval=3', '-o', 'ServerAliveCountMax=2',
            '-L', f'127.0.0.1:{self.port}:127.0.0.1:8000',
            f'{self.target.username}@{self.target.address}'], stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        threading.Thread(target=self._read_ssh_errors, args=(self.process,), daemon=True).start()

    def _read_ssh_errors(self, process):
        try:
            for line in process.stderr:
                with self.lock:
                    if self.process is process:
                        self.ssh_error = line.strip()[:1000]
        finally:
            process.stderr.close()

    def _monitor(self):
        while not self.stop.is_set():
            with self.lock:
                if self.desired:
                    if self.process is None or self.process.poll() is not None:
                        self._terminate()
                        try:
                            self._launch()
                            self.state, self.message = 'connecting', 'Connecting securely to the Pi…'
                        except OSError:
                            self.state, self.message = 'reconnecting', 'SSH could not start. Check that OpenSSH is installed.'
                    port, process = self.port, self.process
                else:
                    port = process = None
            if port and process:
                start = time.monotonic()
                try:
                    with self.opener.open(f'http://127.0.0.1:{port}/api/heartbeat', timeout=2) as response:
                        beat = json.load(response)
                    if beat.get('service') != 'dataset-capture' or not beat.get('instance_id'):
                        raise ValueError('Unexpected service')
                    with self.lock:
                        if self.process is process and self.desired:
                            self.last_seen = time.monotonic()
                            self.latency_ms = round((self.last_seen-start)*1000)
                            self.heartbeat = beat
                            self.ssh_error = ''
                            self.state, self.message = 'online', 'Pi connected. Connection checked every two seconds.'
                except (OSError, ValueError, urllib.error.URLError):
                    with self.lock:
                        if self.process is process and self.desired:
                            self.state, self.message = connection_failure(self.ssh_error)
            self.stop.wait(2)

    def forward(self, method, path, body, query):
        with self.lock:
            if self.snapshot()['state'] != 'online' or self.port is None:
                return 503, b'{"detail":"Pi connection unavailable. Reconnect before continuing."}', 'application/json'
            port = self.port
        request = urllib.request.Request(f'http://127.0.0.1:{port}/api/{path}' + ('?' + query if query else ''),
                                         data=body if method != 'GET' else None, method=method,
                                         headers={'Content-Type':'application/json'})
        try:
            # Never retry mutations here: a lost response may follow a saved frame.
            with self.opener.open(request, timeout=120 if path == 'captures' else 12) as response:
                return response.status, response.read(), response.headers.get('Content-Type','application/json')
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read(), exc.headers.get('Content-Type','application/json')
        except (OSError, urllib.error.URLError):
            return 503, b'{"detail":"Connection interrupted. A capture may still have saved; retry the same capture ID."}', 'application/json'


def create_desktop_app(connection):
    @asynccontextmanager
    async def lifespan(app):
        connection.start()
        yield
        await asyncio.to_thread(connection.close)

    app = FastAPI(title='Dataset Capture desktop', lifespan=lifespan)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['localhost','127.0.0.1','[::1]','testserver'])

    @app.middleware('http')
    async def protect(request: Request, call_next):
        if request.method not in ('GET','HEAD','OPTIONS'):
            origin = request.headers.get('origin')
            if origin and origin != str(request.base_url).rstrip('/'):
                return JSONResponse({'detail':'Cross-origin writes are disabled'},status_code=403)
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    @app.get('/')
    def index(): return FileResponse(STATIC/'index.html')

    @app.get('/api/connection')
    def status(): return connection.snapshot()

    @app.post('/api/connection')
    def connect(target: ConnectionTarget): return connection.connect(target)

    @app.delete('/api/connection')
    def disconnect(): return connection.disconnect()

    @app.get('/api/protocol')
    def protocol(): return FileResponse(Path(__file__).parent/'protocol.md',media_type='text/plain; charset=utf-8')

    @app.get('/api/save-location')
    def save_location():
        return {'destination': str(Path.cwd() / 'captures')}

    @app.post('/api/save-local')
    def save_local(body: LocalSave):
        try:
            return save_local_capture(connection, body)
        except (ValueError, OSError, subprocess.SubprocessError) as exc:
            detail = str(exc) if isinstance(exc, ValueError) else 'Transfer failed. The Pi original is retained; retry the transfer.'
            return JSONResponse({'detail': detail}, status_code=409 if isinstance(exc, ValueError) else 503)

    @app.api_route('/api/{path:path}',methods=['GET','POST','PUT'])
    async def forward(path: str, request: Request):
        allowed = {'GET': {'status','settings','setup','measurement-state','raw','raw-preview.jpg','preview.jpg','series'},
                   'POST': {'connect','captures','chunks/enable','series','series/cancel'},
                   'PUT': {'setup','preview'}}
        if path not in allowed[request.method] and not (request.method == 'PUT' and re.fullmatch(r'settings/[A-Za-z0-9_]+',path)):
            return JSONResponse({'detail':'Unknown operation'}, status_code=404)
        status, body, content_type = await asyncio.to_thread(connection.forward, request.method, path,
                                                           await request.body(), request.url.query)
        return Response(body,status_code=status,headers={'Content-Type':content_type})

    app.mount('/static',StaticFiles(directory=STATIC),name='static')
    return app


def main():
    import uvicorn
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8001)
    parser.add_argument('--pi',default='10.42.0.141')
    parser.add_argument('--username',default='cameramodule')
    args = parser.parse_args()
    connection = PiConnection(ConnectionTarget(address=args.pi,username=args.username))
    uvicorn.run(create_desktop_app(connection),host='127.0.0.1',port=args.port,timeout_graceful_shutdown=5)


if __name__ == '__main__': main()
