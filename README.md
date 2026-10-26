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
- Interfaz web (HTML + JavaScript) con navegador de árbol, resumen, búsqueda y carga de carpetas del PC.

## Estructura del repositorio
```
folder-explorer/
├── src/file_explorer.py        # Lógica del sistema (Python, solo biblioteca estándar)
├── tests/test_file_explorer.py # Pruebas (pytest)
├── web/explorer.html         # Interfaz visual (port de la lógica a JavaScript)
├── docs/SkillArboles.md        # Skill de diseño de árboles usada como guía
├── run_web.py                  # Abre la interfaz en el navegador
├── requirements.txt            # Dependencias (solo pytest, para pruebas)
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

# 2) Instalar dependencias (solo para las pruebas)
python -m pip install -r requirements.txt

# 3) Demo en consola
python src/file_explorer.py

# 4) Interfaz visual
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

real = FileExplorer.from_disk(".")            # árbol de una carpeta real
```

## Complejidad
*n* = nodos del subárbol, *d* = profundidad, *k* = hijos de una carpeta.

| Operación | Tiempo |
|---|---|
| `add_file`, `add_folder`, `get`, `remove` | O(d·k) |
| `count_files`, `count_folders`, `total_size`, `find` | O(n) |
| `print_folder_structure` | O(n log k) |

## 🔭 Ideas para evolucionar
Mover/renombrar nodos, deshacer/rehacer con el patrón Command, un servidor (Flask/FastAPI)
que conecte la interfaz con `file_explorer.py` en vivo, y carga perezosa de carpetas grandes.
