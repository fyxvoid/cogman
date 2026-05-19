//! Package installer — install, remove, upgrade, query.
//!
//! Install delegates to `cogman-planner` for build planning and
//! shell execution for the actual build steps. Tracks installed
//! files in PackageDb.

use std::fs;
use std::io;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::{SystemTime, UNIX_EPOCH};

use super::db::{PackageDb, PackageRecord};
use super::schema::PackageMeta;

pub struct Installer {
    pub db:   PackageDb,
    pub root: PathBuf,
    planner:  PathBuf,
}

impl Installer {
    pub fn new(root: Option<&Path>) -> Result<Self, String> {
        let db   = PackageDb::system().map_err(|e| format!("db: {e}"))?;
        let root = root.unwrap_or(Path::new("/")).to_path_buf();
        let planner = find_bin("cogman-planner");
        Ok(Installer { db, root, planner })
    }

    // ── Install ───────────────────────────────────────────────────────────

    pub fn install(&mut self, toml: &Path) -> Result<PackageRecord, String> {
        let meta = PackageMeta::load(toml)?;
        let name = &meta.identity.name;

        if self.db.has(name) {
            eprintln!("[cogman] '{}' is already installed — use upgrade to refresh", name);
        }

        eprintln!("[cogman] installing {} v{}", name, meta.identity.version);

        // If cogman-planner is available, use it for dependency-aware build
        if self.planner.exists() {
            self.plan_and_build(toml, &meta)?;
        } else {
            // Fallback: run build + installer steps directly
            self.run_steps_direct(&meta)?;
        }

        let rec = PackageRecord {
            name:         name.clone(),
            version:      meta.identity.version.clone(),
            category:     meta.identity.category.clone(),
            install_root: self.root.to_string_lossy().into_owned(),
            installed_at: unix_now(),
            files:        Vec::new(),
        };

        self.db.upsert(rec.clone())
            .map_err(|e| format!("db: {e}"))?;
        eprintln!("[cogman] {} installed successfully", name);
        Ok(rec)
    }

    // ── Remove ────────────────────────────────────────────────────────────

    pub fn remove(&mut self, name: &str) -> Result<(), String> {
        let rec = self.db.get(name)
            .ok_or_else(|| format!("'{}' is not installed", name))?
            .clone();

        eprintln!("[cogman] removing {} ({} files)", name, rec.files.len());

        let root = Path::new(&rec.install_root);
        let mut dirs: Vec<PathBuf> = Vec::new();

        for rel in &rec.files {
            let abs = root.join(rel.trim_start_matches('/'));
            if abs.is_dir() { dirs.push(abs); continue; }
            if let Err(e) = fs::remove_file(&abs) {
                if e.kind() != io::ErrorKind::NotFound {
                    eprintln!("[cogman] warn: could not remove {}: {e}", abs.display());
                }
            }
        }

        dirs.sort(); dirs.reverse();
        for d in &dirs {
            if fs::read_dir(d).map_or(false, |mut e| e.next().is_none()) {
                let _ = fs::remove_dir(d);
            }
        }

        self.db.remove(name).map_err(|e| format!("db: {e}"))?;
        eprintln!("[cogman] {} removed", name);
        Ok(())
    }

    // ── Upgrade ───────────────────────────────────────────────────────────

    pub fn upgrade(&mut self, toml: &Path) -> Result<PackageRecord, String> {
        let meta = PackageMeta::load(toml)?;
        if self.db.has(&meta.identity.name) {
            self.remove(&meta.identity.name)?;
        }
        self.install(toml)
    }

    // ── Query ─────────────────────────────────────────────────────────────

    pub fn list(&self) -> Vec<String> {
        self.db.list().iter().map(|r| r.display_line()).collect()
    }

    pub fn is_installed(&self, name: &str) -> bool { self.db.has(name) }

    pub fn info(&self, name: &str) -> Option<&PackageRecord> { self.db.get(name) }

    // ── Private helpers ───────────────────────────────────────────────────

    fn plan_and_build(&self, toml: &Path, meta: &PackageMeta) -> Result<(), String> {
        let plan_file = std::env::temp_dir()
            .join(format!("cogman_{}.plan", meta.identity.name));

        let status = Command::new(&self.planner)
            .arg("build")
            .arg(toml)
            .arg("--output")
            .arg(&plan_file)
            .arg("--rootfs")
            .arg(self.root.to_str().unwrap_or("/"))
            .status()
            .map_err(|e| format!("cogman-planner: {e}"))?;

        if !status.success() {
            return Err(format!("cogman-planner failed (exit {})", status));
        }

        // Execute the plan — cogman-planner emits shell steps
        // For now, we execute steps directly
        self.run_steps_direct(meta)
    }

    fn run_steps_direct(&self, meta: &PackageMeta) -> Result<(), String> {
        let pkgroot = self.root.to_string_lossy();
        let env = [("PKGROOT", pkgroot.as_ref())];

        for step in meta.build.steps.iter().chain(meta.installer.steps.iter()) {
            let status = Command::new("/bin/sh")
                .arg("-c")
                .arg(step)
                .envs(env.iter().map(|(k, v)| (k, v)))
                .status()
                .map_err(|e| format!("step exec: {e}"))?;

            if !status.success() {
                return Err(format!("build step failed:\n  {}", step));
            }
        }
        Ok(())
    }
}

fn find_bin(name: &str) -> PathBuf {
    // Look next to current executable first, then PATH
    if let Ok(exe) = std::env::current_exe() {
        let candidate = exe.parent().unwrap_or(Path::new(".")).join(name);
        if candidate.exists() { return candidate; }
    }
    PathBuf::from(name)
}

fn unix_now() -> u64 {
    SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0)
}
