//! Dependency graph resolver using petgraph.
//!
//! Builds a directed graph where an edge A→B means "A must be built before B"
//! (i.e., B depends on A). Topological sort gives the build order.

use petgraph::algo::toposort;
use petgraph::graph::{DiGraph, NodeIndex};
use std::collections::{HashMap, HashSet};
use std::path::{Path, PathBuf};

use crate::metadata::{load, PackageMeta};

// ── Dependency graph ──────────────────────────────────────────────────────

pub struct DepGraph {
    pub graph: DiGraph<String, ()>,
    pub nodes: HashMap<String, NodeIndex>,
}

impl DepGraph {
    pub fn new() -> Self {
        DepGraph { graph: DiGraph::new(), nodes: HashMap::new() }
    }

    fn node(&mut self, name: &str) -> NodeIndex {
        *self.nodes.entry(name.into()).or_insert_with(|| self.graph.add_node(name.into()))
    }

    pub fn ensure(&mut self, name: &str) { self.node(name); }

    pub fn add_edge(&mut self, dep: &str, pkg: &str) {
        let d = self.node(dep);
        let p = self.node(pkg);
        self.graph.add_edge(d, p, ());
    }

    /// Topological build order (dependency-first).
    pub fn build_order(&self) -> Result<Vec<String>, String> {
        toposort(&self.graph, None)
            .map(|order| order.iter().map(|&i| self.graph[i].clone()).collect())
            .map_err(|cycle| {
                format!("circular dependency detected at node {:?}", self.graph[cycle.node_id()])
            })
    }
}

// ── Recursive loader ──────────────────────────────────────────────────────

pub struct Loader {
    packages_root: PathBuf,
    pub graph:     DepGraph,
    pub metas:     HashMap<String, PackageMeta>,
    visited:       HashSet<String>,
}

impl Loader {
    pub fn new(packages_root: PathBuf) -> Self {
        Loader {
            packages_root,
            graph:   DepGraph::new(),
            metas:   HashMap::new(),
            visited: HashSet::new(),
        }
    }

    /// Inject root package and recursively resolve its dependencies.
    pub fn inject_root(&mut self, meta: &PackageMeta) -> Result<(), String> {
        let name = meta.full_name();
        if self.visited.contains(&name) { return Ok(()); }
        self.graph.ensure(&name);
        self.metas.insert(name.clone(), meta.clone());
        self.visited.insert(name.clone());
        let deps = meta.identity.depends.build.clone();
        for dep in &deps {
            self.graph.add_edge(dep, &name);
            self.load_dep(dep)?;
        }
        Ok(())
    }

    fn load_dep(&mut self, pkg_id: &str) -> Result<(), String> {
        if self.visited.contains(pkg_id) { return Ok(()); }
        self.visited.insert(pkg_id.into());
        self.graph.ensure(pkg_id);

        let parts: Vec<&str> = pkg_id.splitn(2, '/').collect();
        if parts.len() != 2 {
            return Err(format!("invalid pkg id '{pkg_id}': must be category/name"));
        }
        let (cat, name) = (parts[0], parts[1]);
        let toml_path = self.packages_root
            .join("packages").join(cat).join(name)
            .join(format!("{name}.toml"));

        if !toml_path.exists() {
            // Non-fatal for external deps (toolchain, etc.) — just note it
            eprintln!("[planner] warn: dep '{}' not found at {}", pkg_id, toml_path.display());
            return Ok(());
        }

        let meta = load(&toml_path)?;
        let deps = meta.identity.depends.build.clone();
        self.metas.insert(pkg_id.into(), meta);

        for dep in &deps {
            self.graph.add_edge(dep, pkg_id);
            self.load_dep(dep)?;
        }
        Ok(())
    }
}
