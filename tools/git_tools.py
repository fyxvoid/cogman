"""Git tools: status, log, commit, push, pull, clone, branch, diff, stash."""
import os
import logging
from core.tool_registry import ToolRegistry
from core.system_controller import run_shell
from core.safety import confirm

log = logging.getLogger("cogman.tools.git")


def _in_repo(path: str = ".") -> bool:
    result = run_shell(f"git -C {path} rev-parse --is-inside-work-tree 2>/dev/null")
    return result.strip() == "true"


def git_status(path: str = ".") -> str:
    return run_shell(f"git -C '{path}' status 2>&1")


def git_log(path: str = ".", n: int = 10, oneline: bool = True) -> str:
    fmt = "--oneline" if oneline else "--format='%h %an %ar: %s'"
    return run_shell(f"git -C '{path}' log {fmt} -n {n} 2>&1")


def git_diff(path: str = ".", staged: bool = False, file: str = "") -> str:
    staged_flag = "--staged" if staged else ""
    file_arg = f"-- '{file}'" if file else ""
    return run_shell(f"git -C '{path}' diff {staged_flag} {file_arg} 2>&1 | head -100")


def git_add(files: str = ".", path: str = ".") -> str:
    return run_shell(f"git -C '{path}' add {files} 2>&1")


def git_commit(message: str, path: str = ".", add_all: bool = False) -> str:
    if add_all:
        run_shell(f"git -C '{path}' add -A 2>&1")
    return run_shell(f"git -C '{path}' commit -m '{message}' 2>&1")


def git_push(remote: str = "origin", branch: str = "", path: str = ".") -> str:
    if not confirm(f"Push to {remote}/{branch or 'current branch'}?"):
        return "Cancelled."
    branch_arg = branch if branch else ""
    return run_shell(f"git -C '{path}' push {remote} {branch_arg} 2>&1")


def git_pull(remote: str = "origin", branch: str = "", path: str = ".") -> str:
    branch_arg = branch if branch else ""
    return run_shell(f"git -C '{path}' pull {remote} {branch_arg} 2>&1")


def git_clone(url: str, destination: str = "") -> str:
    dest = f"'{destination}'" if destination else ""
    return run_shell(f"git clone '{url}' {dest} 2>&1")


def git_branch(path: str = ".", all_: bool = False) -> str:
    flag = "-a" if all_ else ""
    return run_shell(f"git -C '{path}' branch {flag} -v 2>&1")


def git_checkout(branch: str, create: bool = False, path: str = ".") -> str:
    flag = "-b" if create else ""
    return run_shell(f"git -C '{path}' checkout {flag} {branch} 2>&1")


def git_merge(branch: str, path: str = ".") -> str:
    if not confirm(f"Merge branch '{branch}' into current branch?"):
        return "Cancelled."
    return run_shell(f"git -C '{path}' merge {branch} 2>&1")


def git_stash(action: str = "push", message: str = "", path: str = ".") -> str:
    if action == "push":
        msg = f"-m '{message}'" if message else ""
        return run_shell(f"git -C '{path}' stash push {msg} 2>&1")
    elif action == "pop":
        return run_shell(f"git -C '{path}' stash pop 2>&1")
    elif action == "list":
        return run_shell(f"git -C '{path}' stash list 2>&1")
    elif action == "drop":
        return run_shell(f"git -C '{path}' stash drop 2>&1")
    return f"Unknown stash action: {action}"


def git_reset(mode: str = "soft", ref: str = "HEAD~1", path: str = ".") -> str:
    if mode == "hard" and not confirm(f"Hard reset to {ref}? This will discard changes!"):
        return "Cancelled."
    return run_shell(f"git -C '{path}' reset --{mode} {ref} 2>&1")


def git_remote(path: str = ".") -> str:
    return run_shell(f"git -C '{path}' remote -v 2>&1")


def git_tag(name: str = "", message: str = "", path: str = ".") -> str:
    if not name:
        return run_shell(f"git -C '{path}' tag 2>&1")
    msg_flag = f"-m '{message}'" if message else ""
    return run_shell(f"git -C '{path}' tag {msg_flag} {name} 2>&1")


def git_blame(file: str, path: str = ".") -> str:
    return run_shell(f"git -C '{path}' blame '{file}' 2>&1 | head -40")


def git_show(ref: str = "HEAD", path: str = ".") -> str:
    return run_shell(f"git -C '{path}' show {ref} --stat 2>&1 | head -40")


def git_init(path: str = ".") -> str:
    return run_shell(f"git init '{path}' 2>&1")


def git_config(key: str, value: str = "", global_: bool = True) -> str:
    scope = "--global" if global_ else "--local"
    if value:
        return run_shell(f"git config {scope} {key} '{value}' 2>&1")
    return run_shell(f"git config {scope} {key} 2>&1")


def register_git_tools(registry: ToolRegistry):
    p = {"path": {"type": "string", "description": "Repo path (default: current directory)"}}

    registry.register("git_status", git_status, "Show git repository status",
        {**p})
    registry.register("git_log", git_log, "Show git commit history",
        {
            **p,
            "n": {"type": "integer", "description": "Number of commits (default 10)"},
            "oneline": {"type": "boolean", "description": "Compact one-line format (default true)"},
        })
    registry.register("git_diff", git_diff, "Show git diff of working tree or staged changes",
        {
            **p,
            "staged": {"type": "boolean", "description": "Show staged diff"},
            "file": {"type": "string", "description": "Specific file to diff"},
        })
    registry.register("git_add", git_add, "Stage files for commit",
        {
            **p,
            "files": {"type": "string", "description": "Files to stage (default: . for all)"},
        })
    registry.register("git_commit", git_commit, "Create a git commit",
        {
            **p,
            "message": {"type": "string", "description": "Commit message", "required": True},
            "add_all": {"type": "boolean", "description": "Stage all changes before committing"},
        })
    registry.register("git_push", git_push, "Push commits to remote",
        {
            **p,
            "remote": {"type": "string", "description": "Remote name (default: origin)"},
            "branch": {"type": "string", "description": "Branch name (default: current)"},
        }, requires_confirm=True)
    registry.register("git_pull", git_pull, "Pull from remote",
        {
            **p,
            "remote": {"type": "string", "description": "Remote name (default: origin)"},
            "branch": {"type": "string", "description": "Branch name"},
        })
    registry.register("git_clone", git_clone, "Clone a git repository",
        {
            "url": {"type": "string", "description": "Repository URL", "required": True},
            "destination": {"type": "string", "description": "Local directory name"},
        })
    registry.register("git_branch", git_branch, "List git branches",
        {
            **p,
            "all_": {"type": "boolean", "description": "Show remote branches too"},
        })
    registry.register("git_checkout", git_checkout, "Switch or create a branch",
        {
            **p,
            "branch": {"type": "string", "description": "Branch name", "required": True},
            "create": {"type": "boolean", "description": "Create new branch (-b)"},
        })
    registry.register("git_merge", git_merge, "Merge a branch into current",
        {
            **p,
            "branch": {"type": "string", "description": "Branch to merge", "required": True},
        }, requires_confirm=True)
    registry.register("git_stash", git_stash, "Git stash operations (push, pop, list, drop)",
        {
            **p,
            "action": {"type": "string", "description": "Action: push, pop, list, drop (default: push)"},
            "message": {"type": "string", "description": "Stash message"},
        })
    registry.register("git_reset", git_reset, "Reset git HEAD to a previous commit",
        {
            **p,
            "mode": {"type": "string", "description": "Mode: soft, mixed, hard (default: soft)"},
            "ref": {"type": "string", "description": "Git ref (default: HEAD~1)"},
        }, requires_confirm=True)
    registry.register("git_remote", git_remote, "List git remote URLs", {**p})
    registry.register("git_tag", git_tag, "List or create git tags",
        {
            **p,
            "name": {"type": "string", "description": "Tag name (empty = list all)"},
            "message": {"type": "string", "description": "Annotated tag message"},
        })
    registry.register("git_blame", git_blame, "Show who changed each line of a file",
        {
            **p,
            "file": {"type": "string", "description": "File path", "required": True},
        })
    registry.register("git_show", git_show, "Show details of a commit",
        {
            **p,
            "ref": {"type": "string", "description": "Commit ref (default: HEAD)"},
        })
    registry.register("git_init", git_init, "Initialize a new git repository",
        {**p})
    registry.register("git_config", git_config, "Get or set git config values",
        {
            "key": {"type": "string", "description": "Config key e.g. user.name", "required": True},
            "value": {"type": "string", "description": "Value to set (empty = get current)"},
            "global_": {"type": "boolean", "description": "Global config (default true)"},
        })
