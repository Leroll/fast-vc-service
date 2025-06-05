"""Command line interface."""
import click
import sys
from pathlib import Path

# add project root to sys.path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(project_root))
    
@click.group()
def cli():
    """Fast Voice Conversion Service CLI."""
    pass

@cli.command()
@click.option("--host", default="0.0.0.0", help="Host to bind to")
@click.option("--port", default=8042, type=int, help="Port to bind to")
def serve(host: str, port: int):
    """Start the FastAPI server."""
    from .app import main
    main(host=host, port=port)

@cli.command()
def version():
    """Show version information."""
    from . import __version__
    click.echo(click.style(f"🎤 Fast VC Service ", fg="cyan", bold=True) + 
               click.style(f"v{__version__}", fg="green", bold=True))
 
if __name__ == "__main__":
    cli()