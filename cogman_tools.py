"""
cogman_tools — direct function API for every cogman capability.

Three ways to use:

  1. Flat import (fastest to type):
        from cogman_tools import git_status, docker_ps, apt_install
        git_status()
        docker_ps()
        apt_install("vim")

  2. Namespace import:
        import cogman_tools as cog
        cog.calculate("sqrt(144) + pi")
        cog.set_brightness(70)
        cog.service_restart("nginx")

  3. Grouped class (IDE-friendly autocomplete by category):
        from cogman_tools import CogmanTools
        c = CogmanTools()
        c.shell.run_shell("ls -la")
        c.git.git_status()
        c.docker.docker_ps()
        c.packages.apt_install("htop")
        c.power.set_brightness(80)
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

# ── Re-export everything flat ────────────────────────────────────────────────
from tools import *   # noqa: F401, F403 — intentional star import for flat namespace


# ── Grouped class API ────────────────────────────────────────────────────────

class _ShellTools:
    """Direct shell and OS control."""
    from core.system_controller import (
        run_shell, open_app, get_time, get_date,
        screenshot, lock_screen, set_volume, mute_toggle,
        kill_process, list_processes, network_info,
        battery_status, type_text,
    )
    from tools.system_tools import disk_usage, memory_usage, cpu_usage


class _FileTools:
    """File system operations."""
    from tools.file_tools import list_files, read_file, write_file, find_files


class _ProcessTools:
    """Process management."""
    from tools.process_tools import (
        process_tree, top_processes, get_process_info,
        set_priority, run_background, send_signal,
        find_process_by_port, wait_for_process,
    )


class _NetworkTools:
    """Networking, WiFi, firewall, SSH."""
    from tools.network_tools import (
        ping, traceroute, dns_lookup, reverse_dns,
        list_open_ports, check_port,
        firewall_status, firewall_allow, firewall_deny,
        download_file, get_public_ip, get_local_ip,
        wifi_networks, wifi_connect, wifi_disconnect,
        speed_test, ssh_keygen, list_ssh_keys, network_stats,
    )


class _PackageTools:
    """apt, pip, snap, flatpak, npm, cargo."""
    from tools.package_tools import (
        apt_install, apt_remove, apt_purge, apt_update, apt_upgrade,
        apt_search, apt_show, apt_list_installed, apt_autoremove,
        pip_install, pip_uninstall, pip_list, pip_show,
        pip_outdated, pip_upgrade,
        snap_install, snap_remove, snap_list, snap_refresh,
        flatpak_install, flatpak_list, flatpak_update,
        npm_install, npm_list, cargo_install,
    )


class _ServiceTools:
    """systemd services, timers, journal."""
    from tools.service_tools import (
        service_status, service_start, service_stop,
        service_restart, service_reload,
        service_enable, service_disable, service_logs,
        list_services, failed_services, daemon_reload,
        system_uptime, list_timers,
        user_service_status, user_service_start, user_service_stop,
    )


class _GitTools:
    """Git version control."""
    from tools.git_tools import (
        git_status, git_log, git_diff, git_add, git_commit,
        git_push, git_pull, git_clone, git_branch, git_checkout,
        git_merge, git_stash, git_reset, git_remote,
        git_tag, git_blame, git_show, git_init, git_config,
    )


class _PowerTools:
    """Power, brightness, sleep, shutdown."""
    from tools.power_tools import (
        suspend, hibernate, reboot, shutdown, cancel_shutdown,
        get_brightness, set_brightness,
        screen_off, screen_on, set_screen_timeout, power_stats,
    )


class _WindowTools:
    """Window and desktop management."""
    from tools.window_tools import (
        list_windows, focus_window, close_window,
        maximize_window, minimize_window,
        move_window, resize_window,
        list_workspaces, switch_workspace,
        move_window_to_workspace, get_active_window,
        fullscreen_window, always_on_top, set_wallpaper,
    )


class _ArchiveTools:
    """Compression and archives."""
    from tools.archive_tools import (
        extract, create_tar, create_zip, list_archive, compress_file,
    )


class _TextTools:
    """Text processing, hashing, diff, base64."""
    from tools.text_tools import (
        grep_in_file, grep_in_dir, word_count, file_diff,
        hash_file, hash_text, base64_encode, base64_decode,
        sort_lines, replace_in_file, count_occurrences,
        json_query, head_file, tail_file, column_cut,
    )


class _DockerTools:
    """Docker containers, images, compose."""
    from tools.docker_tools import (
        docker_ps, docker_images, docker_run,
        docker_stop, docker_start, docker_restart,
        docker_rm, docker_rmi, docker_logs, docker_exec,
        docker_build, docker_pull, docker_push,
        docker_inspect, docker_stats, docker_prune,
        docker_compose_up, docker_compose_down, docker_compose_logs,
    )


class _SysInfoTools:
    """Hardware, OS, kernel, sensors, logs."""
    from tools.system_info_tools import (
        system_info, os_release, kernel_info, cpu_info,
        memory_info, disk_info, pci_devices, usb_devices,
        hardware_info, sensors, journal_logs, syslog, dmesg,
        env_vars, which_command, path_info, installed_shells,
        hostname_info, user_info, load_average, boot_time, locale_info,
    )


class _MiscTools:
    """Clipboard, notifications, cron, calculator, media, users."""
    from tools.misc_tools import (
        clipboard_copy, clipboard_paste, notify,
        cron_list, cron_add, cron_remove,
        calculate, unit_convert,
        play_audio, play_video, ffmpeg_convert, get_media_info,
        list_users, current_user, who_is_logged_in,
        add_user, user_groups, add_to_group,
        chmod_file, chown_file, file_permissions,
    )


class _MemoryTools:
    """Long-term and short-term memory."""
    from tools.memory_tools import (
        save_memory, search_memory, set_preference, get_preference,
    )


class _WebTools:
    """Web search, fetch, weather."""
    from tools.web_tools import web_search, fetch_url, get_weather


class CogmanTools:
    """
    Grouped API — every cogman capability, organized by category.

    Example:
        c = CogmanTools()
        c.git.git_status()
        c.packages.apt_install("htop")
        c.docker.docker_ps()
        c.power.set_brightness(70)
        c.text.hash_file("~/important.txt")
        c.misc.calculate("sqrt(2) * pi")
    """
    shell    = _ShellTools
    files    = _FileTools
    process  = _ProcessTools
    network  = _NetworkTools
    packages = _PackageTools
    services = _ServiceTools
    git      = _GitTools
    power    = _PowerTools
    windows  = _WindowTools
    archives = _ArchiveTools
    text     = _TextTools
    docker   = _DockerTools
    sysinfo  = _SysInfoTools
    misc     = _MiscTools
    memory   = _MemoryTools
    web      = _WebTools

    def help(self, category: str = "") -> str:
        cats = {
            "shell":    _ShellTools,
            "files":    _FileTools,
            "process":  _ProcessTools,
            "network":  _NetworkTools,
            "packages": _PackageTools,
            "services": _ServiceTools,
            "git":      _GitTools,
            "power":    _PowerTools,
            "windows":  _WindowTools,
            "archives": _ArchiveTools,
            "text":     _TextTools,
            "docker":   _DockerTools,
            "sysinfo":  _SysInfoTools,
            "misc":     _MiscTools,
            "memory":   _MemoryTools,
            "web":      _WebTools,
        }
        if category:
            cls = cats.get(category)
            if not cls:
                return f"Unknown category: {category}. Available: {list(cats)}"
            fns = [k for k in vars(cls) if not k.startswith("_")]
            return f"[{category}]\n" + "\n".join(f"  {f}" for f in sorted(fns))

        lines = ["CogmanTools categories (use help('category') for functions):"]
        for name, cls in cats.items():
            fns = [k for k in vars(cls) if not k.startswith("_")]
            lines.append(f"  .{name:<10} ({len(fns)} functions)")
        return "\n".join(lines)
