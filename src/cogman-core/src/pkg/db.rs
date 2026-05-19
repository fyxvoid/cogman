//! Package database — binary flat-file, no external deps.
//!
//! Path: /var/lib/cogman/packages.db  (or $COGMAN_DB)
//!
//! Layout:
//!   [DbHeader  32 B]
//!   [RawEntry  512 B each × N]
//!   [string heap, variable]

use std::fs::{self, OpenOptions};
use std::io::{self, Read, Write};
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

pub const DB_PATH:   &str = "/var/lib/cogman/packages.db";
pub const DB_MAGIC:  u32  = 0x434F474D; // "COGM"
pub const DB_VER:    u16  = 1;
pub const ENTRY_SZ:  usize = 512;

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct PackageRecord {
    pub name:         String,
    pub version:      String,
    pub category:     String,
    pub install_root: String,
    pub installed_at: u64,
    pub files:        Vec<String>,
}

impl PackageRecord {
    pub fn new(name: &str, version: &str, category: &str, root: &str) -> Self {
        PackageRecord {
            name:         name.into(),
            version:      version.into(),
            category:     category.into(),
            install_root: root.into(),
            installed_at: unix_now(),
            files:        Vec::new(),
        }
    }

    pub fn display_line(&self) -> String {
        format!("{}/{} {} (installed {})",
            self.category, self.name, self.version,
            format_ts(self.installed_at))
    }
}

// ── Binary layout (little-endian, packed) ────────────────────────────────

#[repr(C, packed)]
struct RawHeader {
    magic:       u32,
    version:     u16,
    _pad:        u16,
    count:       u32,
    heap_off:    u32,
    heap_len:    u32,
    _reserved:   [u8; 12],
}

const RENTRY_FIXED: usize = 4+2 + 4+2 + 4+2 + 4+2 + 8 + 4+4;

#[repr(C, packed)]
struct RawEntry {
    name_off:  u32, name_len:  u16,
    ver_off:   u32, ver_len:   u16,
    cat_off:   u32, cat_len:   u16,
    root_off:  u32, root_len:  u16,
    inst_at:   u64,
    files_off: u32, files_len: u32,
    _pad:      [u8; ENTRY_SZ - RENTRY_FIXED],
}

const _: () = assert!(std::mem::size_of::<RawHeader>() == 32);
const _: () = assert!(std::mem::size_of::<RawEntry>()  == ENTRY_SZ);

// ── PackageDb ─────────────────────────────────────────────────────────────

pub struct PackageDb {
    path:    PathBuf,
    records: Vec<PackageRecord>,
}

impl PackageDb {
    pub fn open<P: AsRef<Path>>(path: P) -> io::Result<Self> {
        let path = path.as_ref().to_path_buf();
        if let Some(p) = path.parent() { fs::create_dir_all(p)?; }
        let records = if path.exists() { Self::read_all(&path)? } else { Vec::new() };
        Ok(PackageDb { path, records })
    }

    pub fn system() -> io::Result<Self> {
        let path = std::env::var("COGMAN_DB")
            .map(PathBuf::from)
            .unwrap_or_else(|_| PathBuf::from(DB_PATH));
        Self::open(path)
    }

    pub fn get(&self, name: &str) -> Option<&PackageRecord> {
        self.records.iter().find(|r| r.name == name)
    }

    pub fn has(&self, name: &str) -> bool { self.get(name).is_some() }

    pub fn list(&self) -> &[PackageRecord] { &self.records }

    pub fn upsert(&mut self, rec: PackageRecord) -> io::Result<()> {
        if let Some(e) = self.records.iter_mut().find(|r| r.name == rec.name) {
            *e = rec;
        } else {
            self.records.push(rec);
        }
        self.flush()
    }

    pub fn remove(&mut self, name: &str) -> io::Result<Option<PackageRecord>> {
        if let Some(pos) = self.records.iter().position(|r| r.name == name) {
            let r = self.records.remove(pos);
            self.flush()?;
            Ok(Some(r))
        } else {
            Ok(None)
        }
    }

    // ── Serialization ─────────────────────────────────────────────────────

    fn flush(&self) -> io::Result<()> {
        let mut heap: Vec<u8> = Vec::new();
        let mut entries: Vec<RawEntry> = Vec::new();

        for r in &self.records {
            let (no, nl) = push(&mut heap, r.name.as_bytes());
            let (vo, vl) = push(&mut heap, r.version.as_bytes());
            let (co, cl) = push(&mut heap, r.category.as_bytes());
            let (ro, rl) = push(&mut heap, r.install_root.as_bytes());
            let blob: Vec<u8> = r.files.iter()
                .flat_map(|f| f.as_bytes().iter().chain(&[0u8]).copied())
                .collect();
            let (fo, fl) = push(&mut heap, &blob);

            entries.push(RawEntry {
                name_off: no as u32, name_len: nl as u16,
                ver_off:  vo as u32, ver_len:  vl as u16,
                cat_off:  co as u32, cat_len:  cl as u16,
                root_off: ro as u32, root_len: rl as u16,
                inst_at:  r.installed_at,
                files_off: fo as u32, files_len: fl as u32,
                _pad: [0; ENTRY_SZ - RENTRY_FIXED],
            });
        }

        let heap_offset = (32 + entries.len() * ENTRY_SZ) as u32;
        let header = RawHeader {
            magic: DB_MAGIC, version: DB_VER, _pad: 0,
            count: entries.len() as u32,
            heap_off: heap_offset, heap_len: heap.len() as u32,
            _reserved: [0; 12],
        };

        let mut f = OpenOptions::new()
            .write(true).create(true).truncate(true)
            .open(&self.path)?;
        f.write_all(as_bytes(&header))?;
        for e in &entries { f.write_all(as_bytes(e))?; }
        f.write_all(&heap)?;
        f.flush()
    }

    fn read_all(path: &Path) -> io::Result<Vec<PackageRecord>> {
        let mut f = fs::File::open(path)?;
        let mut buf = Vec::new();
        f.read_to_end(&mut buf)?;
        if buf.len() < 32 {
            return Err(io::Error::new(io::ErrorKind::InvalidData, "db too small"));
        }
        let hdr = unsafe { &*(buf.as_ptr() as *const RawHeader) };
        if hdr.magic != DB_MAGIC {
            return Err(io::Error::new(io::ErrorKind::InvalidData, "bad magic — not a cogman db"));
        }
        let count = hdr.count as usize;
        let heap_off = hdr.heap_off as usize;
        let heap = buf.get(heap_off..).unwrap_or(&[]);
        let mut out = Vec::with_capacity(count);
        for i in 0..count {
            let eoff = 32 + i * ENTRY_SZ;
            if eoff + ENTRY_SZ > buf.len() { break; }
            let e = unsafe { &*(buf[eoff..].as_ptr() as *const RawEntry) };
            let files_blob = heap.get(
                e.files_off as usize .. (e.files_off + e.files_len) as usize
            ).unwrap_or(&[]);
            out.push(PackageRecord {
                name:         read_str(heap, e.name_off as _, e.name_len as _),
                version:      read_str(heap, e.ver_off  as _, e.ver_len  as _),
                category:     read_str(heap, e.cat_off  as _, e.cat_len  as _),
                install_root: read_str(heap, e.root_off as _, e.root_len as _),
                installed_at: e.inst_at,
                files:        files_blob.split(|&b| b == 0)
                    .filter(|s| !s.is_empty())
                    .map(|s| String::from_utf8_lossy(s).into_owned())
                    .collect(),
            });
        }
        Ok(out)
    }
}

fn push(heap: &mut Vec<u8>, data: &[u8]) -> (usize, usize) {
    let off = heap.len();
    heap.extend_from_slice(data);
    (off, data.len())
}

fn read_str(heap: &[u8], off: usize, len: usize) -> String {
    heap.get(off..off+len)
        .map(|b| String::from_utf8_lossy(b).into_owned())
        .unwrap_or_default()
}

fn as_bytes<T: Sized>(v: &T) -> &[u8] {
    unsafe { std::slice::from_raw_parts(v as *const T as *const u8, std::mem::size_of::<T>()) }
}

fn unix_now() -> u64 {
    SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0)
}

fn format_ts(ts: u64) -> String {
    // Simple human-readable relative time
    let now = unix_now();
    let secs = now.saturating_sub(ts);
    if secs < 60 { format!("{}s ago", secs) }
    else if secs < 3600 { format!("{}m ago", secs / 60) }
    else if secs < 86400 { format!("{}h ago", secs / 3600) }
    else { format!("{}d ago", secs / 86400) }
}
