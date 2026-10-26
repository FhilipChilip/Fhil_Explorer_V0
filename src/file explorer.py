"""
Explorador de Carpetas (Árbol N-ario) 
==============================================
* Problema   : representar la estructura de carpetas de un proyecto para que una
               interfaz pueda navegarla (aquí solo se desarrolla la lógica).
* Nodo       : FSNode (carpeta o archivo).
* Raíz       : carpeta principal del proyecto (p. ej. "/my-project").
* Subraíces  : carpetas internas (/src, /assets, /tests...), cada una es un
               subárbol independiente.
* Hojas      : archivos (index.py, style.css). OJO: una carpeta vacía también
               es hoja estructural, pero NO es archivo -> por eso cada nodo
               lleva un `kind` y los conteos usan `kind`, nunca `is_leaf`.
* Estructura : Árbol N-ario con lista de hijos (jerarquía libre, sin orden de clave).
* Soporte    : PILA (DFS iterativo: conteos, búsqueda, impresión).
               No hay recursión -> sin límite de profundidad de Python.
               
INVARIANTES
-----------
1. Una sola raíz (carpeta) con parent=None.
2. Los archivos nunca tienen hijos.
3. Los nombres son únicos entre hermanos y no contienen "/".
4. Cada hijo apunta a su padre y aparece una sola vez en `parent.children`.

COMPLEJIDAD (n = nodos del subárbol, d = profundidad, k = hijos de una carpeta)
-------------------------------------------------------------------------------
add_file / add_folder : O(d·k)        count_files / count_folders : O(n)
get / remove          : O(d·k)        print_folder_structure     : O(n log k)
find                  : O(n)          from_disk                  : O(n)
"""
from __future__ import annotations

import fnmatch
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterator, List, Optional


# ----------------------------------------------------------------------------
# Errores explícitos
# ----------------------------------------------------------------------------
class ExplorerError(Exception):
    """Base de los errores del explorador."""


class InvalidPathError(ExplorerError):
    """Ruta mal formada (no absoluta, vacía, con '.' o '..')."""


class PathNotFoundError(ExplorerError):
    """La ruta no existe en el árbol."""


class DuplicateNameError(ExplorerError):
    """Ya existe un elemento con ese nombre en la carpeta."""


class NotAFolderError(ExplorerError):
    """Se intentó usar un archivo como carpeta."""


# ----------------------------------------------------------------------------
# Nodo
# ----------------------------------------------------------------------------
class NodeKind(Enum):
    FOLDER = "folder"
    FILE = "file"


@dataclass(eq=False)
class FSNode:
    name: str
    kind: NodeKind
    size: int = 0  # bytes (solo archivos)
    parent: Optional["FSNode"] = field(default=None, repr=False)
    children: List["FSNode"] = field(default_factory=list, repr=False)

    @property
    def is_file(self) -> bool:
        return self.kind is NodeKind.FILE

    @property
    def is_folder(self) -> bool:
        return self.kind is NodeKind.FOLDER

    @property
    def path(self) -> str:
        """Ruta absoluta estilo POSIX, p. ej. '/my-project/src/index.py'. O(d)."""
        names, n = [], self
        while n is not None:
            names.append(n.name)
            n = n.parent
        return "/" + "/".join(reversed(names))


# ----------------------------------------------------------------------------
# Gestor del árbol
# ----------------------------------------------------------------------------
class FileExplorer:
    """Único punto de mutación del árbol (protege los invariantes)."""

    def __init__(self, root_name: str = "my-project"):
        self._check_name(root_name)
        self.root = FSNode(root_name, NodeKind.FOLDER)

    # ---------------- utilidades de ruta ----------------
    @staticmethod
    def _check_name(name: str) -> None:
        if not name or "/" in name or name in (".", ".."):
            raise InvalidPathError(f"invalid name: {name!r}")

    @staticmethod
    def _split(path: str) -> List[str]:
        if not isinstance(path, str) or not path.startswith("/"):
            raise InvalidPathError(f"path must be absolute (start with '/'): {path!r}")
        parts = [p for p in path.split("/") if p]
        if not parts:
            raise InvalidPathError("empty path")
        for p in parts:
            if p in (".", ".."):
                raise InvalidPathError(f"'.' and '..' are not allowed: {path!r}")
        return parts

    @staticmethod
    def _child(folder: FSNode, name: str) -> Optional[FSNode]:
        return next((c for c in folder.children if c.name == name), None)

    def _resolve(self, path: Optional[str]) -> FSNode:
        if path is None:
            return self.root
        parts = self._split(path)
        if parts[0] != self.root.name:
            raise PathNotFoundError(path)
        node = self.root
        for name in parts[1:]:
            if node.is_file:
                raise PathNotFoundError(path)
            nxt = self._child(node, name)
            if nxt is None:
                raise PathNotFoundError(path)
            node = nxt
        return node

    # ---------------- consulta ----------------
    def get(self, path: str) -> FSNode:
        return self._resolve(path)

    def exists(self, path: str) -> bool:
        try:
            self._resolve(path)
            return True
        except (PathNotFoundError, InvalidPathError):
            return False

    def walk(self, path: Optional[str] = None) -> Iterator[FSNode]:
        """DFS pre-orden con PILA (iterativo). O(n)."""
        stack = [self._resolve(path)]
        while stack:
            node = stack.pop()
            yield node
            stack.extend(reversed(node.children))

    # ---------------- mutación ----------------
    def _create(self, path: str, kind: NodeKind, size: int, parents: bool) -> FSNode:
        parts = self._split(path)
        if parts[0] != self.root.name:
            raise PathNotFoundError(f"the root is '/{self.root.name}': {path!r}")
        if len(parts) == 1:
            raise DuplicateNameError("the root already exists")
        for p in parts:
            self._check_name(p)

        folder = self.root
        for name in parts[1:-1]:  # recorrer/crear carpetas intermedias
            nxt = self._child(folder, name)
            if nxt is None:
                if not parents:
                    raise PathNotFoundError(f"folder '{name}' does not exist in {path!r}")
                nxt = FSNode(name, NodeKind.FOLDER, parent=folder)
                folder.children.append(nxt)
            elif nxt.is_file:
                raise NotAFolderError(f"'{name}' is a file")
            folder = nxt

        name = parts[-1]
        if self._child(folder, name) is not None:
            raise DuplicateNameError(f"already exists: {path}")
        node = FSNode(name, kind, size=size if kind is NodeKind.FILE else 0, parent=folder)
        folder.children.append(node)
        return node

    def add_folder(self, path: str, parents: bool = False) -> FSNode:
        """Crea una carpeta. `parents=True` crea las intermedias (como mkdir -p)."""
        return self._create(path, NodeKind.FOLDER, 0, parents)

    def add_file(self, path: str, size: int = 0, parents: bool = False) -> FSNode:
        """Crea un archivo (hoja). `size` en bytes."""
        if size < 0:
            raise ValueError("size cannot be negative")
        return self._create(path, NodeKind.FILE, size, parents)

    def remove(self, path: str) -> FSNode:
        """Elimina un archivo o carpeta completa (con todo su subárbol)."""
        node = self._resolve(path)
        if node is self.root:
            raise InvalidPathError("the root cannot be removed")
        node.parent.children.remove(node)
        node.parent = None
        return node

    # ---------------- funciones clave ----------------
    def count_files(self, path: Optional[str] = None) -> int:
        """Cuenta los ARCHIVOS de la carpeta indicada (por defecto, la raíz) y de
        todas sus subcarpetas. Las carpetas vacías no cuentan. O(n)."""
        return sum(1 for n in self.walk(path) if n.is_file)

    def count_folders(self, path: Optional[str] = None) -> int:
        """Cuenta las subcarpetas (sin contar la carpeta de partida). O(n)."""
        start = self._resolve(path)
        return sum(1 for n in self.walk(path) if n.is_folder and n is not start)

    def total_size(self, path: Optional[str] = None) -> int:
        """Suma de bytes de todos los archivos del subárbol. O(n)."""
        return sum(n.size for n in self.walk(path) if n.is_file)

    def find(self, pattern: str, kind: Optional[NodeKind] = None) -> List[str]:
        """Rutas cuyo nombre coincide con un patrón glob (p. ej. '*.py')."""
        return [
            n.path
            for n in self.walk()
            if fnmatch.fnmatch(n.name, pattern) and (kind is None or n.kind is kind)
        ]

    # ---------------- impresión ----------------
    @staticmethod
    def _ordered(node: FSNode, show_files: bool, sort: bool) -> List[FSNode]:
        kids = [c for c in node.children if show_files or c.is_folder]
        if sort:  # carpetas primero, luego orden alfabético
            kids.sort(key=lambda c: (c.is_file, c.name.lower()))
        return kids

    @staticmethod
    def _label(node: FSNode) -> str:
        return node.name + "/" if node.is_folder else node.name

    def render_structure(
        self,
        path: Optional[str] = None,
        style: str = "tree",
        show_files: bool = True,
        max_depth: Optional[int] = None,
        sort: bool = True,
    ) -> str:
        """Devuelve la estructura como texto.
        style='tree'   -> ├── └── │   (conectores)
        style='indent' -> sangría simple de 2 espacios por nivel."""
        if style not in ("tree", "indent"):
            raise ValueError("style must be 'tree' or 'indent'")
        start = self._resolve(path)
        lines = [self._label(start)]

        def push(parent: FSNode, prefix: str, depth: int, stack: list) -> None:
            kids = self._ordered(parent, show_files, sort)
            for i in range(len(kids) - 1, -1, -1):  # inverso: la pila saca en orden
                stack.append((kids[i], prefix, i == len(kids) - 1, depth))

        stack: list = []
        if start.is_folder:
            push(start, "", 1, stack)
        while stack:
            node, prefix, is_last, depth = stack.pop()
            if style == "tree":
                lines.append(prefix + ("└── " if is_last else "├── ") + self._label(node))
                child_prefix = prefix + ("    " if is_last else "│   ")
            else:
                lines.append("  " * depth + self._label(node))
                child_prefix = ""
            if node.is_folder and (max_depth is None or depth < max_depth):
                push(node, child_prefix, depth + 1, stack)
        return "\n".join(lines)

    def print_folder_structure(self, path: Optional[str] = None, **kwargs: Any) -> str:
        """Imprime en pantalla el árbol con sangrías y devuelve el mismo texto.
        Acepta: style, show_files, max_depth, sort."""
        text = self.render_structure(path, **kwargs)
        print(text)
        return text

    # ---------------- integración con el disco real ----------------
    @classmethod
    def from_disk(cls, directory: str, max_depth: Optional[int] = None) -> "FileExplorer":
        """Construye el árbol leyendo una carpeta real (iterativo, sin recursión).
        Omite enlaces simbólicos (evita ciclos) y rutas sin permiso."""
        directory = os.path.abspath(directory)
        if not os.path.isdir(directory):
            raise PathNotFoundError(directory)
        ex = cls(os.path.basename(directory.rstrip(os.sep)) or "root")
        stack = [(directory, ex.root, 0)]
        while stack:
            disk_path, node, depth = stack.pop()
            if max_depth is not None and depth >= max_depth:
                continue
            try:
                entries = list(os.scandir(disk_path))
            except (PermissionError, OSError):
                continue
            for e in entries:
                try:
                    if e.is_symlink():
                        continue
                    if e.is_dir(follow_symlinks=False):
                        child = FSNode(e.name, NodeKind.FOLDER, parent=node)
                        node.children.append(child)
                        stack.append((e.path, child, depth + 1))
                    elif e.is_file(follow_symlinks=False):
                        child = FSNode(e.name, NodeKind.FILE, size=e.stat().st_size, parent=node)
                        node.children.append(child)
                except OSError:
                    continue
        return ex

    # ---------------- serialización (útil para enlazar con una GUI) ----------------
    def to_dict(self, path: Optional[str] = None) -> Dict[str, Any]:
        start = self._resolve(path)

        def make(n: FSNode) -> Dict[str, Any]:
            d: Dict[str, Any] = {"name": n.name, "type": n.kind.value}
            if n.is_file:
                d["size"] = n.size
            else:
                d["children"] = []
            return d

        root_d = make(start)
        stack = [(start, root_d)]
        while stack:
            n, d = stack.pop()
            if n.is_folder:
                for c in n.children:
                    cd = make(c)
                    d["children"].append(cd)
                    stack.append((c, cd))
        return root_d

    # ---------------- verificación de invariantes ----------------
    def validate(self) -> None:
        assert self.root.parent is None and self.root.is_folder, "invalid root"
        seen = set()
        for n in self.walk():
            assert id(n) not in seen, "repeated node (cycle)"
            seen.add(id(n))
            assert not (n.is_file and n.children), f"file with children: {n.path}"
            names = [c.name for c in n.children]
            assert len(names) == len(set(names)), f"duplicate names in {n.path}"
            for c in n.children:
                assert c.parent is n, f"inconsistent parent in {c.path}"

# ----------------------------------------------------------------------------
# Demo
# ----------------------------------------------------------------------------
if __name__ == "__main__":
    ex = FileExplorer("my-project")
    ex.add_file("/my-project/README.md", 1200)
    ex.add_file("/my-project/src/index.py", 2048, parents=True)
    ex.add_file("/my-project/src/utils/helpers.py", 900, parents=True)
    ex.add_file("/my-project/assets/style.css", 512, parents=True)
    ex.add_file("/my-project/assets/img/logo.png", 20480, parents=True)
    ex.add_file("/my-project/tests/test_main.py", 700, parents=True)
    ex.add_folder("/my-project/docs")  # carpeta vacía

    print("=== Structure (tree) ===")
    ex.print_folder_structure()
    print("\n=== Structure (indent) ===")
    ex.print_folder_structure(style="indent")
    print("\nTotal files      :", ex.count_files())
    print("Files in /src    :", ex.count_files("/my-project/src"))
    print("Subfolders       :", ex.count_folders())
    print("Total size (B)   :", ex.total_size())
    print("*.py             :", ex.find("*.py"))

