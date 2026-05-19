//! Package manifest schema — TOML v1.
//!
//! Every package is described by a single `<name>.toml` file:
//!
//! ```toml
//! [identity]
//! name     = "hello"
//! version  = "1.0.0"
//! category = "base"
//! summary  = "GNU Hello"
//!
//! [identity.source]
//! kind = "tarball"
//! file = "hello-2.12.tar.gz"
//!
//! [identity.depends]
//! build   = ["toolchain/gcc"]
//! runtime = []
//!
//! [build]
//! system = "autotools"
//! steps  = ["cd build && ../source/configure --prefix=/usr", "make -j$(nproc)"]
//!
//! [installer]
//! steps = ["make install DESTDIR=$PKGROOT"]
//!
//! [policy.filesystem]
//! read  = ["/"]
//! write = ["/usr"]
//!
//! [policy.network]
//! outbound = false
//! ```

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct PackageMeta {
    pub identity:  Identity,
    pub build:     Builder,
    pub installer: Installer,
    #[serde(default)]
    pub policy:    Policy,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct Identity {
    pub name:     String,
    pub version:  String,
    pub category: String,
    #[serde(default)]
    pub summary:  String,
    pub source:   Source,
    #[serde(default)]
    pub depends:  Depends,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct Source {
    pub kind: SourceKind,
    #[serde(default)]
    pub file: Option<String>,
    #[serde(default)]
    pub url:  Option<String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Deserialize, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum SourceKind { Tarball, Git, Local, None }

#[derive(Debug, Clone, Default, Deserialize, Serialize)]
pub struct Depends {
    #[serde(default)]
    pub build:   Vec<String>,
    #[serde(default)]
    pub runtime: Vec<String>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct Builder {
    pub system: BuildSystem,
    pub steps:  Vec<String>,
    #[serde(default)]
    pub configure: Configure,
}

#[derive(Debug, Clone, Copy, PartialEq, Deserialize, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum BuildSystem {
    Autotools, Cmake, Meson, Make, Go, Rust, Python, Custom,
}

#[derive(Debug, Clone, Default, Deserialize, Serialize)]
pub struct Configure {
    #[serde(default)]
    pub flags: Vec<String>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct Installer {
    pub steps: Vec<String>,
    #[serde(default)]
    pub verify: Option<Verify>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct Verify {
    #[serde(default)]
    pub expected_files: Vec<String>,
    pub checksum: Option<String>,
}

#[derive(Debug, Clone, Default, Deserialize, Serialize)]
pub struct Policy {
    #[serde(default)]
    pub filesystem:   Filesystem,
    #[serde(default)]
    pub network:      Network,
    #[serde(default)]
    pub capabilities: Vec<String>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct Filesystem {
    #[serde(default = "default_read")]
    pub read:  Vec<String>,
    #[serde(default = "default_write")]
    pub write: Vec<String>,
}

impl Default for Filesystem {
    fn default() -> Self { Self { read: default_read(), write: default_write() } }
}

fn default_read()  -> Vec<String> { vec!["/".into()] }
fn default_write() -> Vec<String> { vec!["/usr".into()] }

#[derive(Debug, Clone, Default, Deserialize, Serialize)]
pub struct Network {
    #[serde(default)]
    pub outbound: bool,
}

impl PackageMeta {
    pub fn full_name(&self) -> String {
        format!("{}/{}", self.identity.category, self.identity.name)
    }

    pub fn load(path: &std::path::Path) -> Result<Self, String> {
        let src = std::fs::read_to_string(path)
            .map_err(|e| format!("cannot read {}: {e}", path.display()))?;
        toml::from_str(&src)
            .map_err(|e| format!("parse error in {}: {e}", path.display()))
    }
}
