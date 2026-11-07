import io
import json
import logging
import sys
import tarfile
import traceback
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Union
from enum import Enum
from pathlib import Path

import docker
from docker.errors import NotFound, APIError
from docker.models.containers import Container
import requests
from requests.exceptions import RequestException, Timeout, ConnectionError

logger = logging.getLogger(__name__)

SUPERSET_CONTAINER_NAME = "apache-superset"
SUPERSET_HEALTH_ENDPOINT = "http://localhost:8088/health"
SUPERSET_HEALTH_TIMEOUT = 10

ETL_CONTAINER_NAME = "swedish-funds-etl-pg"
DOCKER_CONNECTION_TIMEOUT = 5


class ContainerState(Enum):
    RUNNING = 'running'
    PAUSED = 'paused'
    EXITED = 'exited'
    RESTARTING = 'restarting'
    REMOVING = 'removing'
    DEAD = 'dead'
    UNKNOWN = 'unknown'


class HealthStatus(Enum):
    HEALTHY = 'healthy'
    UNHEALTHY = 'unhealthy'
    NO_HEALTHCHECK = 'no_healthcheck'
    UNKNOWN = 'unknown'


class TraceLevel(Enum):
    DEBUG = 'DEBUG'
    INFO = 'INFO'
    WARNING = 'WARNING'
    ERROR = 'ERROR'


class DockerAPITrace:
    def __init__(self):
        self.traces: List[Dict] = []
        self.boundary_violations: List[Dict] = []
        self.container_snapshots: Dict[str, Dict] = {}
    
    def log_api_call(self, level: TraceLevel, operation: str, 
                     container_name: str, request_context: Dict, 
                     response: Optional[Dict] = None, 
                     error: Optional[str] = None) -> None:
        trace_entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': level.value,
            'operation': operation,
            'container': container_name,
            'request': request_context,
            'response': response,
            'error': error,
            'call_stack_depth': len(traceback.extract_stack())
        }
        self.traces.append(trace_entry)
        outcome = error or (
            f"exit_code={response['exit_code']}"
            if response and response.get('exit_code', 0) != 0
            else 'OK'
        )
        logger.log(getattr(logging, level.value), 
                   f"[{operation}] {container_name}: {outcome}")
    
    def record_boundary_violation(self, violation_type: str, 
                                  container_name: str, 
                                  expected_state: str,
                                  actual_state: str) -> None:
        violation = {
            'timestamp': datetime.utcnow().isoformat(),
            'type': violation_type,
            'container': container_name,
            'expected': expected_state,
            'actual': actual_state
        }
        self.boundary_violations.append(violation)
        logger.error(f"[BOUNDARY VIOLATION] {violation_type}: {container_name} "
                    f"expected={expected_state}, actual={actual_state}")
    
    def snapshot_container_state(self, container_name: str, state_dict: Dict) -> None:
        self.container_snapshots[container_name] = {
            'timestamp': datetime.utcnow().isoformat(),
            'state': state_dict
        }
    
    def export_trace_log(self, output_path: str = 'logs/docker_trace.json') -> None:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump({
                'traces': self.traces,
                'boundary_violations': self.boundary_violations,
                'container_snapshots': self.container_snapshots,
                'export_time': datetime.utcnow().isoformat()
            }, f, indent=2)
        logger.info(f"Trace log exported to {output_path}")


class DockerClientManager:
    def __init__(self):
        self.client: Optional[docker.DockerClient] = None
        self.trace = DockerAPITrace()
        self._connection_verified = False
    
    def connect(self) -> bool:
        try:
            logger.info("Connecting to Docker daemon...")
            self.client = docker.from_env(timeout=DOCKER_CONNECTION_TIMEOUT)
            response = self.client.ping()
            self._connection_verified = True
            
            self.trace.log_api_call(
                TraceLevel.INFO, 'client.ping', 'docker_daemon', {}, {'ping_response': response}
            )
            logger.info("✓ Docker daemon connection verified")
            return True
        except docker.errors.DockerException as e:
            error_msg = str(e)
            self.trace.log_api_call(
                TraceLevel.ERROR, 'client.connect', 'docker_daemon', {}, error=error_msg
            )
            logger.error(f"✗ Docker daemon connection failed: {error_msg}")
            return False
    
    def is_connected(self) -> bool:
        return self._connection_verified and self.client is not None


class ContainerDiscovery:
    def __init__(self, client_manager: DockerClientManager):
        self.client_manager = client_manager
        self.discovered_containers: Dict[str, Container] = {}
    
    def find_container_by_name(self, container_name: str) -> Optional[Container]:
        if not self.client_manager.is_connected():
            logger.error("Docker daemon not connected")
            return None
        
        try:
            logger.info(f"Searching for container: {container_name}")
            container = self.client_manager.client.containers.get(container_name)
            
            self.client_manager.trace.log_api_call(
                TraceLevel.INFO, 'containers.get', container_name,
                {'container_name': container_name},
                {'container_id': container.id, 'status': container.status}
            )
            self.discovered_containers[container_name] = container
            logger.info(f"✓ Found container: {container_name} (status: {container.status})")
            return container
        
        except NotFound:
            self.client_manager.trace.record_boundary_violation(
                'CONTAINER_NOT_FOUND', container_name, 'FOUND', 'NOT_FOUND'
            )
            logger.error(f"✗ Container not found: {container_name}")
            return None
        except APIError as e:
            error_msg = str(e)
            self.client_manager.trace.log_api_call(
                TraceLevel.ERROR, 'containers.get', container_name,
                {'container_name': container_name}, error=error_msg
            )
            logger.error(f"API error finding container: {error_msg}")
            return None
    
    def verify_container_exists(self, container: Container) -> bool:
        try:
            container.reload()
            return True
        except NotFound:
            raise RuntimeError(
                f"FATAL: Container {container.name} was discovered but no longer exists."
            )


class HealthChecker:
    def __init__(self, trace: DockerAPITrace):
        self.trace = trace
    
    def check_container_state(self, container: Container) -> Tuple[bool, ContainerState]:
        try:
            container.reload()
            status = container.status.lower()
            
            state_map = {
                'running': ContainerState.RUNNING,
                'paused': ContainerState.PAUSED,
                'exited': ContainerState.EXITED,
                'restarting': ContainerState.RESTARTING,
                'removing': ContainerState.REMOVING,
                'dead': ContainerState.DEAD
            }
            state = state_map.get(status, ContainerState.UNKNOWN)
            self.trace.snapshot_container_state(container.name, {'status': status, 'state': state.value})
            
            is_running = state == ContainerState.RUNNING
            logger.info(f"Container {container.name} state: {state.value}")
            return is_running, state
        except Exception as e:
            logger.error(f"Error checking container state: {e}")
            return False, ContainerState.UNKNOWN
    
    def check_healthcheck_status(self, container: Container) -> Tuple[bool, HealthStatus]:
        try:
            container.reload()
            if hasattr(container, 'attrs') and 'State' in container.attrs:
                state = container.attrs['State']
                if 'Health' in state:
                    health_status = state['Health'].get('Status', 'unknown')
                    status_map = {
                        'healthy': HealthStatus.HEALTHY,
                        'unhealthy': HealthStatus.UNHEALTHY,
                        'starting': HealthStatus.UNKNOWN
                    }
                    status = status_map.get(health_status.lower(), HealthStatus.UNKNOWN)
                    return status == HealthStatus.HEALTHY, status
            return True, HealthStatus.NO_HEALTHCHECK
        except Exception as e:
            logger.error(f"Error checking healthcheck: {e}")
            return False, HealthStatus.UNKNOWN
    
    def check_http_endpoint(self, url: str, timeout: int = SUPERSET_HEALTH_TIMEOUT) -> bool:
        try:
            logger.info(f"Probing HTTP endpoint: {url}")
            response = requests.get(url, timeout=timeout)
            is_healthy = response.status_code < 400
            logger.info(f"HTTP probe {url}: {response.status_code}")
            return is_healthy
        except (Timeout, ConnectionError, RequestException) as e:
            logger.warning(f"HTTP endpoint issue for {url}: {e}")
            return False


class ContainerExecutor:
    def __init__(self, trace: DockerAPITrace):
        self.trace = trace
    
    def exec_command(self, container: Container, command: Union[str, List[str]],
                     timeout: int = 30) -> Tuple[bool, str, str]:
        try:
            logger.info(f"Executing in {container.name}: {command}")
            cmd_list = ['/bin/sh', '-c', command] if isinstance(command, str) else command
            
            exit_code, output = container.exec_run(cmd_list, stdout=True, stderr=True)
            stdout = output.decode('utf-8', errors='ignore') if output else ''
            stderr = '' if exit_code == 0 else stdout
            success = exit_code == 0
            
            self.trace.log_api_call(
                TraceLevel.INFO if success else TraceLevel.WARNING,
                'exec_run', container.name, {'command': command},
                {'exit_code': exit_code, 'output_lines': len(stdout.splitlines())}
            )
            return success, stdout, stderr
        except Exception as e:
            error_msg = str(e)
            self.trace.log_api_call(
                TraceLevel.ERROR, 'exec_run', container.name, {'command': command}, error=error_msg
            )
            return False, '', error_msg
    
    def get_container_logs(self, container: Container, lines: int = 100) -> str:
        try:
            return container.logs(tail=lines).decode('utf-8', errors='ignore')
        except Exception as e:
            return f"Error retrieving logs: {e}"


class DockerOrchestrator:
    def __init__(self):
        self.client_manager = DockerClientManager()
        self.discovery = ContainerDiscovery(self.client_manager)
        self.health_checker = HealthChecker(self.client_manager.trace)
        self.executor = ContainerExecutor(self.client_manager.trace)
        self.superset_container: Optional[Container] = None
        self.etl_container: Optional[Container] = None
    
    def initialize(self) -> bool:
        logger.info("="*80)
        logger.info("DOCKER ORCHESTRATOR INITIALIZATION")
        logger.info("="*80)
        
        if not self.client_manager.connect():
            logger.error("FATAL: Docker daemon unreachable")
            return False
        
        self.superset_container = self.discovery.find_container_by_name(SUPERSET_CONTAINER_NAME)
        if not self.superset_container:
            logger.error(f"FATAL: Superset container '{SUPERSET_CONTAINER_NAME}' not found")
            return False
        
        try:
            self.discovery.verify_container_exists(self.superset_container)
        except RuntimeError as e:
            logger.error(f"FATAL: {e}")
            return False
        
        self.etl_container = self.discovery.find_container_by_name(ETL_CONTAINER_NAME)
        if not self.etl_container:
            logger.warning(f"ETL container '{ETL_CONTAINER_NAME}' not found.")
        
        return True
    
    def verify_all_containers(self) -> int:
        logger.info("\n" + "="*80)
        logger.info("CONTAINER HEALTH VERIFICATION")
        logger.info("="*80)
        
        exit_code = 0
        
        if self.superset_container:
            is_running, _ = self.health_checker.check_container_state(self.superset_container)
            if not is_running:
                exit_code = 2
            else:
                is_healthy, _ = self.health_checker.check_healthcheck_status(self.superset_container)
                http_healthy = self.health_checker.check_http_endpoint(SUPERSET_HEALTH_ENDPOINT)
                if not (is_healthy and http_healthy):
                    exit_code = max(exit_code, 1)
        else:
            exit_code = 2
        
        if self.etl_container:
            is_running, _ = self.health_checker.check_container_state(self.etl_container)
            if not is_running:
                exit_code = max(exit_code, 1)
        
        return exit_code
    
    def clear_superset_cache(self) -> bool:
        if not self.superset_container:
            return False
        cache_clear_script = (
            "from superset.app import create_app; "
            "from superset.extensions import cache_manager; "
            "app = create_app(); "
            "app.app_context().push(); "
            "cache_manager.data_cache.clear(); "
            "cache_manager.explore_form_data_cache.clear()"
        )
        success, stdout, stderr = self.executor.exec_command(
            self.superset_container,
            ['python', '-c', cache_clear_script],
        )
        if not success:
            logger.error("Superset cache invalidation failed: %s", stderr or stdout)
            return False
        logger.info("Cleared Superset chart and explore-form caches")
        return success

    def provision_superset_dashboard(self) -> None:
        if not self.superset_container:
            raise RuntimeError("Superset container is not initialized")

        project_root = Path(__file__).resolve().parent.parent
        assets = (
            (project_root / 'app' / 'superset_provision.py', 'fondinsyn_superset_provision.py'),
            (project_root / 'app' / 'database' / 'db' / 'superset_views.sql', 'fondinsyn_superset_views.sql'),
        )
        archive_buffer = io.BytesIO()
        with tarfile.open(fileobj=archive_buffer, mode='w') as archive:
            for source, archive_name in assets:
                if not source.is_file():
                    raise FileNotFoundError(f"Superset provisioning asset not found: {source}")
                archive.add(source, arcname=archive_name)

        if not self.superset_container.put_archive('/tmp', archive_buffer.getvalue()):
            raise RuntimeError("Could not stage Fondinsyn Superset provisioning assets")

        script_path = '/tmp/fondinsyn_superset_provision.py'
        views_path = '/tmp/fondinsyn_superset_views.sql'
        try:
            result = self.superset_container.exec_run(
                ['python', script_path],
                demux=True,
            )
            stdout, stderr = result.output or (b'', b'')
            stdout = stdout or b''
            stderr = stderr or b''
            if result.exit_code != 0:
                error = stderr.decode('utf-8', errors='replace').strip()
                output = stdout.decode('utf-8', errors='replace').strip()
                raise RuntimeError(
                    f"Superset dashboard provisioning failed "
                    f"(exit {result.exit_code}): {error or output}"
                )
            logger.info(
                "Superset dashboard provisioning completed: %s",
                stdout.decode('utf-8', errors='replace').strip() or "success",
            )
        finally:
            self.superset_container.exec_run(['rm', '-f', script_path, views_path])
    
    def export_diagnostics(self, output_dir: str = 'logs/diagnostics') -> None:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        self.client_manager.trace.export_trace_log(f'{output_dir}/docker_trace.json')
        
        if self.superset_container:
            logs = self.executor.get_container_logs(self.superset_container)
            with open(f'{output_dir}/superset_logs.txt', 'w') as f:
                f.write(logs)
        if self.etl_container:
            logs = self.executor.get_container_logs(self.etl_container)
            with open(f'{output_dir}/etl_logs.txt', 'w') as f:
                f.write(logs)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        handlers=[
            logging.FileHandler('logs/docker_manager.log'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    orchestrator = DockerOrchestrator()
    if not orchestrator.initialize():
        sys.exit(2)
    
    exit_code = orchestrator.verify_all_containers()
    if exit_code == 0:
        orchestrator.clear_superset_cache()
    orchestrator.export_diagnostics()
    
    sys.exit(exit_code)


if __name__ == '__main__':
    main()