"""Docker tools: ps, images, run, stop, logs, exec, build, compose."""
import shutil
import logging
from core.tool_registry import ToolRegistry
from core.system_controller import run_shell
from core.safety import confirm

log = logging.getLogger("cogman.tools.docker")


def _docker_available() -> str | None:
    if not shutil.which("docker"):
        return "Docker not installed — visit https://docs.docker.com/engine/install/"
    result = run_shell("docker info --format '{{.ServerVersion}}' 2>&1")
    if "permission denied" in result.lower():
        return "Docker permission denied — add user to docker group: sudo usermod -aG docker $USER"
    return None


def docker_ps(all_: bool = False) -> str:
    err = _docker_available()
    if err:
        return err
    flag = "-a" if all_ else ""
    return run_shell(f"docker ps {flag} --format 'table {{{{.ID}}}}\t{{{{.Image}}}}\t{{{{.Status}}}}\t{{{{.Names}}}}' 2>&1")


def docker_images(all_: bool = False) -> str:
    err = _docker_available()
    if err:
        return err
    flag = "-a" if all_ else ""
    return run_shell(f"docker images {flag} 2>&1")


def docker_run(image: str, name: str = "", ports: str = "", volumes: str = "",
               env: str = "", detach: bool = True, command: str = "") -> str:
    err = _docker_available()
    if err:
        return err
    parts = ["docker run"]
    if detach:
        parts.append("-d")
    if name:
        parts.append(f"--name '{name}'")
    if ports:
        for p in ports.split(","):
            parts.append(f"-p {p.strip()}")
    if volumes:
        for v in volumes.split(","):
            parts.append(f"-v {v.strip()}")
    if env:
        for e in env.split(","):
            parts.append(f"-e {e.strip()}")
    parts.append(f"'{image}'")
    if command:
        parts.append(command)
    return run_shell(" ".join(parts))


def docker_stop(name_or_id: str) -> str:
    err = _docker_available()
    if err:
        return err
    return run_shell(f"docker stop '{name_or_id}' 2>&1")


def docker_start(name_or_id: str) -> str:
    err = _docker_available()
    if err:
        return err
    return run_shell(f"docker start '{name_or_id}' 2>&1")


def docker_restart(name_or_id: str) -> str:
    err = _docker_available()
    if err:
        return err
    return run_shell(f"docker restart '{name_or_id}' 2>&1")


def docker_rm(name_or_id: str, force: bool = False) -> str:
    err = _docker_available()
    if err:
        return err
    if not confirm(f"Remove container '{name_or_id}'?"):
        return "Cancelled."
    flag = "-f" if force else ""
    return run_shell(f"docker rm {flag} '{name_or_id}' 2>&1")


def docker_rmi(image: str, force: bool = False) -> str:
    err = _docker_available()
    if err:
        return err
    if not confirm(f"Remove image '{image}'?"):
        return "Cancelled."
    flag = "-f" if force else ""
    return run_shell(f"docker rmi {flag} '{image}' 2>&1")


def docker_logs(name_or_id: str, tail: int = 50, follow: bool = False) -> str:
    err = _docker_available()
    if err:
        return err
    if follow:
        return f"Use: docker logs -f {name_or_id} (interactive)"
    return run_shell(f"docker logs --tail {tail} '{name_or_id}' 2>&1")


def docker_exec(name_or_id: str, command: str) -> str:
    err = _docker_available()
    if err:
        return err
    return run_shell(f"docker exec '{name_or_id}' {command} 2>&1")


def docker_build(tag: str, context: str = ".", dockerfile: str = "") -> str:
    err = _docker_available()
    if err:
        return err
    df_flag = f"-f '{dockerfile}'" if dockerfile else ""
    return run_shell(f"docker build {df_flag} -t '{tag}' '{context}' 2>&1 | tail -10")


def docker_pull(image: str) -> str:
    err = _docker_available()
    if err:
        return err
    return run_shell(f"docker pull '{image}' 2>&1 | tail -5")


def docker_push(image: str) -> str:
    err = _docker_available()
    if err:
        return err
    if not confirm(f"Push image '{image}' to registry?"):
        return "Cancelled."
    return run_shell(f"docker push '{image}' 2>&1 | tail -5")


def docker_inspect(name_or_id: str) -> str:
    err = _docker_available()
    if err:
        return err
    return run_shell(f"docker inspect '{name_or_id}' 2>&1 | head -50")


def docker_stats() -> str:
    err = _docker_available()
    if err:
        return err
    return run_shell("docker stats --no-stream 2>&1")


def docker_prune(all_: bool = False) -> str:
    err = _docker_available()
    if err:
        return err
    if not confirm("Remove all stopped containers and dangling images?"):
        return "Cancelled."
    flag = "-a" if all_ else ""
    return run_shell(f"docker system prune {flag} -f 2>&1")


def docker_compose_up(path: str = ".", detach: bool = True) -> str:
    err = _docker_available()
    if err:
        return err
    flag = "-d" if detach else ""
    return run_shell(f"docker compose -f '{path}/docker-compose.yml' up {flag} 2>&1 | tail -10")


def docker_compose_down(path: str = ".") -> str:
    err = _docker_available()
    if err:
        return err
    return run_shell(f"docker compose -f '{path}/docker-compose.yml' down 2>&1")


def docker_compose_logs(path: str = ".", tail: int = 30) -> str:
    err = _docker_available()
    if err:
        return err
    return run_shell(f"docker compose -f '{path}/docker-compose.yml' logs --tail {tail} 2>&1")


def register_docker_tools(registry: ToolRegistry):
    registry.register("docker_ps", docker_ps, "List running Docker containers",
        {"all_": {"type": "boolean", "description": "Show all containers including stopped"}})
    registry.register("docker_images", docker_images, "List Docker images", {})
    registry.register("docker_run", docker_run, "Run a Docker container",
        {
            "image": {"type": "string", "description": "Docker image name", "required": True},
            "name": {"type": "string", "description": "Container name"},
            "ports": {"type": "string", "description": "Port mappings e.g. 8080:80,443:443"},
            "volumes": {"type": "string", "description": "Volume mounts e.g. /host:/container"},
            "env": {"type": "string", "description": "Env vars e.g. KEY=val,KEY2=val2"},
            "detach": {"type": "boolean", "description": "Run detached (default true)"},
            "command": {"type": "string", "description": "Command to run in container"},
        })
    registry.register("docker_stop", docker_stop, "Stop a container",
        {"name_or_id": {"type": "string", "description": "Container name or ID", "required": True}})
    registry.register("docker_start", docker_start, "Start a stopped container",
        {"name_or_id": {"type": "string", "description": "Container name or ID", "required": True}})
    registry.register("docker_restart", docker_restart, "Restart a container",
        {"name_or_id": {"type": "string", "description": "Container name or ID", "required": True}})
    registry.register("docker_rm", docker_rm, "Remove a container",
        {
            "name_or_id": {"type": "string", "description": "Container name or ID", "required": True},
            "force": {"type": "boolean", "description": "Force remove running container"},
        }, requires_confirm=True)
    registry.register("docker_rmi", docker_rmi, "Remove a Docker image",
        {
            "image": {"type": "string", "description": "Image name or ID", "required": True},
            "force": {"type": "boolean", "description": "Force remove"},
        }, requires_confirm=True)
    registry.register("docker_logs", docker_logs, "View container logs",
        {
            "name_or_id": {"type": "string", "description": "Container name or ID", "required": True},
            "tail": {"type": "integer", "description": "Lines to show (default 50)"},
        })
    registry.register("docker_exec", docker_exec, "Execute a command in a running container",
        {
            "name_or_id": {"type": "string", "description": "Container name or ID", "required": True},
            "command": {"type": "string", "description": "Command to execute", "required": True},
        })
    registry.register("docker_build", docker_build, "Build a Docker image",
        {
            "tag": {"type": "string", "description": "Image tag name", "required": True},
            "context": {"type": "string", "description": "Build context path (default: .)"},
            "dockerfile": {"type": "string", "description": "Custom Dockerfile path"},
        })
    registry.register("docker_pull", docker_pull, "Pull a Docker image",
        {"image": {"type": "string", "description": "Image name:tag", "required": True}})
    registry.register("docker_push", docker_push, "Push an image to registry",
        {"image": {"type": "string", "description": "Image name:tag", "required": True}},
        requires_confirm=True)
    registry.register("docker_inspect", docker_inspect, "Inspect container/image details",
        {"name_or_id": {"type": "string", "description": "Container or image name/ID", "required": True}})
    registry.register("docker_stats", docker_stats, "Show live resource usage of containers", {})
    registry.register("docker_prune", docker_prune, "Clean up unused Docker resources", {},
        requires_confirm=True)
    registry.register("docker_compose_up", docker_compose_up, "Start Docker Compose services",
        {
            "path": {"type": "string", "description": "Directory with docker-compose.yml (default: .)"},
            "detach": {"type": "boolean", "description": "Run detached (default true)"},
        })
    registry.register("docker_compose_down", docker_compose_down, "Stop Docker Compose services",
        {"path": {"type": "string", "description": "Directory with docker-compose.yml (default: .)"}})
    registry.register("docker_compose_logs", docker_compose_logs, "View Docker Compose logs",
        {
            "path": {"type": "string", "description": "Directory with docker-compose.yml (default: .)"},
            "tail": {"type": "integer", "description": "Lines to show (default 30)"},
        })
