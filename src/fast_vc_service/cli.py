"""Command line interface."""
import click

from .app import main

@click.group()
@click.version_option()
def cli():
    """Fast Voice Conversion Service CLI."""
    pass

@cli.command()
@click.option("--host", default="0.0.0.0", help="Host to bind to")
@click.option("--port", default=8042, type=int, help="Port to bind to")
def serve(host: str, port: int):
    """Start the FastAPI server."""
    main(host=host, port=port)

@cli.command()
def version():
    """Show version information."""
    from . import __version__
    click.echo(f"Fast VC Service version {__version__}")
 
if __name__ == "__main__":
    cli()