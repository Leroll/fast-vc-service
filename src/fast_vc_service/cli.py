"""Command line interface."""
import click
import sys
import signal
import os
import psutil
import json
import time
from pathlib import Path

from fast_vc_service.config import Config

# add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(PROJECT_ROOT))

def get_port_from_config(config_path: str = None) -> int:
    """Get port number from config file."""
    # 临时设置环境变量来读取配置
    old_config_path = os.environ.get("CONFIG_PATH")
    if config_path:
        os.environ["CONFIG_PATH"] = config_path
    
    try:
        cfg = Config()
        port = cfg.get_config().app.port
        return port
    finally:
        # 恢复原来的环境变量
        if old_config_path:
            os.environ["CONFIG_PATH"] = old_config_path
        elif "CONFIG_PATH" in os.environ:
            del os.environ["CONFIG_PATH"]

def get_pid_file(port: int = None) -> Path:
    """Get the PID file path based on port number."""
    temp_dir = PROJECT_ROOT / "temp"
    temp_dir.mkdir(exist_ok=True)
    
    if port:
        return temp_dir / f"fast_vc_service_port_{port}.json"
    else:
        return temp_dir / "fast_vc_service.json"

def get_connection_file(port: int = None) -> Path:
    """Get the connection file path based on port number."""
    temp_dir = PROJECT_ROOT / "temp"
    temp_dir.mkdir(exist_ok=True)
    
    if port:
        return temp_dir / f"connections_port_{port}.json"
    else:
        return temp_dir / "connections.json"
    
@click.group()
def cli():
    """Fast Voice Conversion Service CLI."""
    pass

@cli.command()
@click.option('--config', '-c', 'config_path', 
              help='Path to configuration file')
def serve(config_path):
    """Start the FastAPI server."""
    # 如果指定了配置文件路径，设置环境变量
    if config_path:
        os.environ["CONFIG_PATH"] = config_path
        click.echo(click.style(f"📄 Using config file: {config_path}", fg="cyan"))
    
    cfg = Config()
    app_config = cfg.get_config().app
    port = app_config.port
    
    pid_file = get_pid_file(port)
    
    click.echo(click.style(f"🌐 Service will run on port: {port}", fg="magenta"))
    click.echo(click.style(f"📝 PID file: {pid_file}", fg="cyan"))
    
    # check if service is already running
    if pid_file.exists():
        try:
            with open(pid_file, "r") as f:
                existing_info = json.load(f)
            # 检查主进程是否存在
            if psutil.pid_exists(existing_info["master_pid"]):
                click.echo(click.style(f"❌ Service already running on port {port} (Master PID: {existing_info['master_pid']})", fg="red"))
                return
            else:
                pid_file.unlink()
        except (json.JSONDecodeError, KeyError, FileNotFoundError):
            pid_file.unlink()
    
    # 保存服务信息
    service_info = {
        "master_pid": os.getpid(),
        "host": app_config.host,
        "port": port,
        "workers": app_config.workers,
        "start_time": time.time(),
        "config_path": cfg.config_path  # 记录使用的配置文件路径
    }
    with open(pid_file, "w") as f:
        json.dump(service_info, f)
    click.echo(click.style(f"📝 Service info saved to: {pid_file}", fg="cyan"))
    
    # start server
    try:
        from .app import main
        main()
    finally:
        if pid_file.exists():
            pid_file.unlink()
            click.echo(click.style("🧹 Cleaned up service info file", fg="cyan"))
        
        connection_file = get_connection_file(port)
        if connection_file.exists():
            connection_file.unlink()
            click.echo(click.style("🧹 Cleaned up connection info file", fg="cyan"))

@cli.command()
@click.option("--force", "-f", is_flag=True, help="Force shutdown using system signal")
@click.option('--config', '-c', 'config_path', 
              help='Path to configuration file (to identify service by its port)')
@click.option('--port', '-p', type=int,
              help='Port number (direct port specification)')
def stop(force: bool, config_path: str, port: int):
    """Stop the running FastAPI server. Stops all services by default."""
    
    # 如果没有指定 config 或 port，默认停止所有服务
    if not config_path and not port:
        # 停止所有服务
        temp_dir = PROJECT_ROOT / "temp"
        pid_files = list(temp_dir.glob("fast_vc_service_port_*.json"))
        
        if not pid_files:
            click.echo(click.style("❌ No running services found", fg="red"))
            return
        
        click.echo(click.style(f"🔍 Found {len(pid_files)} service(s) to stop", fg="cyan"))
        
        for pid_file in pid_files:
            # 从文件名提取端口号
            port_from_filename = pid_file.stem.replace("fast_vc_service_port_", "")
            click.echo(click.style(f"\n🛑 Stopping service on port: {port_from_filename}", fg="yellow"))
            _stop_service(pid_file, force)
        
        return
    
    # 确定要停止的服务端口
    if config_path:
        try:
            port = get_port_from_config(config_path)
            click.echo(click.style(f"📄 Read port {port} from config: {config_path}", fg="cyan"))
        except Exception as e:
            click.echo(click.style(f"❌ Failed to read port from config {config_path}: {e}", fg="red"))
            return
    elif port:
        click.echo(click.style(f"🌐 Using specified port: {port}", fg="cyan"))
    
    pid_file = get_pid_file(port)
    
    if not pid_file.exists():
        click.echo(click.style(f"❌ No service info found for port: {port}", fg="red"))
        return
    
    _stop_service(pid_file, force)

def _stop_service(pid_file: Path, force: bool):
    """Helper function to stop a specific service."""
    try:
        with open(pid_file, "r") as f:
            service_info = json.load(f)
        
        master_pid = service_info["master_pid"]
        port = service_info.get("port", "unknown")
        
        if not psutil.pid_exists(master_pid):
            click.echo(click.style(f"❌ Master process not found for port {port}", fg="red"))
            pid_file.unlink()
            return
        
        # 获取主进程和所有子进程
        try:
            master_process = psutil.Process(master_pid)
            all_processes = [master_process] + master_process.children(recursive=True)
            
            # 先尝试优雅关闭
            signal_type = signal.SIGTERM if force else signal.SIGINT
            signal_name = "SIGTERM" if force else "SIGINT"
            
            # 发送信号到所有进程
            for proc in all_processes:
                try:
                    if proc.is_running():
                        proc.send_signal(signal_type)
                        click.echo(click.style(f"📤 Sent {signal_name} to PID {proc.pid} (Port: {port})", fg="cyan"))
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            # 等待进程终止
            click.echo(click.style("⏳ Waiting for processes to terminate...", fg="yellow"))
            wait_timeout = 10 if not force else 5
            
            terminated = []
            for proc in all_processes:
                try:
                    proc.wait(timeout=wait_timeout)
                    terminated.append(proc.pid)
                    click.echo(click.style(f"✅ Process {proc.pid} terminated", fg="green"))
                except psutil.TimeoutExpired:
                    click.echo(click.style(f"⚠️  Process {proc.pid} did not terminate within {wait_timeout}s", fg="yellow"))
                except psutil.NoSuchProcess:
                    terminated.append(proc.pid)
                    click.echo(click.style(f"✅ Process {proc.pid} already terminated", fg="green"))
            
            # 如果有进程没有终止，使用 SIGKILL 强制杀死
            remaining_processes = []
            for proc in all_processes:
                try:
                    if proc.is_running():
                        remaining_processes.append(proc)
                except psutil.NoSuchProcess:
                    continue
            
            if remaining_processes:
                click.echo(click.style(f"🔨 Force killing {len(remaining_processes)} remaining processes...", fg="red"))
                for proc in remaining_processes:
                    try:
                        proc.kill()  # SIGKILL
                        click.echo(click.style(f"💀 Killed PID {proc.pid}", fg="red"))
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
                
                # 再次等待
                for proc in remaining_processes:
                    try:
                        proc.wait(timeout=3)
                    except (psutil.TimeoutExpired, psutil.NoSuchProcess):
                        continue
            
            # 最终检查
            still_running = []
            for proc in all_processes:
                try:
                    if proc.is_running():
                        still_running.append(proc.pid)
                except psutil.NoSuchProcess:
                    continue
            
            if still_running:
                click.echo(click.style(f"❌ Failed to stop processes: {still_running}", fg="red"))
            else:
                click.echo(click.style(f"✅ Service on port {port} terminated successfully", fg="green"))
            
        except psutil.NoSuchProcess:
            click.echo(click.style(f"❌ Process not found for port {port}", fg="red"))
        
        # 清理文件
        if pid_file.exists():
            pid_file.unlink()
            click.echo(click.style(f"🧹 Cleaned up service info file for port {port}", fg="cyan"))
            
    except Exception as e:
        click.echo(click.style(f"❌ Error stopping service: {e}", fg="red"))

@cli.command()
@click.option('--config', '-c', 'config_path', 
              help='Path to configuration file (to identify service by its port)')
@click.option('--port', '-p', type=int,
              help='Port number (direct port specification)')
def status(config_path: str, port: int):
    """Check service status. Shows all services by default."""
    
    # 如果没有指定 config 或 port，默认显示所有服务状态
    if not config_path and not port:
        # 显示所有服务状态
        temp_dir = PROJECT_ROOT / "temp"
        pid_files = list(temp_dir.glob("fast_vc_service_port_*.json"))
        
        if not pid_files:
            click.echo(click.style("❌ No running services found", fg="red"))
            return
        
        click.echo(click.style(f"🔍 Found {len(pid_files)} service(s):", fg="cyan"))
        
        for pid_file in pid_files:
            port_from_filename = pid_file.stem.replace("fast_vc_service_port_", "")
            click.echo(click.style(f"\n🌐 Service on port: {port_from_filename}", fg="magenta"))
            _show_service_status(pid_file)
        
        return
    
    # 确定要查看的服务端口
    if config_path:
        try:
            port = get_port_from_config(config_path)
            click.echo(click.style(f"📄 Read port {port} from config: {config_path}", fg="cyan"))
        except Exception as e:
            click.echo(click.style(f"❌ Failed to read port from config {config_path}: {e}", fg="red"))
            return
    elif port:
        click.echo(click.style(f"🌐 Using specified port: {port}", fg="cyan"))
    
    pid_file = get_pid_file(port)
    
    click.echo(click.style(f"🌐 Service port: {port}", fg="magenta"))
    click.echo(click.style(f"📝 PID file location: {pid_file}", fg="cyan"))
    
    if not pid_file.exists():
        click.echo(click.style(f"❌ No service info found for port: {port}", fg="red"))
        return
    
    _show_service_status(pid_file)

def _show_service_status(pid_file: Path):
    """Helper function to show status of a specific service."""
    try:
        with open(pid_file, "r") as f:
            service_info = json.load(f)
        
        master_pid = service_info["master_pid"]
        host = service_info["host"]
        port = service_info["port"]
        workers = service_info.get("workers", 1)
        config_path = service_info.get("config_path")
        
        if psutil.pid_exists(master_pid):
            # 检查所有相关进程
            try:
                master_process = psutil.Process(master_pid)
                all_processes = [master_process] + master_process.children(recursive=True)
                
                click.echo(click.style(f"✅ Service running on {host}:{port}", fg="green"))
                if config_path:
                    click.echo(click.style(f"📄 Config file: {config_path}", fg="magenta"))
                else:
                    click.echo(click.style(f"📄 Using default configuration", fg="magenta"))
                click.echo(click.style(f"📊 Master PID: {master_pid}, Workers: {workers}", fg="cyan"))
                click.echo(click.style(f"🔧 Active processes: {len(all_processes)}", fg="cyan"))
                
                # 显示进程详情
                for i, process in enumerate(all_processes, 1):
                    try:
                        click.echo(click.style(f"   Worker {i}: PID {process.pid}", fg="white"))
                    except psutil.NoSuchProcess:
                        click.echo(click.style(f"   Worker {i}: Process ended", fg="yellow"))
                        
            except psutil.NoSuchProcess:
                click.echo(click.style(f"❌ Master process not found for port {port}", fg="red"))
                pid_file.unlink()
        else:
            click.echo(click.style(f"❌ Service on port {port} not running (stale info file)", fg="red"))
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
    from . import __build_date__
    from . import __author__ 
    click.echo(click.style(f"🎤 Fast VC Service ", fg="cyan", bold=True) + 
               click.style(f"v{__version__}", fg="green", bold=True))
    click.echo(click.style(f"📅 Build Date: ", fg="cyan", bold=True) +
               click.style(f"{__build_date__}", fg="green", bold=True)),
    click.echo(click.style(f"👷 Author: ", fg="cyan", bold=True)+
               click.style(f"{__author__}", fg="green", bold=True))

if __name__ == "__main__":
    """
    Usage:
    
    # 启动服务 (Start Services)
    fast-vc serve                           # 使用默认配置启动服务
    fast-vc serve -c configs/prod.yaml     # 使用指定配置文件启动服务
    fast-vc serve -c configs/dev.yaml      # 使用不同配置文件启动另一个服务
    fast-vc serve --config configs/test.yaml  # 长选项形式
    
    # 查看状态 (Check Status)
    fast-vc status                          # 查看所有运行中的服务状态 (默认行为)
    fast-vc status -c configs/prod.yaml    # 通过配置文件查看特定服务状态
    fast-vc status -p 8042                 # 通过端口号查看特定服务状态
    fast-vc status --port 8043             # 长选项形式
    
    # 停止服务 (Stop Services)
    fast-vc stop                           # 停止所有运行中的服务 (默认行为)
    fast-vc stop -c configs/prod.yaml      # 通过配置文件停止特定服务
    fast-vc stop -p 8042                   # 通过端口号停止特定服务
    fast-vc stop -p 8043 --force           # 强制停止服务（使用SIGTERM）
    fast-vc stop -f                        # 强制停止所有服务
    
    # 清理日志 (Clean Logs)
    fast-vc clean                          # 清理日志文件（需要确认）
    fast-vc clean -y                       # 跳过确认直接清理日志文件
    fast-vc clean --confirm                # 长选项形式
    
    # 版本信息 (Version Info)
    fast-vc version                        # 显示版本信息
    
    # 帮助信息 (Help)
    fast-vc --help                         # 显示主要帮助信息
    fast-vc serve --help                   # 显示serve命令的帮助信息
    fast-vc stop --help                    # 显示stop命令的帮助信息
    fast-vc status --help                  # 显示status命令的帮助信息
    
    # 多服务实例管理示例 (Multi-Service Management Examples)
    # 1. 启动多个不同配置的服务
    fast-vc serve -c configs/prod.yaml     # 启动生产环境服务 (端口: 8042)
    fast-vc serve -c configs/dev.yaml      # 启动开发环境服务 (端口: 8043) 
    fast-vc serve -c configs/test.yaml     # 启动测试环境服务 (端口: 8044)
    
    # 2. 查看所有服务状态 (默认行为)
    fast-vc status
    
    # 3. 分别停止不同服务
    fast-vc stop -c configs/test.yaml      # 停止测试环境服务
    fast-vc stop -p 8043                   # 停止开发环境服务
    fast-vc stop -c configs/prod.yaml      # 停止生产环境服务
    
    # 4. 一键停止所有服务 (默认行为)
    fast-vc stop
    
    注意事项 (Notes):
    - 服务实例通过配置文件中的端口号进行区分
    - 每个端口只能运行一个服务实例
    - PID文件存储在 temp/fast_vc_service_port_{port}.json
    - 可以同时运行多个不同端口的服务实例
    - 使用 --force/-f 选项进行强制停止时会发送SIGTERM信号
    - stop 和 status 命令默认操作所有服务，只有指定 --port 或 --config 时才操作特定服务
    """
    cli()