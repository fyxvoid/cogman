"""
Verify every tool is directly callable as a Python function.
No LLM, no registry, no orchestrator — just raw function calls.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── Style 1: flat import ─────────────────────────────────────────────────────

def test_flat_import_system():
    from tools import get_time, get_date, cpu_usage, memory_usage, disk_usage
    assert "time" in get_time().lower() or ":" in get_time()
    assert "today" in get_date().lower() or "202" in get_date()
    assert "%" in cpu_usage()
    assert "RAM" in memory_usage()
    assert "GB" in disk_usage()


def test_flat_import_shell():
    from tools import run_shell
    out = run_shell("echo cogman_works")
    assert "cogman_works" in out


def test_flat_import_file(tmp_path):
    from tools import write_file, read_file, list_files, find_files
    p = str(tmp_path / "hello.txt")
    write_file(p, "hello cogman", overwrite=True)
    content = read_file(p)
    assert "hello cogman" in content
    listing = list_files(str(tmp_path))
    assert "hello.txt" in listing
    found = find_files("*.txt", str(tmp_path))
    assert "hello.txt" in found


def test_flat_import_text(tmp_path):
    from tools import (
        grep_in_file, word_count, hash_text, base64_encode,
        base64_decode, sort_lines, head_file, tail_file,
    )
    p = str(tmp_path / "data.txt")
    with open(p, "w") as f:
        f.write("banana\napple\ncherry\napple\n")

    assert "apple" in grep_in_file("apple", p)
    assert "4" in word_count(p)                         # 4 lines

    h = hash_text("cogman", "sha256")
    assert "SHA256" in h and len(h) > 20

    enc = base64_encode("hello")
    assert enc == "aGVsbG8="
    dec = base64_decode("aGVsbG8=")
    assert dec == "hello"

    sorted_ = sort_lines("banana\napple\ncherry")
    assert sorted_.split("\n")[0] == "apple"

    assert "banana" in head_file(p, 1)
    assert "apple" in tail_file(p, 1)


def test_flat_import_calculate():
    from tools import calculate, unit_convert
    assert "144" in calculate("12 ** 2")
    assert "3.14" in calculate("round(pi, 2)")
    result = unit_convert(1.0, "km", "m")
    assert "1000" in result
    result_f = unit_convert(0.0, "c", "f")
    assert "32" in result_f


def test_flat_import_hash_file(tmp_path):
    from tools import hash_file
    p = str(tmp_path / "test.bin")
    with open(p, "wb") as f:
        f.write(b"cogman")
    out = hash_file(p, "md5")
    assert "MD5" in out


def test_flat_import_base64():
    from tools import base64_encode, base64_decode
    for text in ["hello world", "cogman AI", "123!@#"]:
        encoded = base64_encode(text)
        decoded = base64_decode(encoded)
        assert decoded == text


def test_flat_import_archive(tmp_path):
    from tools import create_zip, list_archive, extract
    # Create a file to archive
    src = tmp_path / "src.txt"
    src.write_text("cogman archive test")
    zip_path = str(tmp_path / "test")
    result = create_zip(zip_path, str(src))
    assert os.path.exists(str(tmp_path / "test.zip"))
    # List it
    listing = list_archive(str(tmp_path / "test.zip"))
    assert "src.txt" in listing
    # Extract it
    out_dir = str(tmp_path / "extracted")
    extract(str(tmp_path / "test.zip"), out_dir)
    import glob
    found = glob.glob(os.path.join(out_dir, "**", "src.txt"), recursive=True)
    assert found, f"src.txt not found under {out_dir}"


def test_flat_import_process():
    from tools import top_processes, list_processes, get_process_info
    top = top_processes(n=5, sort_by="cpu")
    assert "CPU%" in top
    procs = list_processes()
    assert len(procs) > 10
    # look up current python process
    import os
    info = get_process_info(str(os.getpid()))
    assert str(os.getpid()) in info


def test_flat_import_network():
    from tools import get_local_ip, list_open_ports, check_port
    ip = get_local_ip()
    # Should return something (may be empty in some envs)
    assert isinstance(ip, str)
    ports = list_open_ports()
    assert isinstance(ports, str)
    result = check_port("127.0.0.1", 1)   # port 1 almost certainly closed
    assert "CLOSED" in result or "OPEN" in result or "UNREACHABLE" in result


def test_flat_import_git(tmp_path):
    from tools import git_init, git_status, git_config
    repo = str(tmp_path / "repo")
    os.makedirs(repo)
    result = git_init(repo)
    assert "Initialized" in result or "git" in result.lower()
    status = git_status(repo)
    assert "branch" in status.lower() or "nothing" in status.lower()


def test_flat_import_memory():
    from tools import save_memory, search_memory, set_preference, get_preference
    from tools import set_memory_backend
    from core.memory import Memory
    set_memory_backend(Memory())

    result = save_memory("cogman is awesome", category="test")
    assert "Remembered" in result

    result = set_preference("theme", "dark")
    assert "dark" in result

    result = get_preference("theme")
    assert "dark" in result


# ── Style 2: namespace import ────────────────────────────────────────────────

def test_namespace_import():
    import tools
    assert ":" in tools.get_time()
    assert "GB" in tools.disk_usage()
    assert "cogman_ns" in tools.run_shell("echo cogman_ns")


# ── Style 3: CogmanTools grouped class ──────────────────────────────────────

def test_grouped_class_shell():
    from cogman_tools import CogmanTools
    c = CogmanTools()
    assert ":" in c.shell.get_time()
    assert "cogman_cls" in c.shell.run_shell("echo cogman_cls")


def test_grouped_class_git(tmp_path):
    from cogman_tools import CogmanTools
    c = CogmanTools()
    repo = str(tmp_path / "gitrepo")
    os.makedirs(repo)
    result = c.git.git_init(repo)
    assert "Initialized" in result or "git" in result.lower()
    status = c.git.git_status(repo)
    assert isinstance(status, str)


def test_grouped_class_text(tmp_path):
    from cogman_tools import CogmanTools
    c = CogmanTools()
    assert c.text.base64_encode("hi") == "aGk="
    assert c.text.base64_decode("aGk=") == "hi"
    assert "SHA256" in c.text.hash_text("x")


def test_grouped_class_misc():
    from cogman_tools import CogmanTools
    c = CogmanTools()
    assert "144" in c.misc.calculate("12**2")
    result = c.misc.unit_convert(100, "c", "f")
    assert "212" in result


def test_grouped_class_sysinfo():
    from cogman_tools import CogmanTools
    c = CogmanTools()
    info = c.sysinfo.system_info()
    assert "OS" in info
    assert "CPU" in info
    assert "RAM" in info


def test_grouped_class_help():
    from cogman_tools import CogmanTools
    c = CogmanTools()
    overview = c.help()
    assert "git" in overview
    assert "docker" in overview

    git_help = c.help("git")
    assert "git_status" in git_help
    assert "git_commit" in git_help


# ── Style 4: direct import from cogman_tools flat ────────────────────────────

def test_cogman_tools_flat_import():
    from cogman_tools import (
        calculate, git_status, docker_ps,
        apt_search, system_info, base64_encode,
    )
    assert isinstance(calculate("1+1"), str)
    assert isinstance(docker_ps(), str)
    assert isinstance(apt_search("vim"), str)
    assert "OS" in system_info()
    assert base64_encode("test") == "dGVzdA=="
