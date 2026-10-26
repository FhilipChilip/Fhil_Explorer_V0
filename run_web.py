"""Abre la interfaz visual (web/explorer.html) en tu navegador."""
import pathlib
import webbrowser

path = pathlib.Path(__file__).resolve().parent / "web" / "explorer.html"
print(f"Opening {path}")
webbrowser.open(path.as_uri())
