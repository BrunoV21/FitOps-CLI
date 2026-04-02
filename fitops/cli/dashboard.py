from __future__ import annotations

import typer

app = typer.Typer(no_args_is_help=True)


@app.command("serve")
def serve(
    host: str = typer.Option(
        "127.0.0.1", "--host", help="Host to bind the dashboard server to."
    ),
    port: int = typer.Option(
        8888, "--port", help="Port to bind the dashboard server to."
    ),
    no_open: bool = typer.Option(
        False, "--no-open", help="Don't open the browser automatically."
    ),
) -> None:
    """Launch the FitOps local dashboard server."""
    try:
        import uvicorn
    except ImportError:
        typer.echo(
            "uvicorn is required. Run: pip install 'fitops-cli[dashboard]'", err=True
        )
        raise typer.Exit(1)

    from fitops.db.migrations import init_db

    init_db()

    url = f"http://{host}:{port}"
    typer.echo(f"Starting FitOps Dashboard at {url}")

    if not no_open:
        import threading
        import time
        import webbrowser

        def _open():
            time.sleep(0.8)
            webbrowser.open(url)

        threading.Thread(target=_open, daemon=True).start()

    from fitops.dashboard.server import create_app

    uvicorn.run(create_app(port=port), host=host, port=port, log_level="info")
