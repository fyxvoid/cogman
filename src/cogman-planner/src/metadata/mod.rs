pub mod schema;
pub use schema::{PackageMeta, BuildSystem};

use std::path::Path;

pub fn load(path: &Path) -> Result<PackageMeta, String> {
    PackageMeta::load(path)
}
