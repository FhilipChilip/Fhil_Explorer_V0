import os
import tempfile

from file_explorer import (
    DuplicateNameError, FileExplorer, InvalidPathError, NodeKind,
    NotAFolderError, PathNotFoundError,
)


def build() -> FileExplorer:
    ex = FileExplorer("my-project")
    ex.add_file("/my-project/README.md", 100)
    ex.add_file("/my-project/src/index.py", 200, parents=True)
    ex.add_file("/my-project/src/utils/helpers.py", 50, parents=True)
    ex.add_file("/my-project/assets/style.css", 30, parents=True)
    ex.add_file("/my-project/tests/test_main.py", 70, parents=True)
    ex.add_folder("/my-project/docs")  # vacía
    return ex


def test_count_files():
    ex = build()
    assert ex.count_files() == 5
    assert ex.count_files("/my-project/src") == 2
    assert ex.count_files("/my-project/docs") == 0      # carpeta vacía no es archivo
    assert ex.count_files("/my-project/README.md") == 1  # un archivo cuenta como 1
    assert ex.count_folders() == 5                        # src, utils, assets, tests, docs
    assert ex.total_size() == 450


def test_print_tree_style():
    expected = "\n".join([
        "my-project/",
        "├── assets/",
        "│   └── style.css",
        "├── docs/",
        "├── src/",
        "│   ├── utils/",
        "│   │   └── helpers.py",
        "│   └── index.py",
        "├── tests/",
        "│   └── test_main.py",
        "└── README.md",
    ])
    assert build().render_structure() == expected


def test_print_indent_style_and_options():
    ex = build()
    out = ex.render_structure(style="indent", max_depth=1)
    assert out.splitlines() == [
        "my-project/", "  assets/", "  docs/", "  src/", "  tests/", "  README.md"
    ]
    only_dirs = ex.render_structure(show_files=False)
    assert "index.py" not in only_dirs and "utils/" in only_dirs
    assert ex.render_structure("/my-project/src").splitlines()[0] == "src/"


def test_print_returns_and_prints(capsys):
    text = build().print_folder_structure(style="indent")
    assert capsys.readouterr().out.strip() == text


def test_find_remove_exists():
    ex = build()
    assert sorted(ex.find("*.py")) == [
        "/my-project/src/index.py",
        "/my-project/src/utils/helpers.py",
        "/my-project/tests/test_main.py",
    ]
    assert ex.find("src", NodeKind.FOLDER) == ["/my-project/src"]
    ex.remove("/my-project/src")
    assert not ex.exists("/my-project/src/index.py") and ex.count_files() == 3
    ex.validate()


def test_errors():
    ex = build()
    for bad, exc in [
        (lambda: ex.add_file("/my-project/README.md"), DuplicateNameError),
        (lambda: ex.add_file("/my-project/new/a.txt"), PathNotFoundError),
        (lambda: ex.add_file("/my-project/README.md/x.txt", parents=True), NotAFolderError),
        (lambda: ex.add_file("relative/a.txt"), InvalidPathError),
        (lambda: ex.add_file("/my-project/../a.txt"), InvalidPathError),
        (lambda: ex.remove("/my-project"), InvalidPathError),
        (lambda: ex.get("/other/a"), PathNotFoundError),
        (lambda: ex.count_files("/my-project/missing"), PathNotFoundError),
    ]:
        try:
            bad()
        except exc:
            continue
        raise AssertionError(f"should have raised {exc.__name__}")


def test_deep_tree_no_recursion_error():
    ex = FileExplorer("r")
    deep = "/r" + "/d" * 3000 + "/f.txt"
    ex.add_file(deep, 1, parents=True)
    assert ex.count_files() == 1 and ex.count_folders() == 3000
    assert len(ex.render_structure().splitlines()) == 3002
    ex.validate()


def test_from_disk_and_to_dict():
    with tempfile.TemporaryDirectory() as tmp:
        base = os.path.join(tmp, "proj")
        os.makedirs(os.path.join(base, "src", "pkg"))
        os.makedirs(os.path.join(base, "empty"))
        for rel in ("main.py", "src/a.py", "src/pkg/b.py"):
            with open(os.path.join(base, rel), "w") as f:
                f.write("x" * 10)
        ex = FileExplorer.from_disk(base)
        assert ex.root.name == "proj" and ex.count_files() == 3
        assert ex.total_size() == 30 and ex.count_folders() == 3
        ex.validate()
        d = ex.to_dict()
        assert d["type"] == "folder" and {c["name"] for c in d["children"]} == {
            "main.py", "src", "empty"}


if __name__ == "__main__":
    import pytest, sys
    sys.exit(pytest.main([__file__, "-q"]))
