"""Command line interface."""
import click
import sys
import signal
import os
import psutil
import json
import time
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
@click.option("--workers", default=2, type=int, help="Number of worker processes")
def serve(host: str, port: int, workers: int):
    """Start the FastAPI server."""
    pid_file = get_pid_file()
    
    # check if service is already running
    if pid_file.exists():
        try:
            with open(pid_file, "r") as f:
                existing_info = json.load(f)
            # 检查主进程是否存在
            if psutil.pid_exists(existing_info["master_pid"]):
                click.echo(click.style(f"❌ Service already running (Master PID: {existing_info['master_pid']})", fg="red"))
                return
            else:
                pid_file.unlink()
        except (json.JSONDecodeError, KeyError, FileNotFoundError):
            pid_file.unlink()
    
    # 保存服务信息
    service_info = {
        "master_pid": os.getpid(),
        "host": host,
        "port": port,
        "workers": workers,
        "start_time": time.time()
    }
    with open(pid_file, "w") as f:
        json.dump(service_info, f)
    click.echo(click.style(f"📝 Service info saved to: {pid_file}", fg="cyan"))
    
    # start server
    try:
        from .app import main
        main(host=host, port=port, workers=workers)
    finally:
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
        
        master_pid = service_info["master_pid"]
        
        if not psutil.pid_exists(master_pid):
            click.echo(click.style("❌ Master process not found", fg="red"))
            pid_file.unlink()
            return
        
        # 获取主进程和所有子进程
        try:
            master_process = psutil.Process(master_pid)
            all_processes = [master_process] + master_process.children(recursive=True)
            
            signal_type = signal.SIGTERM if force else signal.SIGINT
            signal_name = "SIGTERM" if force else "SIGINT"
            
            # 停止所有进程
            for proc in all_processes:
                try:
                    proc.send_signal(signal_type)
                    click.echo(click.style(f"📤 Sent {signal_name} to PID {proc.pid}", fg="cyan"))
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            click.echo(click.style("✅ Shutdown signals sent to all processes", fg="green"))
            
        except psutil.NoSuchProcess:
            click.echo(click.style("❌ Process not found", fg="red"))
        
        # 清理文件
        if pid_file.exists():
            pid_file.unlink()
            click.echo(click.style("🧹 Cleaned up service info file", fg="cyan"))
            
    except Exception as e:
        click.echo(click.style(f"❌ Error stopping service: {e}", fg="red"))

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
        
        master_pid = service_info["master_pid"]
        host = service_info["host"]
        port = service_info["port"]
        workers = service_info.get("workers", 1)
        
        if psutil.pid_exists(master_pid):
            # 检查所有相关进程
            try:
                master_process = psutil.Process(master_pid)
                children = master_process.children(recursive=True)
                
                click.echo(click.style(f"✅ Service running on {host}:{port}", fg="green"))
                click.echo(click.style(f"📊 Master PID: {master_pid}, Workers: {workers}", fg="cyan"))
                click.echo(click.style(f"🔧 Active processes: {len(children) + 1}", fg="cyan"))
                
                # 显示进程详情
                for i, child in enumerate(children, 1):
                    try:
                        click.echo(click.style(f"   Worker {i}: PID {child.pid}", fg="white"))
                    except psutil.NoSuchProcess:
                        click.echo(click.style(f"   Worker {i}: Process ended", fg="yellow"))
                        
            except psutil.NoSuchProcess:
                click.echo(click.style("❌ Master process not found", fg="red"))
                pid_file.unlink()
        else:
            click.echo(click.style("❌ Service not running (stale info file)", fg="red"))
            pid_file.unlink()
            
    except Exception as e:
        click.echo(click.style(f"❌ Error checking status: {e}", fg="red"))

@cli.command("clean")
@click.option("--confirm", "-y", is_flag=True, help="Skip confirmation prompt")
def clean(confirm: bool):
    """Clean log files in the logs/ directory."""
    log_dir = PROJECT_ROOT / "logs"
    
    # 检查logs目录是否存在
    if not log_dir.exists():
        click.echo(click.style(f"❌ Log directory does not exist: {log_dir}", fg="red"))
        return
    
    # 查找所有.log文件
    log_files = list(log_dir.glob("*.log*"))
    
    if not log_files:
        click.echo(click.style("✅ No log files found to delete", fg="green"))
        return
    
    # 显示要删除的文件
    click.echo(click.style(f"📁 Found {len(log_files)} log file(s) to delete:", fg="cyan"))
    for log_file in log_files:
        click.echo(f"  - {log_file.relative_to(PROJECT_ROOT)}")
    
    # 确认删除
    if not confirm:
        if not click.confirm(click.style("❓ Do you want to delete these files?", fg="yellow")):
            click.echo(click.style("❌ Operation cancelled", fg="red"))
            return
    
    # 删除文件
    deleted_count = 0
    for log_file in log_files:
        try:
            log_file.unlink()
            click.echo(click.style(f"🗑️  Deleted: {log_file.relative_to(PROJECT_ROOT)}", fg="green"))
            deleted_count += 1
        except Exception as e:
            click.echo(click.style(f"❌ Failed to delete {log_file.name}: {e}", fg="red"))
    
    click.echo(click.style(f"✅ Successfully deleted {deleted_count} log file(s)", fg="green"))

@cli.command()
def version():
    """Show version information."""
    from . import __version__
    click.echo(click.style(f"🎤 Fast VC Service ", fg="cyan", bold=True) + 
               click.style(f"v{__version__}", fg="green", bold=True))
 
if __name__ == "__main__":
    cli()