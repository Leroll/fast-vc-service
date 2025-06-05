"""Command line interface."""
import click
import sys
import signal
import os
import psutil
import json
from pathlib import Path

# add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(PROJECT_ROOT))

def get_pid_file() -> Path:
    """Get the PID file path in project temp directory."""
    temp_dir = PROJECT_ROOT / "temp"
    temp_dir.mkdir(exist_ok=True)  # 确保temp文件夹存在
    return temp_dir / "fast_vc_service.json"
    
@click.group()
def cli():
    """Fast Voice Conversion Service CLI."""
    pass

@cli.command()
@click.option("--host", default="0.0.0.0", help="Host to bind to")
@click.option("--port", default=8042, type=int, help="Port to bind to")
def serve(host: str, port: int):
    """Start the FastAPI server."""
    pid_file = get_pid_file()
    
    # check if service is already running
    if pid_file.exists():
        try:
            with open(pid_file, "r") as f:
                existing_info = json.load(f)
            if psutil.pid_exists(existing_info["pid"]):
                click.echo(click.style(f"❌ Service already running (PID: {existing_info['pid']})", fg="red"))
                return
            else:
                # clean up stale PID file
                pid_file.unlink()
        except (json.JSONDecodeError, KeyError, FileNotFoundError):
            pid_file.unlink()
    
    # save current service info
    service_info = {
        "pid": os.getpid(),
        "host": host,
        "port": port
    }
    with open(pid_file, "w") as f:
        json.dump(service_info, f)
    click.echo(click.style(f"📝 Service info saved to: {pid_file}", fg="cyan"))
    
    # start server
    try:
        from .app import main
        main(host=host, port=port)
    finally:
        # clean up PID file on exit
        if pid_file.exists():
            pid_file.unlink()
            click.echo(click.style("🧹 Cleaned up service info file", fg="cyan"))

@cli.command()
@click.option("--force", "-f", is_flag=True, help="Force shutdown using system signal")
def stop(force: bool):
    """Stop the running FastAPI server."""
    pid_file = get_pid_file()
    
    if not pid_file.exists():
        click.echo(click.style("❌ No service info found", fg="red"))
        return
    
    try:
        with open(pid_file, "r") as f:
            service_info = json.load(f)
        
        pid = service_info["pid"]
        host = service_info["host"]
        port = service_info["port"]
        
        # 检查进程是否还在运行
        if not psutil.pid_exists(pid):
            click.echo(click.style("❌ Service process not found", fg="red"))
            pid_file.unlink()
            return
        
        if force:
            # 直接发送SIGTERM信号
            os.kill(pid, signal.SIGTERM)
            click.echo(click.style("✅ Service stopped forcefully", fg="green"))
        else:
            # 尝试优雅关闭 - 直接发送信号而不是HTTP请求
            try:
                os.kill(pid, signal.SIGINT)  # 发送中断信号
                click.echo(click.style("✅ Shutdown signal sent to service", fg="green"))
            except ProcessLookupError:
                click.echo(click.style("❌ Process not found", fg="red"))
        
        # 清理文件
        if pid_file.exists():
            pid_file.unlink()
            click.echo(click.style("🧹 Cleaned up service info file", fg="cyan"))
            
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        click.echo(click.style(f"❌ Invalid service info file: {e}", fg="red"))
        if pid_file.exists():
            pid_file.unlink()
    except PermissionError:
        click.echo(click.style("❌ Permission denied to stop service", fg="red"))

@cli.command()
def status():
    """Check service status."""
    pid_file = get_pid_file()
    
    click.echo(click.style(f"📝 PID file location: {pid_file}", fg="cyan"))
    
    if not pid_file.exists():
        click.echo(click.style("❌ No service info found", fg="red"))
        return
    
    try:
        with open(pid_file, "r") as f:
            service_info = json.load(f)
        
        pid = service_info["pid"]
        host = service_info["host"]
        port = service_info["port"]
        
        if psutil.pid_exists(pid):
            click.echo(click.style(f"✅ Service running on {host}:{port} (PID: {pid})", fg="green"))
        else:
            click.echo(click.style("❌ Service not running (stale info file)", fg="red"))
            pid_file.unlink()
            
    except (json.JSONDecodeError, KeyError) as e:
        click.echo(click.style(f"❌ Invalid service info: {e}", fg="red"))

@cli.command()
def version():
    """Show version information."""
    from . import __version__
    click.echo(click.style(f"🎤 Fast VC Service ", fg="cyan", bold=True) + 
               click.style(f"v{__version__}", fg="green", bold=True))
 
if __name__ == "__main__":
    cli()