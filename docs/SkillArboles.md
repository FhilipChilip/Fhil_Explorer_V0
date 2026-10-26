---
name: arboles-de-informacion
description: Analiza, diseña e implementa desde cero sistemas basados en árboles (N-arios, BST, AVL, B, Segmentos, Behavior Trees, historiales ramificados) con pilas, colas, listas y flujos asíncronos. Úsala cuando el usuario defina un caso de estudio jerárquico y requiera una estructura de datos convertida en sistema funcional, probado y documentado.
---

# Skill: Arquitectura y Desarrollo de Árboles de Información desde Cero

## 1. Descripción
Guía de extremo a extremo para convertir un **caso de estudio** en un **sistema de software** cuyo núcleo es un árbol: desde el análisis del dominio y la elección de la variante de árbol, hasta el código modular, las pruebas, el rendimiento y la persistencia. Integra estructuras de soporte (pilas, colas, listas) y flujos asíncronos (`asyncio`) para agentes de IA y sistemas escalables.

## 2. Cuándo usar / cuándo NO usar
**Usar cuando:**
* Hay jerarquías, redes de decisión, ramificaciones o dependencias padre-hijo (menús, archivos, organigramas, DOM, taxonomías).
* Se implementan árboles de comportamiento (*Behavior Trees*), árboles de decisión, historiales de conversación ramificados, *undo/redo* o planificadores de tareas.
* Se necesitan búsquedas ordenadas, rangos, índices o almacenamiento en disco.

**NO usar (o cuestionar el diseño) cuando:**
* Los datos son planos y solo se busca por clave → basta un `dict`/`set`.
* Hay relaciones muchos-a-muchos o ciclos → el modelo correcto es un **grafo** (un árbol es un grafo conexo, acíclico y con un solo padre por nodo).
* El volumen es pequeño y no habrá crecimiento → una lista ordenada con `bisect` puede ser más simple.

---

## 3. Fase 0 — Definición del Caso de Estudio (obligatoria)
Antes de escribir código, completar este **brief**. Si el usuario no da algún dato, asumirlo, declararlo explícitamente y continuar.

| # | Pregunta | Ejemplo de respuesta |
|---|----------|----------------------|
| 1 | ¿Qué problema resuelve? (una frase) | Historial de chat con ramas alternativas |
| 2 | ¿Qué representa un nodo? | Un mensaje (rol, texto, timestamp) |
| 3 | ¿Qué es la raíz? ¿Y las hojas? | Raíz: inicio de sesión. Hojas: últimas respuestas de cada rama |
| 4 | ¿Cuántos hijos por nodo? ¿Orden relevante? | Ilimitados; orden de creación |
| 5 | Operaciones principales y su frecuencia | Insertar (alta), buscar por id (alta), podar (baja) |
| 6 | ¿Datos estáticos, dinámicos o en tiempo real? | Dinámicos, crecen con el uso |
| 7 | ¿Consultas de rango/orden/agregación? | No / Sí (suma por rango) |
| 8 | Tamaño esperado (n) y límites de memoria | ≤ 100 000 nodos en RAM |
| 9 | ¿Persistencia? ¿Formato? | JSON en disco |
| 10 | ¿Concurrencia/asincronía? | Sí, llamadas a un LLM por nodo |
| 11 | ¿Se requiere deshacer/rehacer? | Sí |
| 12 | Requisitos no funcionales (latencia, trazabilidad, seguridad) | Recorrido < 50 ms |

**Entregable de la fase:** un párrafo de resumen + lista de supuestos.

---

## 4. Fase 1 — Análisis y Definición de la Jerarquía
1. **Raíz principal:** punto de entrada único (`AgentRoot`, `StateRoot`, `FSRoot`). Debe existir siempre y no puede eliminarse.
2. **Subraíces (subárboles):** ramas lógicas (dominios, intenciones, módulos). Cada subárbol debe poder tratarse como un árbol independiente (propiedad recursiva).
3. **Hojas (casos base):** acciones atómicas o datos finales; terminan la recursión.
4. **Identificadores:** cada nodo con `node_id` único e inmutable (UUID, ruta o entero). Mantener un **índice** `id → nodo` para búsquedas O(1).
5. **Flujo de datos:** estático / dinámico / rangos / persistente (condiciona la Fase 2).
6. **Invariantes del sistema** (escribirlos y verificarlos en pruebas):
   * Existe exactamente una raíz y `root.parent is None`.
   * Todo nodo no raíz tiene exactamente un padre y aparece una sola vez en `parent.children`.
   * No existen ciclos; los `node_id` son únicos.
   * (BST) `izq < nodo < der`. (AVL) `|balance| ≤ 1`. (Segmentos) `padre = op(hijoIzq, hijoDer)`.

---

## 5. Fase 2 — Selección de la Estructura de Árbol

### 5.1 Matriz de decisión
| Estructura | Úsala si… | Búsqueda | Insertar | Notas |
|---|---|---|---|---|
| **N-ario** | Jerarquía libre (UI, archivos, decisiones de IA, historial) | O(n) o O(1) con índice | O(1) | Hijos en lista |
| **Binario / BST** | Orden y búsquedas rápidas con datos aleatorios | O(log n) prom., O(n) peor | O(log n) prom. | Se degenera con datos ordenados |
| **AVL** | Muchas lecturas, balance estricto | O(log n) | O(log n) | Rotaciones simples/dobles |
| **Rojo-Negro** | Muchas escrituras, balance relajado | O(log n) | O(log n) | Menos rotaciones que AVL |
| **Árbol B / B+** | Disco/bases de datos, bloques grandes | O(log_t n) | O(log_t n) | Minimiza accesos a disco |
| **Segmentos** | Consultas de rango + actualizaciones puntuales | O(log n) | O(log n) update | Op. asociativa (suma, min, max, gcd) |
| **Fenwick (BIT)** | Sumas prefijo, menos memoria que segmentos | O(log n) | O(log n) | Solo ops. invertibles |
| **Trie** | Prefijos, autocompletado, rutas | O(L) | O(L) | L = longitud de la clave |
| **Heap** | Prioridades (planificador) | O(1) mín. | O(log n) | Árbol completo en un arreglo |
| **Behavior Tree** | Agentes autónomos y decisiones modulares | — | — | Nodos Sequence/Selector/Action |

### 5.2 Árbol de decisión para elegir
```
¿Hay orden por clave y búsquedas frecuentes?
├─ No → ¿Jerarquía libre? → N-ario
│       ¿Decisiones de agente? → Behavior Tree
│       ¿Prefijos de texto? → Trie
├─ Sí → ¿Cabe en RAM?
│        ├─ No → Árbol B / B+
│        └─ Sí → ¿Consultas de rango sobre un arreglo mutable?
│                 ├─ Sí → Segmentos / Fenwick
│                 └─ No → AVL (lectura) o Rojo-Negro (escritura)
```

### 5.3 Cuidados de complejidad
* Documentar siempre **tiempo y espacio** de cada operación pública.
* En Python, `list.pop(0)` es O(n): usar `collections.deque` para colas.
* La recursión de Python limita ~1000 niveles: para árboles profundos o degenerados usar **recorridos iterativos** (pila explícita).

---

## 6. Fase 3 — Integración de Estructuras de Soporte
| Estructura | Uso en el sistema | Implementación Python |
|---|---|---|
| **Cola (FIFO)** | BFS, bucle de eventos, *streaming*, trabajos por nivel | `collections.deque` / `asyncio.Queue` |
| **Pila (LIFO)** | DFS iterativo, Undo/Redo, backtracking | `list` (`append`/`pop`) |
| **Lista** | Colección de hijos de cada nodo | `list` |
| **Dict (índice)** | Acceso O(1) por `node_id` | `dict` |
| **Heap** | Colas de prioridad (ej. A*, planificador) | `heapq` |

Regla práctica: *si necesitas nivel por nivel → cola; si necesitas profundizar o revertir → pila.*

---

## 7. Fase 4 — Arquitectura de Software y Patrones

### 7.1 Estructura de proyecto recomendada
```
proyecto/
├── src/
│   ├── nodes.py        # Node y variantes
│   ├── tree.py         # Gestor: inserción, búsqueda, recorridos
│   ├── commands.py     # Command + History (undo/redo)
│   ├── storage.py      # Serialización JSON / disco
│   ├── services.py     # Reglas del dominio (caso de estudio)
│   └── main.py         # Punto de entrada / demo
├── tests/
│   ├── test_tree.py
│   └── test_invariants.py
└── README.md
```

### 7.2 Separación de responsabilidades
1. **`Node`**: datos, referencias a padre/hijos, metadatos. Sin lógica de negocio pesada.
2. **`Tree` (gestor)**: raíz, índice, inserción, eliminación, movimiento, recorridos. Es el **único** que muta la estructura (protege invariantes).
3. **Servicios de dominio**: reglas específicas del caso de estudio, construidas sobre `Tree`.
4. **Persistencia**: aislada; el árbol no sabe cómo se guarda.

### 7.3 Patrones de diseño aplicables
* **Composite:** tratar hoja y rama con la misma interfaz (base de los Behavior Trees).
* **Iterator / Generator:** exponer recorridos con `yield`, sin revelar la estructura interna.
* **Visitor:** separar el algoritmo (imprimir, evaluar, exportar) de la estructura.
* **Command:** cada mutación es un objeto con `execute()`/`undo()` → Undo/Redo.
* **Observer:** notificar cambios de nodos a la UI o a otros módulos.
* **Strategy:** intercambiar BFS/DFS o criterios de balance sin modificar el árbol.

### 7.4 Reglas de calidad
* Tipado estático (`typing`), `dataclass` donde aplique y docstrings con complejidad.
* Errores explícitos (`NodeNotFoundError`, `InvalidOperationError`), nunca fallos silenciosos.
* Recorridos **iterativos** por defecto; recursión solo si la profundidad está acotada.
* Evitar referencias circulares sin control (padre ↔ hijo): al eliminar, romper `parent`.
* Idempotencia y validación antes de mutar (p. ej. no mover un nodo dentro de su propio subárbol).

---

## 8. Implementación de Referencia (Python 3.10+)

### 8.1 Núcleo N-ario: `Node` + `Tree`
```python
from __future__ import annotations

import asyncio
import json
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Deque, Dict, Iterator, List, Optional, Tuple


class NodeNotFoundError(KeyError):
    """El node_id solicitado no existe en el árbol."""


class InvalidOperationError(ValueError):
    """La operación violaría un invariante del árbol."""


@dataclass(eq=False)
class Node:
    node_id: str
    data: Any = None
    parent: Optional["Node"] = field(default=None, repr=False)
    children: List["Node"] = field(default_factory=list, repr=False)
    meta: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_leaf(self) -> bool:
        return not self.children

    @property
    def is_root(self) -> bool:
        return self.parent is None

    @property
    def depth(self) -> int:
        d, n = 0, self
        while n.parent is not None:
            d, n = d + 1, n.parent
        return d

    def path(self) -> List[str]:
        """Ids desde la raíz hasta este nodo. O(profundidad)."""
        ids, n = [], self
        while n is not None:
            ids.append(n.node_id)
            n = n.parent
        return ids[::-1]


class Tree:
    """Árbol N-ario con índice id→nodo. Único punto de mutación estructural."""

    def __init__(self, root_id: str = "root", root_data: Any = None):
        self.root = Node(root_id, root_data)
        self._index: Dict[str, Node] = {root_id: self.root}

    # ---------- consulta ----------
    def __len__(self) -> int:
        return len(self._index)

    def __contains__(self, node_id: str) -> bool:
        return node_id in self._index

    def get(self, node_id: str) -> Node:  # O(1)
        try:
            return self._index[node_id]
        except KeyError:
            raise NodeNotFoundError(node_id) from None

    # ---------- mutación (protege invariantes) ----------
    def add(self, parent_id: str, node_id: str, data: Any = None) -> Node:  # O(1)
        node = Node(node_id, data)
        self.attach(parent_id, node)
        return node

    def attach(self, parent_id: str, subtree: Node, index: Optional[int] = None) -> None:
        """Inserta un nodo (o subárbol completo) bajo un padre."""
        parent = self.get(parent_id)
        new_nodes = list(self._walk(subtree))
        for n in new_nodes:
            if n.node_id in self._index:
                raise InvalidOperationError(f"id duplicado: {n.node_id}")
        subtree.parent = parent
        if index is None:
            parent.children.append(subtree)
        else:
            parent.children.insert(index, subtree)
        for n in new_nodes:
            self._index[n.node_id] = n

    def detach(self, node_id: str) -> Tuple[str, int, Node]:
        """Extrae un subárbol. Devuelve (id_padre, posición, subárbol). O(k + tamaño)."""
        node = self.get(node_id)
        if node.is_root:
            raise InvalidOperationError("no se puede eliminar la raíz")
        parent = node.parent
        idx = parent.children.index(node)
        parent.children.pop(idx)
        node.parent = None
        for n in self._walk(node):
            del self._index[n.node_id]
        return parent.node_id, idx, node

    def move(self, node_id: str, new_parent_id: str) -> None:
        node, new_parent = self.get(node_id), self.get(new_parent_id)
        if node.is_root:
            raise InvalidOperationError("no se puede mover la raíz")
        anc = new_parent
        while anc is not None:  # evita ciclos: destino dentro del propio subárbol
            if anc is node:
                raise InvalidOperationError("destino dentro del propio subárbol")
            anc = anc.parent
        node.parent.children.remove(node)
        node.parent = new_parent
        new_parent.children.append(node)

    # ---------- recorridos (iterativos) ----------
    @staticmethod
    def _walk(start: Node) -> Iterator[Node]:
        stack = [start]
        while stack:
            n = stack.pop()
            yield n
            stack.extend(reversed(n.children))

    def dfs(self, start: Optional[Node] = None, order: str = "pre") -> Iterator[Node]:
        """DFS con PILA. order: 'pre' | 'post'. O(n) tiempo, O(h) espacio."""
        start = start or self.root
        if order == "pre":
            yield from self._walk(start)
        elif order == "post":
            out, stack = [], [start]
            while stack:
                n = stack.pop()
                out.append(n)
                stack.extend(n.children)
            yield from reversed(out)
        else:
            raise ValueError("order debe ser 'pre' o 'post'")

    def bfs(self, start: Optional[Node] = None) -> Iterator[Node]:
        """BFS con COLA. O(n) tiempo, O(ancho) espacio."""
        q: Deque[Node] = deque([start or self.root])
        while q:
            n = q.popleft()
            yield n
            q.extend(n.children)

    def find(self, predicate: Callable[[Node], bool]) -> Optional[Node]:
        return next((n for n in self.bfs() if predicate(n)), None)

    def height(self) -> int:
        return max((n.depth for n in self.bfs()), default=0)

    def leaves(self) -> List[Node]:
        return [n for n in self.bfs() if n.is_leaf]

    # ---------- asincronía ----------
    async def traverse_async(
        self,
        visit: Callable[[Node], Awaitable[None]],
        start: Optional[Node] = None,
        concurrency: int = 1,
    ) -> None:
        """BFS por niveles; nodos del mismo nivel se procesan en paralelo
        (limitado por `concurrency`). Ideal para llamadas a APIs/LLMs."""
        sem = asyncio.Semaphore(concurrency)

        async def run(n: Node) -> None:
            async with sem:
                await visit(n)

        level = [start or self.root]
        while level:
            await asyncio.gather(*(run(n) for n in level))
            level = [c for n in level for c in n.children]

    # ---------- serialización ----------
    def to_dict(self, node: Optional[Node] = None) -> dict:
        """Serializa con pila (sin recursión)."""
        node = node or self.root
        root_d = {"id": node.node_id, "data": node.data, "children": []}
        stack = [(node, root_d)]
        while stack:
            n, d = stack.pop()
            for c in n.children:
                cd = {"id": c.node_id, "data": c.data, "children": []}
                d["children"].append(cd)
                stack.append((c, cd))
        return root_d

    @classmethod
    def from_dict(cls, d: dict) -> "Tree":
        t = cls(d["id"], d.get("data"))
        stack = [(d, t.root)]
        while stack:
            dd, parent = stack.pop()
            for cd in dd.get("children", []):
                child = t.add(parent.node_id, cd["id"], cd.get("data"))
                stack.append((cd, child))
        return t

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, path: str) -> "Tree":
        with open(path, encoding="utf-8") as f:
            return cls.from_dict(json.load(f))

    # ---------- verificación de invariantes ----------
    def validate(self) -> None:
        seen = set()
        for n in self.bfs():
            assert n.node_id not in seen, f"ciclo/duplicado: {n.node_id}"
            seen.add(n.node_id)
            for c in n.children:
                assert c.parent is n, f"padre inconsistente en {c.node_id}"
        assert seen == set(self._index), "índice desincronizado"
        assert self.root.parent is None, "la raíz tiene padre"
```

### 8.2 Undo/Redo con Command + dos pilas
```python
class Command:
    def execute(self) -> None: ...
    def undo(self) -> None: ...


class AddNode(Command):
    def __init__(self, tree: Tree, parent_id: str, node_id: str, data: Any = None):
        self.tree, self.parent_id, self.node_id, self.data = tree, parent_id, node_id, data

    def execute(self) -> None:
        self.tree.add(self.parent_id, self.node_id, self.data)

    def undo(self) -> None:
        self.tree.detach(self.node_id)


class RemoveNode(Command):
    def __init__(self, tree: Tree, node_id: str):
        self.tree, self.node_id = tree, node_id
        self._saved: Optional[Tuple[str, int, Node]] = None

    def execute(self) -> None:
        self._saved = self.tree.detach(self.node_id)

    def undo(self) -> None:
        parent_id, idx, subtree = self._saved
        self.tree.attach(parent_id, subtree, idx)


class History:
    def __init__(self) -> None:
        self._undo: List[Command] = []  # PILA
        self._redo: List[Command] = []  # PILA

    def run(self, cmd: Command) -> None:
        cmd.execute()
        self._undo.append(cmd)
        self._redo.clear()  # una acción nueva invalida el futuro

    def undo(self) -> bool:
        if not self._undo:
            return False
        cmd = self._undo.pop()
        cmd.undo()
        self._redo.append(cmd)
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        cmd = self._redo.pop()
        cmd.execute()
        self._undo.append(cmd)
        return True
```

### 8.3 AVL (búsqueda y inserción auto-balanceada)
```python
class AVLNode:
    __slots__ = ("key", "left", "right", "height")

    def __init__(self, key):
        self.key, self.left, self.right, self.height = key, None, None, 1


class AVLTree:
    """Invariante: |altura(izq) - altura(der)| <= 1. Insertar/buscar: O(log n)."""

    def __init__(self) -> None:
        self.root: Optional[AVLNode] = None

    @staticmethod
    def _h(n): return n.height if n else 0

    def _upd(self, n): n.height = 1 + max(self._h(n.left), self._h(n.right))

    def _bal(self, n): return self._h(n.left) - self._h(n.right) if n else 0

    def _rot_right(self, y):
        x = y.left
        y.left, x.right = x.right, y
        self._upd(y); self._upd(x)
        return x

    def _rot_left(self, x):
        y = x.right
        x.right, y.left = y.left, x
        self._upd(x); self._upd(y)
        return y

    def _insert(self, n, key):
        if n is None:
            return AVLNode(key)
        if key < n.key:
            n.left = self._insert(n.left, key)
        elif key > n.key:
            n.right = self._insert(n.right, key)
        else:
            return n  # sin duplicados
        self._upd(n)
        b = self._bal(n)
        if b > 1 and key < n.left.key:            # Izq-Izq
            return self._rot_right(n)
        if b < -1 and key > n.right.key:          # Der-Der
            return self._rot_left(n)
        if b > 1 and key > n.left.key:            # Izq-Der
            n.left = self._rot_left(n.left)
            return self._rot_right(n)
        if b < -1 and key < n.right.key:          # Der-Izq
            n.right = self._rot_right(n.right)
            return self._rot_left(n)
        return n

    def insert(self, key) -> None:
        self.root = self._insert(self.root, key)

    def contains(self, key) -> bool:
        n = self.root
        while n:
            if key == n.key:
                return True
            n = n.left if key < n.key else n.right
        return False

    def inorder(self) -> List[Any]:
        out, stack, n = [], [], self.root
        while stack or n:
            while n:
                stack.append(n); n = n.left
            n = stack.pop()
            out.append(n.key)
            n = n.right
        return out
```
> Para borrado AVL: aplicar el mismo rebalanceo (`_upd` + rotaciones) al retornar de cada llamada recursiva de `delete`.

### 8.4 Árbol de Segmentos (rangos + actualización)
```python
class SegmentTree:
    """Consulta de rango [l, r) y actualización puntual en O(log n).
    `op` debe ser asociativa (suma, min, max, gcd...); `identity` su neutro."""

    def __init__(self, data: List[Any], op=lambda a, b: a + b, identity=0):
        self.n, self.op, self.identity = len(data), op, identity
        self.t = [identity] * (2 * self.n)
        self.t[self.n:] = list(data)
        for i in range(self.n - 1, 0, -1):
            self.t[i] = op(self.t[2 * i], self.t[2 * i + 1])

    def update(self, i: int, value: Any) -> None:
        i += self.n
        self.t[i] = value
        while i > 1:
            i //= 2
            self.t[i] = self.op(self.t[2 * i], self.t[2 * i + 1])

    def query(self, l: int, r: int) -> Any:
        left, right = self.identity, self.identity
        l += self.n; r += self.n
        while l < r:
            if l & 1:
                left = self.op(left, self.t[l]); l += 1
            if r & 1:
                r -= 1; right = self.op(self.t[r], right)
            l >>= 1; r >>= 1
        return self.op(left, right)
```

### 8.5 Behavior Tree asíncrono (Composite)
```python
from abc import ABC, abstractmethod
from enum import Enum


class Status(Enum):
    SUCCESS = 1
    FAILURE = 2
    RUNNING = 3


class BTNode(ABC):
    @abstractmethod
    async def tick(self, ctx: dict) -> Status: ...


class Action(BTNode):
    def __init__(self, fn: Callable[[dict], Awaitable[Status]]):
        self.fn = fn

    async def tick(self, ctx: dict) -> Status:
        return await self.fn(ctx)


class Sequence(BTNode):
    """AND lógico: falla/continúa en el primer hijo que no sea SUCCESS."""
    def __init__(self, *children: BTNode):
        self.children = list(children)

    async def tick(self, ctx: dict) -> Status:
        for c in self.children:
            s = await c.tick(ctx)
            if s is not Status.SUCCESS:
                return s
        return Status.SUCCESS


class Selector(BTNode):
    """OR lógico: se detiene en el primer hijo que no sea FAILURE."""
    def __init__(self, *children: BTNode):
        self.children = list(children)

    async def tick(self, ctx: dict) -> Status:
        for c in self.children:
            s = await c.tick(ctx)
            if s is not Status.FAILURE:
                return s
        return Status.FAILURE
```

---

## 9. Caso de Estudio Resuelto (ejemplo): Historial de Conversación Ramificado
**Brief:** un agente de IA guarda cada mensaje como nodo; el usuario puede *bifurcar* desde cualquier mensaje y deshacer/rehacer. Raíz = sesión; hoja = último mensaje de cada rama.

```python
class ConversationTree:
    def __init__(self, session_id: str = "session"):
        self.tree = Tree(session_id, {"role": "system", "text": "inicio"})
        self.history = History()
        self._counter = 0

    def say(self, parent_id: str, role: str, text: str) -> str:
        self._counter += 1
        node_id = f"m{self._counter}"
        self.history.run(AddNode(self.tree, parent_id, node_id, {"role": role, "text": text}))
        return node_id

    def branch_context(self, leaf_id: str) -> List[dict]:
        """Contexto que se enviaría al LLM: ruta raíz→hoja."""
        node = self.tree.get(leaf_id)
        ids, n = [], node
        while n is not None:
            ids.append(n)
            n = n.parent
        return [x.data for x in reversed(ids)]

    def active_branches(self) -> List[str]:
        return [n.node_id for n in self.tree.leaves()]
```

---

## 10. Pruebas y Verificación (ejecutables)
```python
async def _demo_and_tests() -> None:
    # --- núcleo N-ario ---
    t = Tree("root", "R")
    t.add("root", "a"); t.add("root", "b"); t.add("a", "a1"); t.add("a", "a2"); t.add("b", "b1")
    assert [n.node_id for n in t.bfs()] == ["root", "a", "b", "a1", "a2", "b1"]
    assert [n.node_id for n in t.dfs()] == ["root", "a", "a1", "a2", "b", "b1"]
    assert [n.node_id for n in t.dfs(order="post")] == ["a1", "a2", "a", "b1", "b", "root"]
    assert t.get("a2").path() == ["root", "a", "a2"] and t.height() == 2
    t.validate()

    t.move("b1", "a")
    assert t.get("b1").parent.node_id == "a"
    try:
        t.move("a", "a1"); raise SystemExit("debió fallar")
    except InvalidOperationError:
        pass
    t.validate()

    t2 = Tree.from_dict(t.to_dict()); t2.validate()
    assert [n.node_id for n in t2.bfs()] == [n.node_id for n in t.bfs()]

    # --- asincronía ---
    visited: List[str] = []
    async def visit(n: Node) -> None:
        await asyncio.sleep(0.01); visited.append(n.node_id)
    await t.traverse_async(visit, concurrency=3)
    assert set(visited) == {n.node_id for n in t.bfs()}

    # --- undo/redo ---
    h = History()
    h.run(AddNode(t, "root", "z")); h.run(RemoveNode(t, "a"))
    assert "a" not in t and "a1" not in t
    h.undo(); assert "a1" in t and [c.node_id for c in t.root.children][:1] == ["a"]
    h.undo(); assert "z" not in t
    h.redo(); assert "z" in t
    t.validate()

    # --- AVL: 1..1000 insertados en orden NO degenera ---
    avl = AVLTree()
    for k in range(1, 1001): avl.insert(k)
    assert avl.root.height <= 11 and avl.inorder() == list(range(1, 1001)) and avl.contains(500)

    # --- Segmentos ---
    st = SegmentTree([5, 3, 8, 6, 2, 7])
    assert st.query(1, 4) == 17
    st.update(2, 10); assert st.query(1, 4) == 19
    mn = SegmentTree([5, 3, 8, 6], op=min, identity=float("inf"))
    assert mn.query(0, 4) == 3

    # --- Behavior Tree ---
    async def ok(ctx): ctx["log"].append("ok"); return Status.SUCCESS
    async def fail(ctx): ctx["log"].append("fail"); return Status.FAILURE
    ctx = {"log": []}
    bt = Selector(Sequence(Action(ok), Action(fail), Action(ok)), Action(ok))
    assert await bt.tick(ctx) is Status.SUCCESS and ctx["log"] == ["ok", "fail", "ok"]

    # --- caso de estudio ---
    c = ConversationTree()
    m1 = c.say("session", "user", "Hola")
    m2 = c.say(m1, "assistant", "¿En qué ayudo?")
    m3 = c.say(m1, "assistant", "Hola, dime")   # bifurcación
    assert set(c.active_branches()) == {m2, m3}
    assert [x["text"] for x in c.branch_context(m3)] == ["inicio", "Hola", "Hola, dime"]
    c.history.undo(); assert m3 not in c.tree
    c.tree.validate()
    print("TODAS LAS PRUEBAS PASARON")


if __name__ == "__main__":
    asyncio.run(_demo_and_tests())
```

---

## 11. Rendimiento, Escalabilidad y Persistencia
* **Memoria:** usar `__slots__` en nodos masivos; guardar datos pesados fuera del nodo (referencias/ids).
* **Profundidad:** si h ≈ n (árbol degenerado) → migrar a AVL/Rojo-Negro o rediseñar claves.
* **Disco:** > RAM → Árbol B+ (o SQLite/LMDB); serializar por **lotes** y no nodo a nodo.
* **Concurrencia:** `asyncio` para E/S (LLM, red); para CPU intensivo usar `multiprocessing`. Con múltiples escritores, proteger mutaciones con `asyncio.Lock`.
* **Evitar N+1:** procesar por niveles (`gather`) y limitar con `Semaphore`.
* **Medir antes de optimizar:** `timeit`, `cProfile`, `tracemalloc`.

## 12. Errores Comunes (checklist de revisión)
- [ ] Recursión sin límite en árboles profundos → usar pila explícita.
- [ ] `list.pop(0)` como cola → usar `deque`.
- [ ] Mutar `children`/`parent` fuera del gestor → rompe invariantes.
- [ ] Mover un nodo dentro de su propio subárbol (ciclo).
- [ ] IDs duplicados o índice desincronizado tras `detach`/`attach`.
- [ ] Olvidar rebalancear/actualizar alturas en AVL tras borrar.
- [ ] Usar Segmentos con operación no asociativa.
- [ ] No limpiar la pila *redo* al ejecutar una acción nueva.
- [ ] Bloquear el event loop con trabajo síncrono pesado dentro de una corrutina.

---

## 13. Flujo de Trabajo del Agente al Usar esta Skill
1. **Recibir el caso de estudio** → completar el brief (Fase 0); declarar supuestos.
2. **Definir jerarquía e invariantes** (Fase 1) y mostrarlas en un diagrama ASCII o Mermaid.
3. **Elegir la estructura** con la matriz (Fase 2) y **justificar** con complejidades.
4. **Elegir estructuras de soporte** (Fase 3).
5. **Generar el proyecto modular** (Sección 7) reutilizando las plantillas de la Sección 8 y adaptando `Node.data` y las reglas de dominio.
6. **Escribir pruebas** de invariantes y operaciones (Sección 10) y ejecutarlas.
7. **Entregar:** código, README con decisiones de diseño, tabla de complejidades y posibles extensiones.

### Plantilla de entrega (formato de respuesta)
```
1. Resumen del caso y supuestos
2. Jerarquía (raíz, subraíces, hojas) + invariantes
3. Estructura elegida y justificación (tabla de complejidades)
4. Estructuras de soporte
5. Código modular
6. Pruebas ejecutadas y resultados
7. Limitaciones y evolución futura
```
