# Explorador de Carpetas — Árbol N-ario

Miniproyecto que modela la estructura de carpetas de un proyecto como un **árbol N-ario**
y la muestra en una interfaz web. Desarrollado siguiendo la metodología de la skill
[`docs/SkillArboles.md`](docs/SkillArboles.md) (análisis → estructura → código → pruebas).

| Elemento del árbol | En el sistema |
|---|---|
| **Raíz** | Carpeta principal (`/my-project`) |
| **Subraíces** | Carpetas internas (`/src`, `/assets`, `/tests`) |
| **Hojas** | Archivos (`index.py`, `style.css`) |

> Una carpeta vacía también es hoja estructural, pero **no es archivo**: cada nodo guarda su
> tipo (`FOLDER`/`FILE`) y los conteos usan ese tipo.

> **Convención:** el código (identificadores, mensajes e interfaz) está en inglés; los comentarios, docstrings y esta documentación están en español.

## Funcionalidades
- `count_files()` — cuenta los archivos de la raíz y de todas las subcarpetas.
- `print_folder_structure()` — imprime el árbol con conectores (`├──`) o con sangría.
- Crear carpetas/archivos (con carpetas intermedias automáticas), eliminar, buscar con patrones (`*.py`).
- `count_folders()`, `total_size()`, `from_disk()` (lee una carpeta real) y `to_dict()` (JSON).
- Recorridos **iterativos con pila**: sin límite de profundidad por recursión.
- `rename()` y `move()` — renombrar nodos y moverlos a otra carpeta (validan nombres duplicados y ciclos).
- **Servidor FastAPI** con carga perezosa, escaneo de carpetas grandes en segundo plano y tolerancia a fallos (ver sección «Servidor»).
- Interfaz web (HTML + JavaScript) con navegador de árbol, **Drag & Drop**, renombrado, resumen, búsqueda y carga de carpetas del PC.

## Estructura del repositorio
```
folder-explorer/
├── src/file_explorer.py        # Lógica del sistema (Python, solo biblioteca estándar)
├── src/server.py               # Servidor FastAPI (API REST + escaneo + persistencia)
├── tests/test_file_explorer.py # Pruebas de la lógica (pytest)
├── tests/test_server.py        # Pruebas de la API y de la tolerancia a fallos
├── web/app.html                # Interfaz conectada al servidor (carga perezosa)
├── web/explorer.html           # Interfaz independiente, sin servidor (port a JavaScript)
├── docs/SkillArboles.md        # Skill de diseño de árboles usada como guía
├── run_web.py                  # Abre la interfaz en el navegador
├── requirements.txt            # Dependencias (FastAPI, Uvicorn; pytest y httpx para pruebas)
├── pytest.ini
├── .github/workflows/ci.yml    # Integración continua en GitHub Actions
├── .gitignore
├── LICENSE
└── README.md
```

## Ejecución local
Requisitos: **Python 3.9+** (para la interfaz solo necesitas un navegador).

```bash
# 1) (Opcional pero recomendado) entorno virtual
python -m venv .venv
# Windows (PowerShell):  .venv\Scripts\Activate.ps1
# Linux / macOS:         source .venv/bin/activate

# 2) Instalar dependencias
python -m pip install -r requirements.txt

# 3) Demo en consola
python src/file_explorer.py

# 4) Servidor + interfaz (recomendado para carpetas grandes)
python src/server.py       # abre http://127.0.0.1:8000 en el navegador

# 4b) Interfaz independiente, sin servidor
python run_web.py          # o abre web/explorer.html con doble clic

# 5) Pruebas
python -m pytest
```

> En Windows, si `pytest` no se reconoce, usa siempre `python -m pytest`.

Salida de la demo:
```
my-project/
├── assets/
│   ├── img/
│   │   └── logo.png
│   └── style.css
├── docs/
├── src/
│   ├── utils/
│   │   └── helpers.py
│   └── index.py
├── tests/
│   └── test_main.py
└── README.md
```

## Servidor (FastAPI)
`python src/server.py` levanta la API y sirve la interfaz `web/app.html` en `http://127.0.0.1:8000`
(documentación interactiva de la API en `/docs`).

**Alto rendimiento**
- **Carga perezosa y paginada:** `/api/children` entrega 200 hijos por página; el navegador nunca recibe el árbol completo.
- **Caché por versión** del orden de hijos y de las estadísticas; se invalida solo al modificar el árbol.
- **Escaneo en segundo plano** (hilo) con progreso, cancelación y límites (`max_nodes`, `max_depth`); el árbol nuevo se construye aparte y se intercambia de una vez.
- Referencia medida en un entorno de pruebas con 100 000 archivos: escaneo ≈ 0,3 s, página de hijos ≈ 3–4 ms, estadísticas ≈ 20 ms (1 ms con caché). Tus cifras dependerán del disco y del equipo.

**Tolerancia a fallos**
- **Persistencia atómica:** archivo temporal + `fsync` + `os.replace`, con copia `snapshot.json.bak`.
- **Autoguardado** cada 5 s y guardado final al apagar. Al arrancar: si el snapshot está corrupto usa el `.bak`; si ambos fallan, arranca limpio sin caerse.
- **Escaneo seguro:** carpetas sin permiso o archivos ilegibles se cuentan y se omiten; si el escaneo falla o se cancela, el árbol actual no se modifica.
- Un `RLock` protege el árbol; errores del dominio devuelven 404/409/400/422 y un fallo inesperado devuelve 500 sin tumbar el servidor.
- La interfaz reintenta con espera exponencial las lecturas si el servidor se corta un momento.

**Endpoints principales**

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/api/children?path=&offset=&limit=` | Hijos paginados de una carpeta |
| GET | `/api/node`, `/api/stats`, `/api/find`, `/api/render` | Información, conteos, búsqueda y estructura impresa |
| POST | `/api/folders`, `/api/files` | Crear carpeta / archivo (`parents` crea las intermedias) |
| POST | `/api/rename`, `/api/move` | Renombrar y mover (Drag & Drop) |
| DELETE | `/api/node?path=` | Eliminar con todo su subárbol |
| POST | `/api/scan` · GET/DELETE `/api/scan/{id}` | Escanear una carpeta real, consultar progreso o cancelar |
| POST | `/api/snapshot` · GET `/api/health` | Guardar ahora · estado del servidor |

**Variables de entorno:** `EXPLORER_HOST` (127.0.0.1), `EXPLORER_PORT` (8000), `EXPLORER_DATA_DIR` (`./data`),
`EXPLORER_AUTOSAVE_SECONDS` (5) y `EXPLORER_ALLOWED_ROOT` (limita qué carpetas se pueden escanear).

> **Seguridad:** el servidor escucha solo en `127.0.0.1` y la ruta a escanear es una ruta del equipo donde corre.
> Si lo expones en una red, define `EXPLORER_ALLOWED_ROOT` y colócalo detrás de autenticación; esta versión no la incluye.

## 🖱️ Drag & Drop y renombrado en la interfaz
- **Mover:** arrastra un archivo o carpeta y suéltalo sobre otra carpeta. Soltar en el área vacía lo mueve a la raíz.
- **Renombrar:** doble clic sobre el elemento, tecla **F2** o botón **Rename**.
- Se rechazan los movimientos inválidos: mover una carpeta dentro de sí misma, nombres duplicados en el destino, o mover/renombrar la raíz.

## Uso como biblioteca
```python
import sys; sys.path.insert(0, "src")
from file_explorer import FileExplorer

ex = FileExplorer("my-project")
ex.add_file("/my-project/src/index.py", 2048, parents=True)
ex.add_file("/my-project/assets/style.css", 512, parents=True)

print(ex.count_files())                       # 2
ex.print_folder_structure(style="indent")     # imprime con sangrías
print(ex.find("*.py"))                        # ['/my-project/src/index.py']

ex.rename("/my-project/src/index.py", "main.py")          # renombrar
ex.move("/my-project/src/main.py", "/my-project/assets")   # mover (Drag & Drop)

real = FileExplorer.from_disk(".")            # árbol de una carpeta real
```

## Complejidad
*n* = nodos del subárbol, *d* = profundidad, *k* = hijos de una carpeta.

| Operación | Tiempo |
|---|---|
| `add_file`, `add_folder`, `get`, `remove`, `rename` | O(d·k) |
| `move` | O(d·k) |
| `count_files`, `count_folders`, `total_size`, `find` | O(n) |
| `print_folder_structure` | O(n log k) |
