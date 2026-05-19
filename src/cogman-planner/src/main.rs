//! cogman-planner — TOML package manifest → dependency-ordered build plan.
//!
//! Usage:
//!   cogman-planner build   <pkg.toml> [options]
//!   cogman-planner inspect <pkg.toml>          — show metadata
//!   cogman-planner deps    <pkg.toml>           — print dep order
//!
//! Options:
//!   --output <file>   write plan to file instead of stdout
//!   --rootfs <path>   installation root (default: /)
//!   --pkgroot <path>  staging root during build (default: /tmp/pkgroot)
//!   --json            emit JSON instead of shell script
//!   --explain         show dependency resolution steps

mod metadata;
mod graph;
mod plan;

use std::collections::HashMap;
use std::io::BufWriter;
use std::path::PathBuf;
use std::process;

use clap::{Parser, Subcommand};
use graph::Loader;
use metadata::{load, PackageMeta};
use plan::{make_steps, emit_shell, emit_json};

// ── CLI ───────────────────────────────────────────────────────────────────

#[derive(Parser)]
#[command(
    name  = "cogman-planner",
    version = "1.0.0",
    about = "COGMAN build planner — resolve deps and emit a build plan",
)]
struct Cli {
    #[command(subcommand)]
    cmd: Cmd,
}

#[derive(Subcommand)]
enum Cmd {
    /// Resolve dependencies and emit a build plan.
    Build {
        toml: PathBuf,
        #[arg(long)]
        output:  Option<PathBuf>,
        #[arg(long, default_value = "/")]
        rootfs:  String,
        #[arg(long, default_value = "/tmp/pkgroot")]
        pkgroot: String,
        #[arg(long)]
        json:    bool,
        #[arg(long)]
        explain: bool,
    },

    /// Show package metadata.
    Inspect { toml: PathBuf },

    /// Print dependency build order.
    Deps {
        toml: PathBuf,
        #[arg(long)]
        json: bool,
    },
}

// ── Entry point ───────────────────────────────────────────────────────────

fn main() {
    let cli = Cli::parse();
    match cli.cmd {
        Cmd::Build { toml, output, rootfs, pkgroot, json, explain } => {
            run_build(&toml, output.as_deref(), &rootfs, &pkgroot, json, explain);
        }
        Cmd::Inspect { toml } => run_inspect(&toml),
        Cmd::Deps    { toml, json } => run_deps(&toml, json),
    }
}

// ── Build ─────────────────────────────────────────────────────────────────

fn run_build(
    toml_path: &std::path::Path,
    output:    Option<&std::path::Path>,
    rootfs:    &str,
    pkgroot:   &str,
    json:      bool,
    explain:   bool,
) {
    let meta = load_or_die(toml_path);
    let workspace = workspace_root(toml_path);

    if explain {
        eprintln!("[planner] resolving deps for {}", meta.full_name());
    }

    let mut loader = Loader::new(workspace);
    if let Err(e) = loader.inject_root(&meta) {
        eprintln!("[planner] dependency error: {e}"); process::exit(1);
    }

    let order = match loader.graph.build_order() {
        Ok(o)  => o,
        Err(e) => { eprintln!("[planner] {e}"); process::exit(1); }
    };

    if explain {
        eprintln!("[planner] build order ({} package(s)):", order.len());
        for (i, p) in order.iter().enumerate() {
            eprintln!("  {i}. {p}");
        }
    }

    let steps = make_steps(&order, &loader.metas, rootfs, pkgroot);

    match output {
        Some(path) => {
            let f = std::fs::File::create(path).unwrap_or_else(|e| {
                eprintln!("[planner] cannot create {}: {e}", path.display()); process::exit(1);
            });
            let mut w = BufWriter::new(f);
            if json { emit_json(&steps, &meta, &mut w).ok(); }
            else    { emit_shell(&steps, &mut w).ok(); }
            eprintln!("[planner] plan written to {} ({} steps)", path.display(), steps.len());
        }
        None => {
            let stdout = std::io::stdout();
            let mut w  = BufWriter::new(stdout.lock());
            if json { emit_json(&steps, &meta, &mut w).ok(); }
            else    { emit_shell(&steps, &mut w).ok(); }
        }
    }
}

// ── Inspect ───────────────────────────────────────────────────────────────

fn run_inspect(toml_path: &std::path::Path) {
    let meta = load_or_die(toml_path);
    println!("name:        {}", meta.identity.name);
    println!("version:     {}", meta.identity.version);
    println!("category:    {}", meta.identity.category);
    println!("summary:     {}", meta.identity.summary);
    println!("build:       {:?} ({} steps)", meta.build.system, meta.build.steps.len());
    println!("install:     {} steps", meta.installer.steps.len());
    println!("build deps:  {:?}", meta.identity.depends.build);
    println!("runtime deps:{:?}", meta.identity.depends.runtime);
    println!("network:     {}", meta.policy.network.outbound);
    println!("write paths: {:?}", meta.policy.filesystem.write);
}

// ── Deps ──────────────────────────────────────────────────────────────────

fn run_deps(toml_path: &std::path::Path, json: bool) {
    let meta      = load_or_die(toml_path);
    let workspace = workspace_root(toml_path);
    let mut loader = Loader::new(workspace);
    if let Err(e) = loader.inject_root(&meta) {
        eprintln!("[planner] {e}"); process::exit(1);
    }
    let order = match loader.graph.build_order() {
        Ok(o)  => o,
        Err(e) => { eprintln!("[planner] {e}"); process::exit(1); }
    };
    if json {
        println!("{}", serde_json::to_string_pretty(&order).unwrap_or_default());
    } else {
        for (i, p) in order.iter().enumerate() {
            println!("{i:3}. {p}");
        }
    }
}

// ── Helpers ───────────────────────────────────────────────────────────────

fn load_or_die(path: &std::path::Path) -> PackageMeta {
    load(path).unwrap_or_else(|e| {
        eprintln!("[planner] {e}"); process::exit(1);
    })
}

/// Infer workspace root from package toml path:
///   packages/<cat>/<name>/<name>.toml  →  workspace root
fn workspace_root(toml: &std::path::Path) -> PathBuf {
    toml.parent()          // name dir
        .and_then(|p| p.parent())   // cat dir
        .and_then(|p| p.parent())   // packages dir
        .and_then(|p| p.parent())   // workspace root
        .map(PathBuf::from)
        .unwrap_or_else(|| std::env::current_dir().unwrap_or_else(|_| PathBuf::from(".")))
}
