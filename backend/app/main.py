from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import registry_store as _registry_store
from .config import APP_TITLE
from .db.session import close_db_engine, init_db_engine, init_db_schema, storage_backend_name
from .integrations import jupyterhub_integration as _jupyterhub_integration
from .services import ai_service as _ai_service
from .state import assert_legacy_state_write_blocked


def _export_module_symbols(
    module,
    *,
    deny_prefixes: tuple[str, ...] = (),
    deny_suffixes: tuple[str, ...] = (),
    deny_names: set[str] | None = None,
):
    deny_names = deny_names or set()
    for name in dir(module):
        if name.startswith("__"):
            continue
        if name in deny_names:
            continue
        if deny_prefixes and any(name.startswith(prefix) for prefix in deny_prefixes):
            continue
        if deny_suffixes and any(name.endswith(suffix) for suffix in deny_suffixes):
            continue
        globals().setdefault(name, getattr(module, name))


_export_module_symbols(
    _registry_store,
    deny_prefixes=("_load_", "_save_"),
    deny_suffixes=("_db",),
)
_export_module_symbols(
    _jupyterhub_integration,
    deny_suffixes=("_db",),
)
_export_module_symbols(
    _ai_service,
    deny_prefixes=("_load_", "_save_"),
    deny_suffixes=("_db",),
)

app = FastAPI(title=APP_TITLE)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    """应用启动时仅初始化数据库连接和表结构。"""
    assert_legacy_state_write_blocked()
    backend_mode = storage_backend_name()
    if backend_mode != "postgres":
        raise RuntimeError(f"Unsupported storage backend: {backend_mode!r}. Only 'postgres' is allowed.")

    pg_ok = await init_db_engine(force=True)
    if not pg_ok:
        raise RuntimeError("PostgreSQL initialization failed. Service exits without JSON fallback.")

    await init_db_schema()


@app.on_event("shutdown")
async def shutdown_event():
    await close_db_engine()


from .api.v1.router import router as api_v1_router

app.include_router(api_v1_router, prefix="")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
