"""
Servidor FastAPI del Explorador de Carpetas
===========================================

Expone el árbol N-ario (file_explorer.py) por HTTP y sirve la interfaz web/app.html.

ALTO RENDIMIENTO
* Carga perezosa: /api/children devuelve solo una PÁGINA de hijos (el navegador nunca
  recibe el árbol completo). El orden y las estadísticas se cachean por versión.
* Escaneo de carpetas reales en un HILO de fondo, con progreso, cancelación y límites
  (max_nodes, max_depth). El árbol nuevo se construye aparte y se intercambia de golpe.
* Recorridos iterativos (pila): sin límite de profundidad por recursión.

TOLERANCIA A FALLOS
* Un solo RLock protege el árbol; los endpoints son síncronos (threadpool de FastAPI).
* Escaneo: errores de permisos/E-S se cuentan y se omiten; si el escaneo falla o se
  cancela, el árbol vivo NO se toca.
* Persistencia atómica (archivo temporal + fsync + os.replace) con copia .bak;
  autoguardado periódico y guardado final al apagar; al arrancar, si el snapshot está
  corrupto se usa el .bak, y si ambos fallan se parte de un árbol limpio.
* Errores del dominio -> códigos HTTP claros (404/409/400); un fallo inesperado
  devuelve 500 sin tumbar el servidor.

CONFIGURACIÓN (variables de entorno)
EXPLORER_DATA_DIR (def. ./data) · EXPLORER_HOST (def. 127.0.0.1) · EXPLORER_PORT (8000)
EXPLORER_AUTOSAVE_SECONDS (5) · EXPLORER_ALLOWED_ROOT (limita qué carpetas se pueden escanear)
"""
import fnmatch
import json
import logging
import os
import threading
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from file_explorer import (
    DuplicateNameError, ExplorerError, FileExplorer, FSNode, NodeKind,
    NotAFolderError, PathNotFoundError,
)

LOG = logging.getLogger("explorer")
WEB_DIR = Path(__file__).resolve().parent.parent / "web"


# ----------------------------------------------------------------------------
# Modelos de petición
# ----------------------------------------------------------------------------
class CreateReq(BaseModel):
    path: str
    size: int = Field(0, ge=0)
    parents: bool = False


class RenameReq(BaseModel):
    path: str
    new_name: str


class MoveReq(BaseModel):
    path: str
    dest: str


class ScanReq(BaseModel):
    directory: str
    max_depth: Optional[int] = Field(None, ge=0, le=10_000)
    max_nodes: int = Field(2_000_000, ge=1, le=50_000_000)


# ----------------------------------------------------------------------------
# Trabajos de escaneo
# ----------------------------------------------------------------------------
class ScanJob:
    def __init__(self, directory: str, max_depth: Optional[int], max_nodes: int):
        self.id = uuid.uuid4().hex[:12]
        self.directory, self.max_depth, self.max_nodes = directory, max_depth, max_nodes
        self.status = "running"  # running | done | cancelled | failed
        self.nodes = 0
        self.errors = 0
        self.truncated = False
        self.message = ""
        self.cancel = threading.Event()
        self.started = time.time()
        self.finished: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        end = self.finished or time.time()
        return {
            "id": self.id, "status": self.status, "directory": self.directory,
            "nodes": self.nodes, "errors": self.errors, "truncated": self.truncated,
            "message": self.message, "seconds": round(end - self.started, 2),
        }


# ----------------------------------------------------------------------------
# Almacén: árbol + bloqueo + caché + persistencia
# ----------------------------------------------------------------------------
class Store:
    CACHE_MAX = 512

    def __init__(self, data_dir: Path):
        self.lock = threading.RLock()
        data_dir.mkdir(parents=True, exist_ok=True)
        self.path = data_dir / "snapshot.json"
        self.bak = data_dir / "snapshot.json.bak"
        self.version = 0
        self.dirty = False
        self.last_saved: Optional[float] = None
        self._cache: Dict[Any, Any] = {}
        self.jobs: Dict[str, ScanJob] = {}
        self.ex = self._load() or self._demo()

    # ---- árbol inicial ----
    @staticmethod
    def _demo() -> FileExplorer:
        ex = FileExplorer("my-project")
        ex.add_file("/my-project/README.md", 1200)
        ex.add_file("/my-project/src/index.py", 2048, parents=True)
        ex.add_file("/my-project/assets/style.css", 512, parents=True)
        return ex

    # ---- acceso protegido ----
    def run(self, fn: Callable[[FileExplorer], Any], mutate: bool = False) -> Any:
        with self.lock:
            result = fn(self.ex)
            if mutate:
                self._bump()
            return result

    def _bump(self) -> None:
        self.version += 1
        self.dirty = True
        self._cache.clear()

    def cached(self, key: Any, build: Callable[[], Any]) -> Any:
        """Caché válida hasta la siguiente mutación. Llamar con el lock tomado."""
        if key not in self._cache:
            if len(self._cache) >= self.CACHE_MAX:
                self._cache.clear()
            self._cache[key] = build()
        return self._cache[key]

    def swap(self, ex: FileExplorer) -> None:
        with self.lock:
            self.ex = ex
            self._bump()

    # ---- persistencia (formato plano: sin recursión, tolera árboles profundos) ----
    def _rows(self) -> List[list]:
        idx: Dict[int, int] = {}
        rows = []
        for i, n in enumerate(self.ex.walk()):
            idx[id(n)] = i
            rows.append([idx[id(n.parent)] if n.parent else -1, n.name, int(n.is_file), n.size])
        return rows

    @staticmethod
    def _rebuild(rows: List[list]) -> FileExplorer:
        ex = FileExplorer(rows[0][1])
        nodes = [ex.root]
        for parent, name, is_file, size in rows[1:]:
            node = FSNode(name, NodeKind.FILE if is_file else NodeKind.FOLDER,
                          size=size, parent=nodes[parent])
            nodes[parent].children.append(node)
            nodes.append(node)
        ex.validate()
        return ex

    def save(self, force: bool = False) -> bool:
        with self.lock:
            if not (self.dirty or force):
                return False
            rows, self.dirty = self._rows(), False  # copia rápida bajo lock
        tmp = self.path.with_suffix(".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"format": 1, "rows": rows}, f, separators=(",", ":"))
                f.flush()
                os.fsync(f.fileno())
            if self.path.exists():
                os.replace(self.path, self.bak)  # conserva el último bueno
            os.replace(tmp, self.path)
            self.last_saved = time.time()
            return True
        except OSError:
            LOG.exception("no se pudo guardar el snapshot")
            with self.lock:
                self.dirty = True  # se reintentará en el siguiente ciclo
            return False

    def _load(self) -> Optional[FileExplorer]:
        for p in (self.path, self.bak):
            if not p.exists():
                continue
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                return self._rebuild(data["rows"])
            except Exception:  # corrupto: probar con el respaldo
                LOG.warning("snapshot ilegible: %s", p, exc_info=True)
        return None

    # ---- escaneo de carpetas reales (hilo de fondo) ----
    def start_scan(self, job: ScanJob) -> None:
        self.jobs[job.id] = job
        for old in list(self.jobs)[:-20]:  # conserva solo los 20 últimos
            self.jobs.pop(old, None)
        threading.Thread(target=self._scan, args=(job,), daemon=True).start()

    def running_job(self) -> Optional[ScanJob]:
        return next((j for j in self.jobs.values() if j.status == "running"), None)

    def _scan(self, job: ScanJob) -> None:
        try:
            base = os.path.abspath(job.directory)
            ex = FileExplorer(os.path.basename(base.rstrip(os.sep)) or "root")
            stack = [(base, ex.root, 0)]
            while stack and not job.truncated and not job.cancel.is_set():
                disk, node, depth = stack.pop()
                if job.max_depth is not None and depth >= job.max_depth:
                    continue
                try:
                    with os.scandir(disk) as it:
                        for e in it:
                            if job.cancel.is_set() or job.nodes >= job.max_nodes:
                                job.truncated = job.nodes >= job.max_nodes
                                break
                            try:
                                if e.is_symlink():
                                    continue
                                if e.is_dir(follow_symlinks=False):
                                    child = FSNode(e.name, NodeKind.FOLDER, parent=node)
                                    stack.append((e.path, child, depth + 1))
                                elif e.is_file(follow_symlinks=False):
                                    child = FSNode(e.name, NodeKind.FILE, size=e.stat().st_size, parent=node)
                                else:
                                    continue
                                node.children.append(child)
                                job.nodes += 1
                            except OSError:
                                job.errors += 1
                except OSError:  # sin permiso / carpeta desaparecida: se omite
                    job.errors += 1
            if job.cancel.is_set():
                job.status = "cancelled"
                return
            self.swap(ex)  # intercambio atómico: el árbol vivo nunca queda a medias
            job.status = "done"
        except Exception as exc:  # el árbol vivo sigue intacto
            LOG.exception("fallo en el escaneo")
            job.status, job.message = "failed", str(exc)
        finally:
            job.finished = time.time()


# ----------------------------------------------------------------------------
# Aplicación
# ----------------------------------------------------------------------------
def create_app(data_dir: Optional[str] = None, autosave_seconds: Optional[float] = None) -> FastAPI:
    store = Store(Path(data_dir or os.getenv("EXPLORER_DATA_DIR", "data")))
    interval = autosave_seconds if autosave_seconds is not None else float(os.getenv("EXPLORER_AUTOSAVE_SECONDS", "5"))
    stop = threading.Event()

    def autosave_loop() -> None:
        while not stop.wait(interval):
            try:
                store.save()
            except Exception:
                LOG.exception("autoguardado falló")

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        t = threading.Thread(target=autosave_loop, daemon=True)
        t.start()
        yield
        stop.set()
        for j in store.jobs.values():
            j.cancel.set()
        store.save(force=True)  # guardado final al apagar

    app = FastAPI(title="Folder Explorer API", lifespan=lifespan)
    app.state.store = store

    # ---- errores ----
    @app.exception_handler(ExplorerError)
    async def explorer_error(_, exc: ExplorerError):
        code = 404 if isinstance(exc, PathNotFoundError) else 409 if isinstance(
            exc, (DuplicateNameError, NotAFolderError)) else 400
        return JSONResponse({"detail": str(exc)}, status_code=code)

    @app.exception_handler(Exception)
    async def unexpected(_, exc: Exception):
        LOG.exception("error no controlado")
        return JSONResponse({"detail": "internal server error"}, status_code=500)

    # ---- lectura ----
    @app.get("/api/health")
    def health():
        job = store.running_job()
        return {"status": "ok", "version": store.version, "dirty": store.dirty,
                "last_saved": store.last_saved, "scanning": job.id if job else None}

    @app.get("/api/node")
    def node_info(path: Optional[str] = None):
        def work(ex: FileExplorer):
            n = ex.get(path)
            return {"path": n.path, "name": n.name, "type": n.kind.value, "size": n.size,
                    "children": len(n.children), "version": store.version}
        return store.run(work)

    @app.get("/api/children")
    def children(path: Optional[str] = None, offset: int = Query(0, ge=0),
                 limit: int = Query(200, ge=1, le=1000), files: bool = True):
        def work(ex: FileExplorer):
            n = ex.get(path)
            if n.is_file:
                raise NotAFolderError(f"not a folder: {n.path}")
            base = n.path
            ordered = store.cached(("kids", base, files), lambda: FileExplorer._ordered(n, files, True))
            items = [{"name": c.name, "type": c.kind.value, "size": c.size,
                      "has_children": bool(c.children)} for c in ordered[offset:offset + limit]]
            return {"path": base, "total": len(ordered), "offset": offset,
                    "limit": limit, "items": items, "version": store.version}
        return store.run(work)

    @app.get("/api/stats")
    def stats(path: Optional[str] = None):
        def work(ex: FileExplorer):
            n = ex.get(path)

            def build():
                files = folders = size = 0
                for x in ex.walk(n.path):
                    if x.is_file:
                        files += 1
                        size += x.size
                    elif x is not n:
                        folders += 1
                return {"files": files, "folders": folders, "size": size}
            return {"path": n.path, **store.cached(("stats", n.path), build)}
        return store.run(work)

    @app.get("/api/find")
    def find(pattern: str = Query(..., min_length=1), limit: int = Query(100, ge=1, le=1000)):
        def work(ex: FileExplorer):
            out, truncated = [], False
            for n in ex.walk():
                if fnmatch.fnmatch(n.name, pattern):
                    if len(out) >= limit:  # corte temprano
                        truncated = True
                        break
                    out.append(n.path)
            return {"results": out, "truncated": truncated}
        return store.run(work)

    @app.get("/api/render")
    def render(path: Optional[str] = None, style: str = Query("tree", pattern="^(tree|indent)$"),
               max_depth: int = Query(3, ge=0, le=50), limit: int = Query(500, ge=1, le=5000)):
        def work(ex: FileExplorer):
            lines = ex.render_structure(path, style=style, max_depth=max_depth).split("\n")
            more = len(lines) - limit
            if more > 0:
                lines = lines[:limit] + [f"... ({more} more lines)"]
            return {"text": "\n".join(lines)}
        return store.run(work)

    # ---- escritura ----
    @app.post("/api/folders", status_code=201)
    def add_folder(req: CreateReq):
        return store.run(lambda ex: {"path": ex.add_folder(req.path, req.parents).path, "version": store.version + 1}, True)

    @app.post("/api/files", status_code=201)
    def add_file(req: CreateReq):
        return store.run(lambda ex: {"path": ex.add_file(req.path, req.size, req.parents).path, "version": store.version + 1}, True)

    @app.post("/api/rename")
    def rename(req: RenameReq):
        return store.run(lambda ex: {"path": ex.rename(req.path, req.new_name).path, "version": store.version + 1}, True)

    @app.post("/api/move")
    def move(req: MoveReq):
        return store.run(lambda ex: {"path": ex.move(req.path, req.dest).path, "version": store.version + 1}, True)

    @app.delete("/api/node")
    def delete(path: str):
        return store.run(lambda ex: {"deleted": ex.remove(path).name, "version": store.version + 1}, True)

    @app.post("/api/snapshot")
    def snapshot():
        return {"saved": store.save(force=True), "last_saved": store.last_saved}

    # ---- escaneo ----
    @app.post("/api/scan", status_code=202)
    def scan(req: ScanReq):
        real = os.path.realpath(req.directory)
        if not os.path.isdir(real):
            raise HTTPException(404, f"directory not found: {req.directory}")
        allowed = os.getenv("EXPLORER_ALLOWED_ROOT")
        if allowed:
            allowed = os.path.realpath(allowed)
            try:
                ok = os.path.commonpath([real, allowed]) == allowed
            except ValueError:
                ok = False
            if not ok:
                raise HTTPException(403, "directory outside EXPLORER_ALLOWED_ROOT")
        with store.lock:
            if store.running_job():
                raise HTTPException(409, "a scan is already running")
            job = ScanJob(real, req.max_depth, req.max_nodes)
            store.start_scan(job)
        return job.to_dict()

    @app.get("/api/scan/{job_id}")
    def scan_status(job_id: str):
        job = store.jobs.get(job_id)
        if job is None:
            raise HTTPException(404, "unknown scan job")
        return job.to_dict()

    @app.delete("/api/scan/{job_id}")
    def scan_cancel(job_id: str):
        job = store.jobs.get(job_id)
        if job is None:
            raise HTTPException(404, "unknown scan job")
        job.cancel.set()
        return job.to_dict()

    # ---- interfaz ----
    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(WEB_DIR / "app.html")

    return app


if __name__ == "__main__":
    import uvicorn
    logging.basicConfig(level=logging.INFO)
    uvicorn.run(create_app(), host=os.getenv("EXPLORER_HOST", "127.0.0.1"),
                port=int(os.getenv("EXPLORER_PORT", "8000")))
