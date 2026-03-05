#!/usr/bin/env python
"""Convert .ipynb to PDF.

Default backend:
- latex: notebook -> .tex (nbconvert) -> xelatex (2 passes)

Optional backend:
- edge: notebook -> html (nbconvert) -> Edge headless print
"""

from __future__ import annotations

import argparse
import http.server
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Sequence
from urllib.parse import quote


def run(cmd: Sequence[str], cwd: Path | None = None, timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(cmd),
        check=True,
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
        timeout=timeout,
    )


def patch_latex(text: str) -> str:
    # Pandoc can emit LTcaptype=none, which fails on some TeX setups.
    return text.replace(r"{\def\LTcaptype{none} % do not increment counter", r"{\def\LTcaptype{table} % patched")


def convert_with_latex(notebook: Path, output_pdf: Path, keep_tmp: bool = False) -> Path:
    with tempfile.TemporaryDirectory(prefix="nb2pdf_tex_") as tmp_str:
        tmpdir = Path(tmp_str)
        stem = "document"

        run(
            [
                sys.executable,
                "-m",
                "jupyter",
                "nbconvert",
                "--to",
                "latex",
                str(notebook),
                "--output",
                stem,
                "--output-dir",
                str(tmpdir),
            ],
            timeout=300,
        )

        tex_path = tmpdir / f"{stem}.tex"
        if not tex_path.exists():
            raise RuntimeError(f"No se generó .tex esperado: {tex_path}")

        tex_path.write_text(
            patch_latex(tex_path.read_text(encoding="utf-8", errors="replace")),
            encoding="utf-8",
        )

        # Two passes for references/tables.
        for _ in range(2):
            run(
                ["xelatex", "-interaction=nonstopmode", "-halt-on-error", tex_path.name],
                cwd=tmpdir,
                timeout=600,
            )

        generated_pdf = tmpdir / f"{stem}.pdf"
        if not generated_pdf.exists():
            raise RuntimeError(f"No se generó PDF esperado: {generated_pdf}")

        output_pdf.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(generated_pdf, output_pdf)

        if keep_tmp:
            save_tmp = output_pdf.with_suffix(".latex_tmp")
            if save_tmp.exists():
                shutil.rmtree(save_tmp)
            shutil.copytree(tmpdir, save_tmp)

    return output_pdf


def find_edge_executable() -> str:
    env_path = os.environ.get("EDGE_PATH")
    candidates = [env_path] if env_path else []
    candidates.extend(
        [
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        ]
    )
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    raise FileNotFoundError("No se encontró msedge.exe. Define EDGE_PATH o instala Edge.")


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def print_with_edge(edge_exe: str, url: str, output_pdf: Path, wait_ms: int) -> None:
    base_flags = [
        "--disable-gpu",
        "--run-all-compositor-stages-before-draw",
        f"--virtual-time-budget={wait_ms}",
        f"--print-to-pdf={output_pdf.resolve()}",
    ]
    variants = [
        ["--headless=new", "--no-pdf-header-footer"],
        ["--headless", "--no-pdf-header-footer"],
        ["--headless=new"],
        ["--headless"],
    ]

    last_error: Exception | None = None
    for variant in variants:
        cmd = [edge_exe, *variant, *base_flags, url]
        try:
            run(cmd, timeout=max(120, wait_ms // 1000 + 60))
            return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
    raise RuntimeError("Edge no pudo generar el PDF con ninguna variante de flags") from last_error


def convert_with_edge(notebook: Path, output_pdf: Path, wait_ms: int) -> Path:
    edge_exe = find_edge_executable()
    with tempfile.TemporaryDirectory(prefix="nb2pdf_html_") as tmp_str:
        tmpdir = Path(tmp_str)
        html_name = "document.html"
        run(
            [
                sys.executable,
                "-m",
                "jupyter",
                "nbconvert",
                "--to",
                "html",
                str(notebook),
                "--output",
                html_name,
                "--output-dir",
                str(tmpdir),
            ],
            timeout=300,
        )

        port = free_port()
        handler = lambda *a, **kw: http.server.SimpleHTTPRequestHandler(*a, directory=str(tmpdir), **kw)  # noqa: E731
        server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        try:
            url = f"http://127.0.0.1:{port}/{quote(html_name)}"
            output_pdf.parent.mkdir(parents=True, exist_ok=True)
            print_with_edge(edge_exe, url, output_pdf, wait_ms)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    return output_pdf


def main() -> int:
    parser = argparse.ArgumentParser(description="Convierte notebook .ipynb a PDF")
    parser.add_argument("notebook", help="Ruta del notebook .ipynb")
    parser.add_argument("-o", "--output", help="Salida .pdf (default: mismo nombre)")
    parser.add_argument(
        "--backend",
        choices=["latex", "edge"],
        default="latex",
        help="Motor de conversión (default: latex)",
    )
    parser.add_argument(
        "--wait-ms",
        type=int,
        default=20000,
        help="Solo para backend=edge: tiempo virtual para JS/MathJax",
    )
    parser.add_argument(
        "--keep-tmp",
        action="store_true",
        help="Solo para backend=latex: guarda carpeta temporal de compilación",
    )
    args = parser.parse_args()

    notebook = Path(args.notebook).resolve()
    if not notebook.exists():
        raise FileNotFoundError(f"No existe el notebook: {notebook}")

    output_pdf = Path(args.output).resolve() if args.output else notebook.with_suffix(".pdf")

    if args.backend == "latex":
        convert_with_latex(notebook, output_pdf, keep_tmp=args.keep_tmp)
    else:
        convert_with_edge(notebook, output_pdf, wait_ms=args.wait_ms)

    size_kb = output_pdf.stat().st_size / 1024
    print(f"PDF generado: {output_pdf} ({size_kb:.1f} KB) con backend={args.backend}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
