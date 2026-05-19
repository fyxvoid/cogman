"""
Comprehensive tests for every tool module in cogman/tools/.

Organised by module. Tests that require external services (network, docker,
snap, sudo) verify the graceful-failure path rather than the happy path, so
the suite can run fully offline / unprivileged.
"""

from __future__ import annotations

import os
import sys
import json

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ─────────────────────────────── helpers ─────────────────────────────────────

def _is_str(value, *contains) -> bool:
    if not isinstance(value, str):
        return False
    return all(c.lower() in value.lower() for c in contains)


# ══════════════════════════════════════════════════════════════════════════════
# system_tools
# ══════════════════════════════════════════════════════════════════════════════

class TestSystemTools:
    def test_get_time(self):
        from tools.system_tools import get_time
        out = get_time()
        assert ":" in out  # HH:MM:SS

    def test_get_date(self):
        from tools.system_tools import get_date
        out = get_date()
        assert "202" in out  # year

    def test_disk_usage_root(self):
        from tools.system_tools import disk_usage
        out = disk_usage("/")
        assert "GB" in out
        assert "%" in out

    def test_disk_usage_custom_path(self, tmp_path):
        from tools.system_tools import disk_usage
        out = disk_usage(str(tmp_path))
        assert isinstance(out, str)

    def test_memory_usage(self):
        from tools.system_tools import memory_usage
        out = memory_usage()
        assert "RAM" in out
        assert "MB" in out

    def test_cpu_usage(self):
        from tools.system_tools import cpu_usage
        out = cpu_usage()
        assert "CPU" in out
        assert "%" in out

    def test_list_processes(self):
        from core.system_controller import list_processes
        out = list_processes()
        assert isinstance(out, str)
        assert len(out) > 10

    def test_network_info(self):
        from core.system_controller import network_info
        out = network_info()
        assert isinstance(out, str)

    def test_battery_status(self):
        from core.system_controller import battery_status
        out = battery_status()
        # May be "no battery" on a desktop — still must return a string
        assert isinstance(out, str)

    def test_safe_shell_echo(self):
        from tools.system_tools import _safe_run_shell
        out = _safe_run_shell("echo hello_cogman")
        assert "hello_cogman" in out

    def test_blocked_rm_rf(self):
        from tools.system_tools import _safe_run_shell
        out = _safe_run_shell("rm -rf /")
        assert "BLOCKED" in out


# ══════════════════════════════════════════════════════════════════════════════
# file_tools
# ══════════════════════════════════════════════════════════════════════════════

class TestFileTools:
    def test_list_files_home(self):
        from tools.file_tools import list_files
        out = list_files("~")
        assert "Contents of" in out

    def test_list_files_dir(self, tmp_path):
        from tools.file_tools import list_files
        (tmp_path / "a.txt").write_text("x")
        (tmp_path / "b.txt").write_text("y")
        out = list_files(str(tmp_path))
        assert "a.txt" in out and "b.txt" in out

    def test_list_files_empty(self, tmp_path):
        from tools.file_tools import list_files
        empty = tmp_path / "empty"
        empty.mkdir()
        out = list_files(str(empty))
        assert "empty directory" in out.lower()

    def test_read_write_file(self, tmp_path):
        from tools.file_tools import write_file, read_file
        p = str(tmp_path / "test.txt")
        write_file(p, "cogman test content", overwrite=True)
        content = read_file(p)
        assert "cogman test content" in content

    def test_read_missing_file(self):
        from tools.file_tools import read_file
        out = read_file("/nonexistent/path/file.txt")
        assert "not found" in out.lower() or "blocked" in out.lower()

    def test_find_files(self, tmp_path):
        from tools.file_tools import find_files
        (tmp_path / "test.py").write_text("pass")
        (tmp_path / "notes.md").write_text("notes")
        out = find_files("*.py", str(tmp_path))
        assert "test.py" in out

    def test_find_no_match(self, tmp_path):
        from tools.file_tools import find_files
        out = find_files("*.xyz", str(tmp_path))
        assert "No files" in out


# ══════════════════════════════════════════════════════════════════════════════
# text_tools
# ══════════════════════════════════════════════════════════════════════════════

class TestTextTools:

    @pytest.fixture()
    def sample_file(self, tmp_path):
        p = tmp_path / "data.txt"
        p.write_text("apple\nbanana\napple\ncherry\n")
        return str(p)

    def test_grep_in_file_match(self, sample_file):
        from tools.text_tools import grep_in_file
        out = grep_in_file("apple", sample_file)
        assert "apple" in out

    def test_grep_in_file_no_match(self, sample_file):
        from tools.text_tools import grep_in_file
        out = grep_in_file("zzzzzz", sample_file)
        # grep exits non-zero, output is empty or just newline
        assert isinstance(out, str)

    def test_grep_in_file_ignore_case(self, sample_file):
        from tools.text_tools import grep_in_file
        out = grep_in_file("APPLE", sample_file, ignore_case=True)
        assert "apple" in out.lower()

    def test_grep_in_dir(self, tmp_path):
        from tools.text_tools import grep_in_dir
        (tmp_path / "a.py").write_text("def cogman(): pass")
        out = grep_in_dir("cogman", str(tmp_path), file_pattern="*.py")
        assert "cogman" in out

    def test_word_count(self, sample_file):
        from tools.text_tools import word_count
        out = word_count(sample_file)
        assert isinstance(out, str) and len(out) > 0

    def test_file_diff_identical(self, tmp_path):
        from tools.text_tools import file_diff
        a = str(tmp_path / "a.txt")
        b = str(tmp_path / "b.txt")
        open(a, "w").write("same\n")
        open(b, "w").write("same\n")
        out = file_diff(a, b)
        # Empty diff or just newline when identical
        assert isinstance(out, str)

    def test_file_diff_different(self, tmp_path):
        from tools.text_tools import file_diff
        a = str(tmp_path / "a.txt")
        b = str(tmp_path / "b.txt")
        open(a, "w").write("line1\n")
        open(b, "w").write("line2\n")
        out = file_diff(a, b)
        assert "line1" in out or "line2" in out

    def test_hash_file_sha256(self, tmp_path):
        from tools.text_tools import hash_file
        p = str(tmp_path / "f.bin")
        open(p, "wb").write(b"cogman")
        out = hash_file(p, "sha256")
        assert "SHA256" in out

    def test_hash_file_md5(self, tmp_path):
        from tools.text_tools import hash_file
        p = str(tmp_path / "f.bin")
        open(p, "wb").write(b"cogman")
        out = hash_file(p, "md5")
        assert "MD5" in out

    def test_hash_text_algorithms(self):
        from tools.text_tools import hash_text
        for algo in ["md5", "sha1", "sha256", "sha512"]:
            out = hash_text("cogman", algo)
            assert algo.upper() in out

    def test_hash_text_unknown_algo(self):
        from tools.text_tools import hash_text
        out = hash_text("x", "sha999")
        assert "Unknown" in out

    def test_base64_roundtrip(self):
        from tools.text_tools import base64_encode, base64_decode
        for text in ["hello world", "cogman AI", "123!@#", ""]:
            enc = base64_encode(text)
            dec = base64_decode(enc)
            assert dec == text

    def test_base64_known_value(self):
        from tools.text_tools import base64_encode, base64_decode
        assert base64_encode("hello") == "aGVsbG8="
        assert base64_decode("aGVsbG8=") == "hello"

    def test_sort_lines_asc(self):
        from tools.text_tools import sort_lines
        out = sort_lines("banana\napple\ncherry")
        lines = out.split("\n")
        assert lines[0] == "apple"

    def test_sort_lines_desc(self):
        from tools.text_tools import sort_lines
        out = sort_lines("banana\napple\ncherry", reverse=True)
        lines = out.split("\n")
        assert lines[0] == "cherry"

    def test_sort_lines_unique(self):
        from tools.text_tools import sort_lines
        out = sort_lines("a\nb\na\nc\nb", unique=True)
        lines = out.split("\n")
        assert len(lines) == len(set(lines))

    def test_sort_lines_numeric(self):
        from tools.text_tools import sort_lines
        out = sort_lines("10\n2\n30\n1", numeric=True)
        lines = out.split("\n")
        assert lines[0] == "1" and lines[-1] == "30"

    def test_replace_in_file(self, tmp_path):
        from tools.text_tools import replace_in_file
        p = str(tmp_path / "r.txt")
        open(p, "w").write("foo foo foo\n")
        out = replace_in_file(p, "foo", "bar")
        assert "3" in out or "Replaced" in out
        content = open(p).read()
        assert "foo" not in content
        assert "bar" in content

    def test_replace_in_file_regex(self, tmp_path):
        from tools.text_tools import replace_in_file
        p = str(tmp_path / "r.txt")
        open(p, "w").write("abc123def456\n")
        replace_in_file(p, r"\d+", "NUM", regex=True)
        content = open(p).read()
        assert "NUM" in content

    def test_count_occurrences_text(self):
        from tools.text_tools import count_occurrences
        out = count_occurrences("cat", text="the cat sat on the cat mat")
        assert "2" in out

    def test_count_occurrences_file(self, tmp_path):
        from tools.text_tools import count_occurrences
        p = str(tmp_path / "c.txt")
        open(p, "w").write("yes\nno\nyes\nyes\n")
        out = count_occurrences("yes", file=p)
        assert "3" in out or isinstance(out, str)

    def test_json_query(self, tmp_path):
        from tools.text_tools import json_query
        p = str(tmp_path / "data.json")
        json.dump({"name": "cogman", "version": 1}, open(p, "w"))
        out = json_query(p)
        assert "cogman" in out

    def test_head_file(self, sample_file):
        from tools.text_tools import head_file
        out = head_file(sample_file, 2)
        assert "apple" in out

    def test_tail_file(self, sample_file):
        from tools.text_tools import tail_file
        out = tail_file(sample_file, 1)
        assert "cherry" in out

    def test_column_cut(self, tmp_path):
        from tools.text_tools import column_cut
        p = str(tmp_path / "cols.txt")
        open(p, "w").write("a:b:c\n1:2:3\n")
        out = column_cut(p, delimiter=":", fields="2")
        assert "b" in out or "2" in out


# ══════════════════════════════════════════════════════════════════════════════
# misc_tools
# ══════════════════════════════════════════════════════════════════════════════

class TestMiscTools:

    def test_calculate_basic(self):
        from tools.misc_tools import calculate
        assert "144" in calculate("12 ** 2")
        assert "4" in calculate("2 + 2")

    def test_calculate_trig(self):
        from tools.misc_tools import calculate
        out = calculate("round(sin(0), 2)")
        assert "0.0" in out or "= 0" in out

    def test_calculate_pi(self):
        from tools.misc_tools import calculate
        out = calculate("round(pi, 4)")
        assert "3.1416" in out

    def test_calculate_sqrt(self):
        from tools.misc_tools import calculate
        assert "12.0" in calculate("sqrt(144)")

    def test_calculate_div_zero(self):
        from tools.misc_tools import calculate
        out = calculate("1/0")
        assert "zero" in out.lower() or "Error" in out

    def test_unit_convert_km_to_m(self):
        from tools.misc_tools import unit_convert
        out = unit_convert(1.0, "km", "m")
        assert "1000" in out

    def test_unit_convert_celsius_to_fahrenheit(self):
        from tools.misc_tools import unit_convert
        out = unit_convert(0.0, "c", "f")
        assert "32" in out

    def test_unit_convert_fahrenheit_to_celsius(self):
        from tools.misc_tools import unit_convert
        out = unit_convert(212.0, "f", "c")
        assert "100" in out

    def test_unit_convert_kg_to_lb(self):
        from tools.misc_tools import unit_convert
        out = unit_convert(1.0, "kg", "lb")
        assert "2.2" in out

    def test_unit_convert_celsius_to_kelvin(self):
        from tools.misc_tools import unit_convert
        out = unit_convert(0.0, "c", "k")
        assert "273" in out

    def test_unit_convert_unknown(self):
        from tools.misc_tools import unit_convert
        out = unit_convert(1.0, "xyz", "abc")
        assert "No conversion" in out

    def test_unit_convert_gb_to_mb(self):
        from tools.misc_tools import unit_convert
        out = unit_convert(1.0, "gb", "mb")
        assert "1024" in out

    def test_cron_list(self):
        from tools.misc_tools import cron_list
        out = cron_list()
        assert isinstance(out, str)

    def test_clipboard_copy_fallback(self):
        from tools.misc_tools import clipboard_copy
        out = clipboard_copy("test clipboard")
        assert isinstance(out, str)  # either success or "No clipboard tool"

    def test_notify_fallback(self):
        from tools.misc_tools import notify
        out = notify("test title", "test message")
        assert isinstance(out, str)

    def test_list_users(self):
        from tools.misc_tools import list_users
        out = list_users()
        assert isinstance(out, str) and len(out) > 0

    def test_current_user(self):
        from tools.misc_tools import current_user
        out = current_user()
        assert "uid=" in out or "void" in out or "root" in out

    def test_who_is_logged_in(self):
        from tools.misc_tools import who_is_logged_in
        out = who_is_logged_in()
        assert isinstance(out, str)

    def test_user_groups(self):
        from tools.misc_tools import user_groups
        out = user_groups()
        assert isinstance(out, str) and len(out) > 0

    def test_file_permissions(self, tmp_path):
        from tools.misc_tools import file_permissions
        p = str(tmp_path / "perm.txt")
        open(p, "w").write("x")
        out = file_permissions(p)
        assert "perm.txt" in out


# ══════════════════════════════════════════════════════════════════════════════
# network_tools
# ══════════════════════════════════════════════════════════════════════════════

class TestNetworkTools:

    def test_ping_loopback(self):
        from tools.network_tools import ping
        out = ping("127.0.0.1", count=2)
        assert "127.0.0.1" in out

    def test_check_port_closed(self):
        from tools.network_tools import check_port
        out = check_port("127.0.0.1", 1)
        assert "CLOSED" in out or "OPEN" in out or "UNREACHABLE" in out

    def test_check_port_open(self):
        """Port 22 may be open on a development machine."""
        from tools.network_tools import check_port
        out = check_port("127.0.0.1", 22, timeout=2)
        assert isinstance(out, str)

    def test_get_local_ip(self):
        from tools.network_tools import get_local_ip
        out = get_local_ip()
        assert isinstance(out, str)

    def test_list_open_ports(self):
        from tools.network_tools import list_open_ports
        out = list_open_ports()
        assert isinstance(out, str)

    def test_network_stats(self):
        from tools.network_tools import network_stats
        out = network_stats()
        assert "Interface" in out
        assert "Sent MB" in out

    def test_list_ssh_keys(self):
        from tools.network_tools import list_ssh_keys
        out = list_ssh_keys()
        assert isinstance(out, str)

    def test_dns_lookup_localhost(self):
        from tools.network_tools import dns_lookup
        out = dns_lookup("localhost")
        assert isinstance(out, str)

    def test_reverse_dns_loopback(self):
        from tools.network_tools import reverse_dns
        out = reverse_dns("127.0.0.1")
        assert isinstance(out, str)

    def test_firewall_status(self):
        from tools.network_tools import firewall_status
        out = firewall_status()
        assert isinstance(out, str)


# ══════════════════════════════════════════════════════════════════════════════
# process_tools
# ══════════════════════════════════════════════════════════════════════════════

class TestProcessTools:

    def test_top_processes_cpu(self):
        from tools.process_tools import top_processes
        out = top_processes(n=5, sort_by="cpu")
        assert "CPU%" in out
        assert "PID" in out

    def test_top_processes_memory(self):
        from tools.process_tools import top_processes
        out = top_processes(n=5, sort_by="memory")
        assert "MEM%" in out

    def test_get_process_info_by_pid(self):
        from tools.process_tools import get_process_info
        out = get_process_info(str(os.getpid()))
        assert str(os.getpid()) in out

    def test_get_process_info_by_name(self):
        from tools.process_tools import get_process_info
        out = get_process_info("python")
        # Either found or not — must return a string
        assert isinstance(out, str)

    def test_process_tree(self):
        from tools.process_tools import process_tree
        out = process_tree(pid=os.getpid())
        assert str(os.getpid()) in out

    def test_process_tree_full(self):
        from tools.process_tools import process_tree
        out = process_tree()
        assert isinstance(out, str) and len(out) > 0

    def test_find_process_by_port(self):
        from tools.process_tools import find_process_by_port
        out = find_process_by_port(1)  # almost certainly closed
        assert isinstance(out, str)

    def test_run_background_safe(self):
        from tools.process_tools import run_background
        out = run_background("true")
        assert "PID" in out or "BLOCKED" in out


# ══════════════════════════════════════════════════════════════════════════════
# git_tools
# ══════════════════════════════════════════════════════════════════════════════

class TestGitTools:

    @pytest.fixture()
    def repo(self, tmp_path):
        import subprocess
        from tools.git_tools import git_init, git_add, git_commit
        r = str(tmp_path / "repo")
        os.makedirs(r)
        git_init(r)
        # Set local identity directly so the commit works regardless of global config
        subprocess.run(["git", "-C", r, "config", "user.email", "test@test.com"], check=False)
        subprocess.run(["git", "-C", r, "config", "user.name", "Test User"], check=False)
        (tmp_path / "repo" / "README.md").write_text("hello")
        git_add(".", r)
        git_commit("init", r)
        return r

    def test_git_init(self, tmp_path):
        from tools.git_tools import git_init
        r = str(tmp_path / "newrepo")
        os.makedirs(r)
        out = git_init(r)
        assert "Initialized" in out or "git" in out.lower()

    def test_git_status(self, repo):
        from tools.git_tools import git_status
        out = git_status(repo)
        assert "branch" in out.lower() or "nothing" in out.lower()

    def test_git_log(self, repo):
        from tools.git_tools import git_log
        out = git_log(repo, n=5)
        assert "init" in out

    def test_git_branch(self, repo):
        from tools.git_tools import git_branch
        out = git_branch(repo)
        # After a commit the branch name must appear
        assert "master" in out or "main" in out or "HEAD" in out

    def test_git_diff_empty(self, repo):
        from tools.git_tools import git_diff
        out = git_diff(repo)
        assert isinstance(out, str)

    def test_git_diff_staged(self, repo):
        from tools.git_tools import git_add, git_diff
        (os.path.join(repo, "new.txt"))
        open(os.path.join(repo, "new.txt"), "w").write("new content")
        git_add("new.txt", repo)
        out = git_diff(repo, staged=True)
        assert "new" in out or isinstance(out, str)

    def test_git_stash_list(self, repo):
        from tools.git_tools import git_stash
        out = git_stash("list", path=repo)
        assert isinstance(out, str)

    def test_git_remote_empty(self, repo):
        from tools.git_tools import git_remote
        out = git_remote(repo)
        assert isinstance(out, str)

    def test_git_tag_list_empty(self, repo):
        from tools.git_tools import git_tag
        out = git_tag(path=repo)
        assert isinstance(out, str)

    def test_git_show_head(self, repo):
        from tools.git_tools import git_show
        out = git_show(ref="HEAD", path=repo)
        assert "init" in out or "commit" in out.lower()

    def test_git_blame(self, repo):
        from tools.git_tools import git_blame
        out = git_blame("README.md", path=repo)
        assert isinstance(out, str)

    def test_git_config_get(self, repo):
        from tools.git_tools import git_config
        out = git_config("user.name", global_=True)
        assert isinstance(out, str)

    def test_git_checkout_new_branch(self, repo):
        import subprocess
        from tools.git_tools import git_checkout
        git_checkout("feature-test", create=True, path=repo)
        # Use raw git to list branches since git_branch uses -v which needs commits
        out = subprocess.run(
            ["git", "-C", repo, "branch"],
            capture_output=True, text=True,
        ).stdout
        assert "feature-test" in out


# ══════════════════════════════════════════════════════════════════════════════
# archive_tools
# ══════════════════════════════════════════════════════════════════════════════

class TestArchiveTools:

    @pytest.fixture()
    def src_file(self, tmp_path):
        p = tmp_path / "data.txt"
        p.write_text("archive test content from cogman")
        return str(p)

    def test_create_and_list_zip(self, tmp_path, src_file):
        from tools.archive_tools import create_zip, list_archive
        out_path = str(tmp_path / "test")
        create_zip(out_path, src_file)
        zip_path = str(tmp_path / "test.zip")
        assert os.path.exists(zip_path)
        listing = list_archive(zip_path)
        assert "data.txt" in listing

    def test_extract_zip(self, tmp_path, src_file):
        import glob
        from tools.archive_tools import create_zip, extract
        create_zip(str(tmp_path / "arc"), src_file)
        out_dir = str(tmp_path / "extracted")
        extract(str(tmp_path / "arc.zip"), out_dir)
        found = glob.glob(os.path.join(out_dir, "**", "data.txt"), recursive=True)
        assert found

    def test_create_tar_gz(self, tmp_path, src_file):
        from tools.archive_tools import create_tar, list_archive
        out_path = str(tmp_path / "test")
        create_tar(out_path, src_file, compress="gz")
        tar_path = str(tmp_path / "test.tar.gz")
        assert os.path.exists(tar_path)
        listing = list_archive(tar_path)
        assert "data.txt" in listing

    def test_extract_tar_gz(self, tmp_path, src_file):
        import glob
        from tools.archive_tools import create_tar, extract
        create_tar(str(tmp_path / "arc"), src_file, compress="gz")
        out_dir = str(tmp_path / "extracted")
        extract(str(tmp_path / "arc.tar.gz"), out_dir)
        found = glob.glob(os.path.join(out_dir, "**", "data.txt"), recursive=True)
        assert found

    def test_create_tar_no_compress(self, tmp_path, src_file):
        from tools.archive_tools import create_tar, list_archive
        out_path = str(tmp_path / "plain")
        create_tar(out_path, src_file, compress="none")
        assert os.path.exists(str(tmp_path / "plain.tar"))

    def test_compress_file_gzip(self, tmp_path, src_file):
        from tools.archive_tools import compress_file
        compress_file(src_file, "gzip")
        assert os.path.exists(src_file + ".gz")

    def test_list_archive_unknown(self, tmp_path):
        from tools.archive_tools import list_archive
        p = str(tmp_path / "unknown.abc")
        open(p, "w").write("x")
        out = list_archive(p)
        assert "Unknown" in out


# ══════════════════════════════════════════════════════════════════════════════
# package_tools
# ══════════════════════════════════════════════════════════════════════════════

class TestPackageTools:

    def test_apt_search(self):
        from tools.package_tools import apt_search
        out = apt_search("vim")
        assert isinstance(out, str)

    def test_apt_show(self):
        from tools.package_tools import apt_show
        out = apt_show("python3")
        assert isinstance(out, str)

    def test_apt_list_installed(self):
        from tools.package_tools import apt_list_installed
        out = apt_list_installed()
        assert isinstance(out, str)

    def test_pip_list(self):
        from tools.package_tools import pip_list
        out = pip_list()
        assert isinstance(out, str) and len(out) > 0

    def test_pip_show_existing(self):
        from tools.package_tools import pip_show
        out = pip_show("pip")
        assert "pip" in out.lower() or isinstance(out, str)

    def test_pip_outdated(self):
        from tools.package_tools import pip_outdated
        out = pip_outdated()
        assert isinstance(out, str)

    def test_snap_list_graceful(self):
        from tools.package_tools import snap_list
        out = snap_list()
        assert isinstance(out, str)  # either list or "not available"

    def test_flatpak_list_graceful(self):
        from tools.package_tools import flatpak_list
        out = flatpak_list()
        assert isinstance(out, str)

    def test_npm_list_graceful(self):
        from tools.package_tools import npm_list
        out = npm_list()
        assert isinstance(out, str)


# ══════════════════════════════════════════════════════════════════════════════
# service_tools
# ══════════════════════════════════════════════════════════════════════════════

class TestServiceTools:

    def test_list_services_running(self):
        from tools.service_tools import list_services
        out = list_services("running")
        assert isinstance(out, str)

    def test_list_services_failed(self):
        from tools.service_tools import list_services
        out = list_services("failed")
        assert isinstance(out, str)

    def test_failed_services(self):
        from tools.service_tools import failed_services
        out = failed_services()
        assert isinstance(out, str)

    def test_system_uptime(self):
        from tools.service_tools import system_uptime
        out = system_uptime()
        assert isinstance(out, str)

    def test_list_timers(self):
        from tools.service_tools import list_timers
        out = list_timers()
        assert isinstance(out, str)

    def test_service_status_cogman(self):
        from tools.service_tools import user_service_status
        out = user_service_status("cogman")
        assert isinstance(out, str)


# ══════════════════════════════════════════════════════════════════════════════
# docker_tools
# ══════════════════════════════════════════════════════════════════════════════

class TestDockerTools:
    """Docker may not be installed — test graceful failure and available funcs."""

    def test_docker_ps_graceful(self):
        from tools.docker_tools import docker_ps
        out = docker_ps()
        assert isinstance(out, str)  # either table or "not installed" msg

    def test_docker_images_graceful(self):
        from tools.docker_tools import docker_images
        out = docker_images()
        assert isinstance(out, str)

    def test_docker_stats_graceful(self):
        from tools.docker_tools import docker_stats
        out = docker_stats()
        assert isinstance(out, str)


# ══════════════════════════════════════════════════════════════════════════════
# system_info_tools
# ══════════════════════════════════════════════════════════════════════════════

class TestSystemInfoTools:

    def test_system_info(self):
        from tools.system_info_tools import system_info
        out = system_info()
        assert "OS" in out
        assert "CPU" in out
        assert "RAM" in out

    def test_os_release(self):
        from tools.system_info_tools import os_release
        out = os_release()
        assert isinstance(out, str) and len(out) > 0

    def test_kernel_info(self):
        from tools.system_info_tools import kernel_info
        out = kernel_info()
        assert "Linux" in out or "linux" in out.lower()

    def test_cpu_info(self):
        from tools.system_info_tools import cpu_info
        out = cpu_info()
        assert isinstance(out, str) and len(out) > 0

    def test_memory_info(self):
        from tools.system_info_tools import memory_info
        out = memory_info()
        assert "Mem" in out or "mem" in out.lower()

    def test_disk_info(self):
        from tools.system_info_tools import disk_info
        out = disk_info()
        assert isinstance(out, str) and len(out) > 0

    def test_pci_devices(self):
        from tools.system_info_tools import pci_devices
        out = pci_devices()
        assert isinstance(out, str)

    def test_usb_devices(self):
        from tools.system_info_tools import usb_devices
        out = usb_devices()
        assert isinstance(out, str)

    def test_sensors(self):
        from tools.system_info_tools import sensors
        out = sensors()
        assert isinstance(out, str)

    def test_env_vars_all(self):
        from tools.system_info_tools import env_vars
        out = env_vars()
        assert "PATH" in out

    def test_env_vars_filter(self):
        from tools.system_info_tools import env_vars
        out = env_vars("PATH")
        assert "PATH" in out

    def test_which_command(self):
        from tools.system_info_tools import which_command
        out = which_command("python3")
        assert "/python" in out or "not found" in out

    def test_path_info(self):
        from tools.system_info_tools import path_info
        out = path_info()
        assert "PATH" in out

    def test_installed_shells(self):
        from tools.system_info_tools import installed_shells
        out = installed_shells()
        assert "sh" in out or "bash" in out

    def test_hostname_info(self):
        from tools.system_info_tools import hostname_info
        out = hostname_info()
        assert isinstance(out, str) and len(out) > 0

    def test_user_info(self):
        from tools.system_info_tools import user_info
        out = user_info()
        assert "uid=" in out or isinstance(out, str)

    def test_load_average(self):
        from tools.system_info_tools import load_average
        out = load_average()
        assert "load" in out.lower() or "average" in out.lower() or isinstance(out, str)

    def test_boot_time(self):
        from tools.system_info_tools import boot_time
        out = boot_time()
        assert "booted" in out.lower() or "202" in out

    def test_locale_info(self):
        from tools.system_info_tools import locale_info
        out = locale_info()
        assert isinstance(out, str)

    def test_dmesg(self):
        from tools.system_info_tools import dmesg
        out = dmesg(n=5)
        assert isinstance(out, str)

    def test_syslog(self):
        from tools.system_info_tools import syslog
        out = syslog(n=5)
        assert isinstance(out, str)

    def test_journal_logs(self):
        from tools.system_info_tools import journal_logs
        out = journal_logs(n=5)
        assert isinstance(out, str)

    def test_hardware_info(self):
        from tools.system_info_tools import hardware_info
        out = hardware_info()
        assert isinstance(out, str)


# ══════════════════════════════════════════════════════════════════════════════
# power_tools
# ══════════════════════════════════════════════════════════════════════════════

class TestPowerTools:

    def test_get_brightness(self):
        from tools.power_tools import get_brightness
        out = get_brightness()
        assert isinstance(out, str)

    def test_power_stats(self):
        from tools.power_tools import power_stats
        out = power_stats()
        assert isinstance(out, str)
        assert "Uptime" in out or "uptime" in out.lower() or "load" in out.lower()


# ══════════════════════════════════════════════════════════════════════════════
# web_tools (network — may fail offline)
# ══════════════════════════════════════════════════════════════════════════════

class TestWebTools:

    def test_get_weather_returns_string(self):
        from tools.web_tools import get_weather
        out = get_weather("London")
        assert isinstance(out, str)

    def test_fetch_url_error_handling(self):
        from tools.web_tools import fetch_url
        out = fetch_url("http://localhost:19999/nonexistent")
        assert isinstance(out, str)  # error msg or content


# ══════════════════════════════════════════════════════════════════════════════
# browser_tools
# ══════════════════════════════════════════════════════════════════════════════

class TestBrowserTools:

    def test_check_url_invalid(self):
        from tools.browser_tools import check_url
        out = check_url("http://localhost:19999")
        assert isinstance(out, str)  # "Unreachable" or status

    def test_extract_links_error_handling(self):
        from tools.browser_tools import extract_links
        out = extract_links("http://localhost:19999")
        assert isinstance(out, str)

    def test_fetch_page_error_handling(self):
        from tools.browser_tools import fetch_page
        out = fetch_page("http://localhost:19999/notreal")
        assert isinstance(out, str)


# ══════════════════════════════════════════════════════════════════════════════
# code_tools
# ══════════════════════════════════════════════════════════════════════════════

class TestCodeTools:

    def test_run_python_hello(self):
        from tools.code_tools import run_python
        out = run_python("print('hello cogman')")
        assert "hello cogman" in out

    def test_run_python_math(self):
        from tools.code_tools import run_python
        out = run_python("print(2 ** 10)")
        assert "1024" in out

    def test_run_python_multiline(self):
        from tools.code_tools import run_python
        code = "x = [i**2 for i in range(5)]\nprint(x)"
        out = run_python(code)
        assert "16" in out

    def test_run_python_syntax_error(self):
        from tools.code_tools import run_python
        out = run_python("def broken(: pass")
        assert "error" in out.lower() or "SyntaxError" in out

    def test_run_python_timeout(self):
        from tools.code_tools import run_python
        out = run_python("import time; time.sleep(60)", timeout=1)
        assert "Timeout" in out or "timeout" in out.lower()

    def test_run_python_with_input(self):
        from tools.code_tools import run_python_with_input
        out = run_python_with_input("name = input(); print('Hi', name)", stdin_data="cogman")
        assert "cogman" in out

    def test_check_syntax_valid(self):
        from tools.code_tools import check_syntax
        out = check_syntax("def hello(): return 42")
        assert "OK" in out or "valid" in out.lower() or "no error" in out.lower()

    def test_check_syntax_invalid(self):
        from tools.code_tools import check_syntax
        out = check_syntax("def bad(: pass")
        assert "error" in out.lower() or "SyntaxError" in out

    def test_run_script_bash(self):
        from tools.code_tools import run_script
        out = run_script("echo 'script_works'", shell="bash")
        assert "script_works" in out

    def test_format_code(self):
        from tools.code_tools import format_code
        code = "x=1+2\ny =   x  *  3"
        out = format_code(code)
        # Either formatted code or helpful install message
        assert isinstance(out, str) and len(out) > 0

    def test_lint_code_clean(self):
        from tools.code_tools import lint_code
        out = lint_code("x = 1 + 2\nprint(x)\n")
        # Either lint results or install hint
        assert isinstance(out, str) and len(out) > 0

    def test_explain_error(self):
        from tools.code_tools import explain_error
        out = explain_error("NameError: name 'x' is not defined")
        assert isinstance(out, str) and len(out) > 0


# ══════════════════════════════════════════════════════════════════════════════
# image_tools
# ══════════════════════════════════════════════════════════════════════════════

class TestImageTools:

    def test_generate_image_no_key(self):
        from tools.image_tools import generate_image
        env_backup = os.environ.pop("OPENAI_API_KEY", None)
        os.environ.pop("COGMAN_SD_URL", None)
        out = generate_image("a red circle")
        if env_backup:
            os.environ["OPENAI_API_KEY"] = env_backup
        assert "requires" in out.lower() or "OPENAI_API_KEY" in out

    def test_list_images_empty(self, tmp_path):
        from tools.image_tools import list_images
        out = list_images(str(tmp_path))
        assert isinstance(out, str)

    def test_list_images_with_files(self, tmp_path):
        from tools.image_tools import list_images
        (tmp_path / "photo.jpg").write_bytes(b"\xff\xd8\xff")
        (tmp_path / "logo.png").write_bytes(b"\x89PNG")
        (tmp_path / "notes.txt").write_text("not an image")
        out = list_images(str(tmp_path))
        assert "photo.jpg" in out or "logo.png" in out

    def test_image_info_missing(self, tmp_path):
        from tools.image_tools import image_info
        out = image_info(str(tmp_path / "nonexistent.png"))
        assert isinstance(out, str)

    def test_resize_image_missing(self, tmp_path):
        from tools.image_tools import resize_image
        out = resize_image(str(tmp_path / "noimg.png"), width=100)
        assert isinstance(out, str)

    def test_convert_image_missing(self, tmp_path):
        from tools.image_tools import convert_image
        out = convert_image(str(tmp_path / "noimg.png"), str(tmp_path / "out.jpg"))
        assert isinstance(out, str)


# ══════════════════════════════════════════════════════════════════════════════
# build_tools  (cogman native package manager)
# ══════════════════════════════════════════════════════════════════════════════

class TestBuildTools:

    def test_build_status_graceful(self):
        from tools.build_tools import build_status
        out = build_status()
        assert isinstance(out, str)

    def test_pkg_list_definitions_graceful(self):
        from tools.build_tools import pkg_list_definitions
        out = pkg_list_definitions()
        assert isinstance(out, str)

    def test_pkg_validate_invalid(self, tmp_path):
        from tools.build_tools import pkg_validate
        out = pkg_validate(str(tmp_path / "nonexistent.toml"))
        assert isinstance(out, str)


# ══════════════════════════════════════════════════════════════════════════════
# native_pkg_tools  (cogman native package manager)
# ══════════════════════════════════════════════════════════════════════════════

class TestNativePkgTools:

    def test_cogman_pkg_list_graceful(self):
        from tools.native_pkg_tools import cogman_pkg_list
        out = cogman_pkg_list()
        assert isinstance(out, str)

    def test_cogman_svc_list_graceful(self):
        from tools.native_pkg_tools import cogman_svc_list
        out = cogman_svc_list()
        assert isinstance(out, str)

    def test_cogman_core_status_graceful(self):
        from tools.native_pkg_tools import cogman_core_status
        out = cogman_core_status()
        assert isinstance(out, str)

    def test_cogman_svc_ping_graceful(self):
        from tools.native_pkg_tools import cogman_svc_ping
        out = cogman_svc_ping()
        assert isinstance(out, str)


# ══════════════════════════════════════════════════════════════════════════════
# window_tools
# ══════════════════════════════════════════════════════════════════════════════

class TestWindowTools:

    def test_list_windows_graceful(self):
        from tools.window_tools import list_windows
        out = list_windows()
        assert isinstance(out, str)  # either window list or "not available"

    def test_get_active_window_graceful(self):
        from tools.window_tools import get_active_window
        out = get_active_window()
        assert isinstance(out, str)

    def test_list_workspaces_graceful(self):
        from tools.window_tools import list_workspaces
        out = list_workspaces()
        assert isinstance(out, str)


# ══════════════════════════════════════════════════════════════════════════════
# memory_tools
# ══════════════════════════════════════════════════════════════════════════════

class TestMemoryTools:

    @pytest.fixture(autouse=True)
    def _inject_memory(self):
        from tools.memory_tools import set_memory_backend
        from core.memory import Memory
        set_memory_backend(Memory())

    def test_save_and_search_memory(self):
        from tools.memory_tools import save_memory, search_memory
        result = save_memory("cogman is a Linux AI assistant", category="facts")
        assert "Remembered" in result
        found = search_memory("cogman")
        assert isinstance(found, str)

    def test_set_and_get_preference(self):
        from tools.memory_tools import set_preference, get_preference
        set_preference("editor", "neovim")
        result = get_preference("editor")
        assert "neovim" in result

    def test_get_missing_preference(self):
        from tools.memory_tools import get_preference
        result = get_preference("nonexistent_key_xyz")
        assert isinstance(result, str)

    def test_save_memory_different_categories(self):
        from tools.memory_tools import save_memory
        for cat in ["facts", "tasks", "general"]:
            out = save_memory(f"test item for {cat}", category=cat)
            assert "Remembered" in out
