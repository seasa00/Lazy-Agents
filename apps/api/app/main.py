"""Local-only HTTP adapters; backend service and runner own workflow rules."""
from contextlib import asynccontextmanager
import asyncio
import os
from typing import Literal
from urllib.parse import urlsplit
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
from app.api.schemas import AgentSettings, Command, CommandAcknowledgement, CreateProject, ProjectSnapshot
from app.api.service import ControlService, public
from app.api.events import event_stream
from app.persistence.sqlite import SQLiteStateStore
from app.persistence.store import NotFoundError, StoreError, VersionConflictError
from app.persistence.models import ArtifactIntegrityError


def offline_runner(store, project_id, run_id):
    from app.dev.workflow import ScriptedWorkflowProvider
    from app.orchestration.runner import WorkflowRunner
    return WorkflowRunner(store, project_id, run_id, ScriptedWorkflowProvider())


def create_app(*, store=None, runner_factory=offline_runner):
    @asynccontextmanager
    async def lifespan(app):
        backend = store if store is not None else SQLiteStateStore(os.environ.get('AI_OFFICE_DB', 'data/state.db'))
        app.state.service = ControlService(backend, runner_factory)
        app.state.service.startup()
        try:
            yield
        finally:
            await asyncio.to_thread(app.state.service.shutdown)
            if store is None:
                backend.close()

    app = FastAPI(title='AI Office local control surface', version='1', lifespan=lifespan)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['localhost', '127.0.0.1', '[::1]'])

    @app.middleware('http')
    async def local_access(request, call_next):
        origin = request.headers.get('origin')
        if origin:
            parsed = urlsplit(origin)
            if parsed.scheme != 'http' or parsed.netloc != request.headers.get('host') or parsed.path:
                return JSONResponse({'detail': 'origin denied'}, status_code=403)
        if request.method not in {'GET', 'HEAD', 'OPTIONS'} and request.headers.get('sec-fetch-site') in {'cross-site', 'same-site'}:
            return JSONResponse({'detail': 'cross-site mutation denied'}, status_code=403)
        return await call_next(request)

    @app.exception_handler(RequestValidationError)
    async def validation(request, exc):
        # Pydantic's default error includes rejected input values, including secrets.
        return JSONResponse({'detail': 'Invalid request fields; check the API contract'}, status_code=422)

    @app.exception_handler(VersionConflictError)
    async def conflict(request, exc):
        return JSONResponse(CommandAcknowledgement(command_id=request.headers.get('idempotency-key', ''),
            status='rejected', project_id=request.path_params.get('project_id', 'create'),
            run_id=request.path_params.get('run_id'), error=str(exc)).model_dump(), status_code=409)

    @app.exception_handler(NotFoundError)
    @app.exception_handler(KeyError)
    async def missing(request, exc):
        return JSONResponse({'detail': 'record not found'}, status_code=404)

    @app.exception_handler(ArtifactIntegrityError)
    async def integrity(request, exc):
        return JSONResponse({'detail': 'artifact integrity failure; inspect recovery'}, status_code=409)

    @app.exception_handler(ValueError)
    @app.exception_handler(StoreError)
    async def invalid(request, exc):
        return JSONResponse({'detail': 'backend state or policy rejected request'}, status_code=400)

    def service(request):
        return request.app.state.service

    def key(value):
        if not value.strip() or len(value) > 200 or any(ord(c) < 33 or ord(c) > 126 for c in value):
            raise HTTPException(422, 'invalid Idempotency-Key')
        return value

    @app.post('/projects', response_model=CommandAcknowledgement)
    def create(body: CreateProject, request: Request, idempotency_key: str = Header()):
        return service(request).create(body, key(idempotency_key))

    @app.get('/projects')
    def projects(request: Request):
        return public(service(request).store.list_projects())

    @app.get('/projects/{project_id}', response_model=ProjectSnapshot)
    @app.get('/projects/{project_id}/snapshot', response_model=ProjectSnapshot)
    def snapshot(project_id: str, request: Request):
        return service(request).snapshot(project_id)

    @app.get('/projects/{project_id}/settings')
    def settings(project_id: str, request: Request):
        return service(request).settings(project_id)

    @app.post('/projects/{project_id}/settings', response_model=CommandAcknowledgement)
    def configure(project_id: str, body: AgentSettings, request: Request, idempotency_key: str = Header()):
        return service(request).configure(project_id, body, key(idempotency_key))

    @app.get('/projects/{project_id}/runs/{run_id}/inspection')
    def inspection(project_id: str, run_id: str, request: Request):
        return service(request).inspection(project_id, run_id)

    @app.post('/projects/{project_id}/plan', response_model=CommandAcknowledgement)
    def plan(project_id: str, body: Command, request: Request, idempotency_key: str = Header()):
        return service(request).command(project_id, None, 'plan', body, key(idempotency_key))

    @app.post('/projects/{project_id}/runs/{run_id}/{action}', response_model=CommandAcknowledgement)
    def command(project_id: str, run_id: str,
                action: Literal['approve', 'start', 'pause', 'resume', 'cancel', 'permission', 'recovery'],
                body: Command, request: Request, idempotency_key: str = Header()):
        return service(request).command(project_id, run_id, action, body, key(idempotency_key))

    @app.get('/projects/{project_id}/runs/{run_id}/{kind}')
    def read(project_id: str, run_id: str,
             kind: Literal['tasks', 'reviews', 'evidence', 'usage', 'permissions', 'recovery'], request: Request):
        return service(request).read(project_id, run_id, kind)

    @app.get('/projects/{project_id}/runs/{run_id}/artifacts/{submission_id}')
    def artifact(project_id: str, run_id: str, submission_id: str, path: str, request: Request):
        return service(request).artifact(project_id, run_id, submission_id, path)

    @app.get('/projects/{project_id}/events')
    def events(project_id: str, request: Request, after: int = 0, last_event_id: str | None = Header(default=None)):
        backend = service(request)
        backend.store.get_project(project_id)
        try:
            cursor = int(last_event_id) if last_event_id is not None else after
        except ValueError:
            raise HTTPException(409, 'invalid cursor; fetch snapshot')
        if cursor < 0 or not backend.store.valid_cursor(project_id, cursor):
            raise HTTPException(409, 'unavailable cursor; fetch snapshot')
        return StreamingResponse(event_stream(backend, project_id, cursor, request.is_disconnected),
            media_type='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

    return app


app = create_app()
