//! Build plan emitter.
//!
//! Two output modes:
//!   - `shell`  (default) — a shell script executable by /bin/sh
//!   - `json`             — structured JSON for tooling / AI consumption

use std::io::{self, Write};
use std::path::Path;

use crate::metadata::PackageMeta;

// ── Plan step ────────────────────────────────────────────────────────────

#[derive(Debug, serde::Serialize)]
pub struct PlanStep {
    pub package: String,
    pub phase:   Phase,
    pub command: String,
    pub workdir: Option<String>,
}

#[derive(Debug, serde::Serialize, Clone, Copy)]
#[serde(rename_all = "lowercase")]
pub enum Phase { Build, Install, Verify }

// ── Build plan from ordered list of metas ────────────────────────────────

pub fn make_steps(
    order:   &[String],
    metas:   &std::collections::HashMap<String, PackageMeta>,
    rootfs:  &str,
    pkgroot: &str,
) -> Vec<PlanStep> {
    let mut steps = Vec::new();

    for pkg_id in order {
        let Some(meta) = metas.get(pkg_id) else { continue };
        let env_prefix = format!(
            "export PKGROOT={pkgroot} ROOTFS={rootfs} PKGNAME={name} PKGVER={ver};\n",
            name = meta.identity.name,
            ver  = meta.identity.version,
        );

        for s in &meta.build.steps {
            steps.push(PlanStep {
                package: pkg_id.clone(),
                phase:   Phase::Build,
                command: format!("{env_prefix}{s}"),
                workdir: None,
            });
        }
        for s in &meta.installer.steps {
            steps.push(PlanStep {
                package: pkg_id.clone(),
                phase:   Phase::Install,
                command: format!("{env_prefix}{s}"),
                workdir: None,
            });
        }
    }
    steps
}

// ── Emitters ─────────────────────────────────────────────────────────────

pub fn emit_shell<W: Write>(steps: &[PlanStep], out: &mut W) -> io::Result<()> {
    writeln!(out, "#!/bin/sh")?;
    writeln!(out, "# cogman-planner generated build script")?;
    writeln!(out, "set -eu")?;
    writeln!(out)?;
    for step in steps {
        writeln!(out, "# [{:?}] {}", step.phase, step.package)?;
        writeln!(out, "{}", step.command)?;
        writeln!(out)?;
    }
    Ok(())
}

pub fn emit_json<W: Write>(steps: &[PlanStep], meta: &PackageMeta, out: &mut W) -> io::Result<()> {
    let doc = serde_json::json!({
        "package": {
            "name":     meta.identity.name,
            "version":  meta.identity.version,
            "category": meta.identity.category,
            "summary":  meta.identity.summary,
            "build_system": format!("{:?}", meta.build.system),
            "dependencies": meta.identity.depends.build,
        },
        "steps": steps,
    });
    writeln!(out, "{}", serde_json::to_string_pretty(&doc).unwrap_or_default())
}
