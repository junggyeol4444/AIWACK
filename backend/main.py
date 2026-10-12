"""Locally runnable prototype: startup, DB migrations and manual persistence check.

No AI employee or automatic company operation is claimed at this stage.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import insert, select, update
from sqlalchemy.exc import SQLAlchemyError
from backend.core.config import get_settings
from backend.database.connection import (
    build_engine, initialize_database, database_status, system_metadata,
)

settings = get_settings()
CHECKPOINT_KEY = "local_manual_test"


@asynccontextmanager
async def lifespan(application: FastAPI):
    engine = build_engine(settings.database_url)
    try:
        initialize_database(engine)
        application.state.database_engine = engine
        yield
    finally:
        engine.dispose()


app = FastAPI(lifespan=lifespan, title=settings.app_name, version=settings.version,
              description="Prototype diagnostics only. AI employees are not yet implemented.")


@app.get("/")
def root() -> dict[str, str]:
    return {"project": settings.app_name, "status": "development", "docs": "/docs", "diagnostics": "/diagnostics"}


@app.get("/health")
@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok", "component": "api",
            "environment": settings.environment, "version": settings.version}


def _engine(request: Request):
    engine = getattr(request.app.state, "database_engine", None)
    if engine is None:
        raise HTTPException(status_code=503, detail="Database engine not initialized")
    return engine


@app.get("/api/v1/database/health")
def database_health(request: Request) -> dict[str, str]:
    try:
        return database_status(_engine(request))
    except (SQLAlchemyError, RuntimeError):
        raise HTTPException(status_code=503, detail="Database connection unavailable") from None


class CheckpointPayload(BaseModel):
    message: str = Field(min_length=1, max_length=120)


@app.get("/api/v1/diagnostics/checkpoint")
def read_checkpoint(request: Request) -> dict[str, str | None]:
    with _engine(request).connect() as connection:
        value = connection.execute(
            select(system_metadata.c.value).where(system_metadata.c.key == CHECKPOINT_KEY)
        ).scalar_one_or_none()
    return {"message": value}


@app.post("/api/v1/diagnostics/checkpoint")
def write_checkpoint(payload: CheckpointPayload, request: Request) -> dict[str, str]:
    """Single-user local probe; not a production/user-authenticated API."""
    with _engine(request).begin() as connection:
        exists = connection.execute(
            select(system_metadata.c.id).where(system_metadata.c.key == CHECKPOINT_KEY)
        ).scalar_one_or_none()
        if exists is None:
            connection.execute(insert(system_metadata).values(key=CHECKPOINT_KEY, value=payload.message))
        else:
            connection.execute(update(system_metadata).where(system_metadata.c.key == CHECKPOINT_KEY)
                               .values(value=payload.message))
    return {"message": payload.message, "status": "saved"}


DIAGNOSTICS_HTML = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI Autonomous Company 로컬 진단</title>
<style>body{font-family:system-ui,'Malgun Gothic',sans-serif;background:#f4f6fa;color:#1e293b;margin:0}
main{max-width:760px;margin:48px auto;padding:24px}article{background:white;border-radius:16px;padding:24px;
box-shadow:0 6px 24px #18243a12;margin-bottom:18px}h1{font-size:26px}label{display:block;margin:14px 0 6px}
input{box-sizing:border-box;width:100%;padding:12px;border:1px solid #b9c4d2;border-radius:8px}
button{margin-top:12px;padding:10px 18px;background:#164de4;color:white;border:0;border-radius:8px;cursor:pointer}
small{color:#64748b}pre{white-space:pre-wrap;background:#edf2f9;padding:14px;border-radius:10px}
</style></head><body><main><h1>AI Autonomous Company</h1>
<p>로컬 실행·저장소 진단 페이지 — <strong>실제 AI 회사 기능은 아직 개발 중입니다.</strong></p>
<article><h2>서버 및 데이터베이스 연결</h2><pre id="status">확인 중...</pre>
<button id="refresh">상태 다시 확인</button></article>
<article><h2>저장·재시작 실사용 검사</h2>
<p>아래 메시지를 저장한 후 프로그램을 종료하고 다시 시작해서 같은 내용이 나타나는지 확인하세요.</p>
<label for="message">검증할 메시지 (개인정보·비밀번호 입력 금지)</label>
<input id="message" maxlength="120" placeholder="예: 내 PC에서 저장 테스트 성공">
<button id="save">메시지 저장</button><p id="saved" role="status"></p>
<small>로컬 진단 전용. 사용자 인증이 없어 외부 네트워크에 공개해서는 안 됩니다.</small></article>
<article><h2>현재 구현 범위</h2><p>서버 실행 / 버전 관리형 DB 초기화 / 로컬 메시지 저장·조회.</p>
<p>총괄 AI, 직원 AI, 사업 실행, 실제 매출 기능은 아직 작동하지 않습니다.</p>
<p><a href="/docs">OpenAPI 개발자 화면</a></p></article>
</main><script>
const $=id=>document.getElementById(id);
async function readJSON(url,options){const r=await fetch(url,options);if(!r.ok)throw Error('HTTP '+r.status);return r.json()}
async function refresh(){try{const a=await readJSON('/api/v1/health');const b=await readJSON('/api/v1/database/health');const c=await readJSON('/api/v1/diagnostics/checkpoint');
$('status').textContent='API: '+a.status+' / 버전: '+a.version+'\\nDB: '+b.status+' / 종류: '+b.dialect+' / 마이그레이션: '+b.revision;
$('message').value=c.message||'';}catch(e){$('status').textContent='실패: '+e.message}}
$('refresh').addEventListener('click',refresh);
$('save').addEventListener('click',async()=>{try{const message=$('message').value.trim();
const data=await readJSON('/api/v1/diagnostics/checkpoint',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message})});
$('saved').textContent='저장 완료: '+data.message;}catch(e){$('saved').textContent='저장 실패: '+e.message}});
refresh();
</script></body></html>"""


@app.get("/diagnostics", response_class=HTMLResponse, include_in_schema=False)
def diagnostics():
    return HTMLResponse(DIAGNOSTICS_HTML)
