//! Image processing — diff, hash, template match, change detection.

use pyo3::prelude::*;

// ── Diff ──

#[pyclass]
#[derive(Clone)]
pub struct DiffRegion {
    #[pyo3(get)]
    pub x: u32,
    #[pyo3(get)]
    pub y: u32,
    #[pyo3(get)]
    pub w: u32,
    #[pyo3(get)]
    pub h: u32,
    #[pyo3(get)]
    pub changed_pixels: u64,
    #[pyo3(get)]
    pub total_pixels: u64,
    #[pyo3(get)]
    pub percent: f64,
}

#[pymethods]
impl DiffRegion {
    #[new]
    fn new() -> Self {
        DiffRegion {
            x: 0,
            y: 0,
            w: 0,
            h: 0,
            changed_pixels: 0,
            total_pixels: 0,
            percent: 0.0,
        }
    }
}

#[pyclass]
#[derive(Clone)]
pub struct DiffResult {
    #[pyo3(get)]
    pub changed: bool,
    #[pyo3(get)]
    pub percent: f64,
    #[pyo3(get)]
    pub changed_pixels: u64,
    #[pyo3(get)]
    pub total_pixels: u64,
}

#[pymethods]
impl DiffResult {
    #[new]
    fn new() -> Self {
        DiffResult {
            changed: false,
            percent: 0.0,
            changed_pixels: 0,
            total_pixels: 0,
        }
    }
}

/// Pixel-by-pixel diff between two RGBA buffers. Returns diff result.
#[pyfunction]
pub fn image_diff(
    before_rgba: Vec<u8>,
    after_rgba: Vec<u8>,
    width: u32,
    height: u32,
    threshold: Option<u8>,
) -> PyResult<DiffResult> {
    let thresh = threshold.unwrap_or(10);
    let expected = (width * height * 4) as usize;
    if before_rgba.len() != expected || after_rgba.len() != expected {
        return Err(PyErr::new::<pyo3::exceptions::PyValueError, _>(
            "RGBA buffer size mismatch",
        ));
    }

    let mut changed = 0u64;
    for i in (0..before_rgba.len()).step_by(4) {
        let dr = (before_rgba[i] as i16 - after_rgba[i] as i16).unsigned_abs() as u8;
        let dg = (before_rgba[i + 1] as i16 - after_rgba[i + 1] as i16).unsigned_abs() as u8;
        let db = (before_rgba[i + 2] as i16 - after_rgba[i + 2] as i16).unsigned_abs() as u8;
        if dr > thresh || dg > thresh || db > thresh {
            changed += 1;
        }
    }

    let total = (width * height) as u64;
    Ok(DiffResult {
        changed: changed > 0,
        percent: if total > 0 {
            changed as f64 / total as f64 * 100.0
        } else {
            0.0
        },
        changed_pixels: changed,
        total_pixels: total,
    })
}

// ── Perceptual Hash ──

/// dHash (Difference Hash) — robust to slight changes.
/// Returns a 64-bit hash as a Python int.
#[pyfunction]
pub fn dhash(rgba: Vec<u8>, width: u32, height: u32) -> PyResult<u64> {
    if rgba.len() < (width * height * 4) as usize {
        return Err(PyErr::new::<pyo3::exceptions::PyValueError, _>(
            "Buffer too small",
        ));
    }

    // Resize to 9x8 grayscale, then compute diff hash
    let mut gray = vec![0u8; (9 * 8) as usize];
    for y in 0..8u32 {
        for x in 0..9u32 {
            let sx = (x * width) / 9;
            let sy = (y * height) / 8;
            let idx = ((sy * width + sx) * 4) as usize;
            let r = rgba[idx] as u32;
            let g = rgba[idx + 1] as u32;
            let b = rgba[idx + 2] as u32;
            gray[(y * 9 + x) as usize] = ((r * 30 + g * 59 + b * 11) / 100) as u8;
        }
    }

    let mut hash: u64 = 0;
    for y in 0..8u32 {
        for x in 0..8u32 {
            let left = gray[(y * 9 + x) as usize];
            let right = gray[(y * 9 + x + 1) as usize];
            if left < right {
                hash |= 1 << (y * 8 + x);
            }
        }
    }
    Ok(hash)
}

/// Hamming distance between two hashes. ≤10 = same image, ≤20 = similar.
#[pyfunction]
pub fn hamming_distance(h1: u64, h2: u64) -> u32 {
    (h1 ^ h2).count_ones()
}

// ── Template Matching ──

#[pyclass]
#[derive(Clone)]
pub struct MatchResult {
    #[pyo3(get)]
    pub x: u32,
    #[pyo3(get)]
    pub y: u32,
    #[pyo3(get)]
    pub confidence: f64,
}

#[pymethods]
impl MatchResult {
    #[new]
    fn new() -> Self {
        MatchResult {
            x: 0,
            y: 0,
            confidence: 0.0,
        }
    }
}

/// Naive template match — slide template across image, find best NCC match.
/// For production use, consider OpenCV or custom SIMD — this is a reference impl.
#[pyfunction]
pub fn template_match(
    image_rgba: Vec<u8>,
    img_w: u32,
    img_h: u32,
    template_rgba: Vec<u8>,
    tmpl_w: u32,
    tmpl_h: u32,
    min_confidence: Option<f64>,
) -> PyResult<Option<MatchResult>> {
    let threshold = min_confidence.unwrap_or(0.7);

    if img_w < tmpl_w || img_h < tmpl_h {
        return Ok(None);
    }

    let mut best_x = 0u32;
    let mut best_y = 0u32;
    let mut best_score = -1.0f64;

    // Pre-compute template mean
    let tmpl_pixels = (tmpl_w * tmpl_h) as f64;
    let mut tmpl_mean = 0.0f64;
    for ty in 0..tmpl_h {
        for tx in 0..tmpl_w {
            let idx = ((ty * tmpl_w + tx) * 4) as usize;
            tmpl_mean += rgba_luma(&template_rgba, idx) as f64;
        }
    }
    tmpl_mean /= tmpl_pixels;

    // Sliding window (step = 4 for speed)
    let step = 4u32;
    for y in (0..=img_h - tmpl_h).step_by(step as usize) {
        for x in (0..=img_w - tmpl_w).step_by(step as usize) {
            let mut num = 0.0f64;
            let mut den_img = 0.0f64;
            let mut den_tmpl = 0.0f64;

            let mut img_sum = 0.0f64;
            for ty in 0..tmpl_h {
                for tx in 0..tmpl_w {
                    let i_idx = (((y + ty) * img_w + x + tx) * 4) as usize;
                    img_sum += rgba_luma(&image_rgba, i_idx) as f64;
                }
            }
            let img_mean = img_sum / tmpl_pixels;

            for ty in 0..tmpl_h {
                for tx in 0..tmpl_w {
                    let i_idx = (((y + ty) * img_w + x + tx) * 4) as usize;
                    let t_idx = ((ty * tmpl_w + tx) * 4) as usize;
                    let iv = rgba_luma(&image_rgba, i_idx) as f64;
                    let tv = rgba_luma(&template_rgba, t_idx) as f64;
                    let di = iv - img_mean;
                    let dt = tv - tmpl_mean;
                    num += di * dt;
                    den_img += di * di;
                    den_tmpl += dt * dt;
                }
            }

            let den = (den_img * den_tmpl).sqrt();
            let score = if den > 0.0 { num / den } else { 0.0 };

            if score > best_score {
                best_score = score;
                best_x = x;
                best_y = y;
            }

            // Early exit on perfect match
            if score > 0.999 {
                return Ok(Some(MatchResult {
                    x: best_x,
                    y: best_y,
                    confidence: best_score,
                }));
            }
        }
    }

    if best_score >= threshold {
        Ok(Some(MatchResult {
            x: best_x,
            y: best_y,
            confidence: best_score,
        }))
    } else {
        Ok(None)
    }
}

fn rgba_luma(rgba: &[u8], idx: usize) -> u8 {
    let r = rgba[idx] as u32;
    let g = rgba[idx + 1] as u32;
    let b = rgba[idx + 2] as u32;
    ((r * 30 + g * 59 + b * 11) / 100) as u8
}

// ── Change Detection ──

/// Quick check: are two images significantly different?
/// Uses both pixel percentage (>1%) and dHash for reliability.
#[pyfunction]
pub fn has_changed(
    before_rgba: Vec<u8>,
    after_rgba: Vec<u8>,
    width: u32,
    height: u32,
    pixel_threshold: Option<u8>,
) -> PyResult<bool> {
    let diff = image_diff(
        before_rgba.clone(),
        after_rgba.clone(),
        width,
        height,
        pixel_threshold,
    )?;
    if diff.percent > 1.0 && diff.changed_pixels > 100 {
        return Ok(true);
    }
    // Also check dHash
    let h1 = dhash(before_rgba, width, height)?;
    let h2 = dhash(after_rgba, width, height)?;
    Ok(hamming_distance(h1, h2) > 2)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn black_rgba(w: u32, h: u32) -> Vec<u8> {
        vec![0u8; (w * h * 4) as usize]
    }
    fn white_rgba(w: u32, h: u32) -> Vec<u8> {
        vec![255u8; (w * h * 4) as usize]
    }
    fn small_img() -> Vec<u8> {
        let mut v = vec![0u8; 32 * 32 * 4];
        for i in (0..v.len()).step_by(4) {
            v[i] = 128;
            v[i + 1] = 100;
            v[i + 2] = 80;
            v[i + 3] = 255;
        }
        v
    }

    #[test]
    fn test_image_diff_same() {
        let img = black_rgba(16, 16);
        let r = image_diff(img.clone(), img, 16, 16, Some(10)).expect("diff");
        assert!(!r.changed);
        assert_eq!(r.percent, 0.0);
    }

    #[test]
    fn test_image_diff_changed() {
        let r = image_diff(black_rgba(16, 16), white_rgba(16, 16), 16, 16, Some(10)).expect("diff");
        assert!(r.changed);
        assert!(r.percent > 90.0);
    }

    #[test]
    fn test_dhash_same() {
        let img = small_img();
        let h1 = dhash(img.clone(), 32, 32).expect("dhash1");
        let h2 = dhash(img, 32, 32).expect("dhash2");
        assert_eq!(hamming_distance(h1, h2), 0);
    }

    #[test]
    fn test_dhash_different() {
        // Gradient left-to-right vs uniform — must differ
        let mut grad = vec![0u8; 32 * 32 * 4];
        let mut flat = vec![0u8; 32 * 32 * 4];
        for y in 0..32u32 {
            for x in 0..32u32 {
                let i = ((y * 32 + x) * 4) as usize;
                let v = (x * 8) as u8;
                grad[i] = v;
                grad[i + 3] = 255;
                flat[i] = 128;
                flat[i + 3] = 255;
            }
        }
        let h1 = dhash(grad, 32, 32).unwrap();
        let h2 = dhash(flat, 32, 32).unwrap();
        assert!(hamming_distance(h1, h2) > 0, "Gradient vs flat must differ");
    }

    #[test]
    fn test_hamming_zero() {
        assert_eq!(hamming_distance(0, 0), 0);
    }
    #[test]
    fn test_hamming_identical() {
        assert_eq!(hamming_distance(0xFFFFFFFFFFFFFFFF, 0xFFFFFFFFFFFFFFFF), 0);
    }
    #[test]
    fn test_hamming_diff() {
        assert!(hamming_distance(0xFFFFFFFFFFFFFFFF, 0) > 0);
    }

    #[test]
    fn test_has_changed_same() {
        let img = small_img();
        assert!(!has_changed(img.clone(), img, 32, 32, Some(10)).expect("has_changed"));
    }

    #[test]
    fn test_template_match_none_small() {
        let r = template_match(black_rgba(10, 10), 10, 10, black_rgba(20, 20), 20, 20, None)
            .expect("match");
        assert!(r.is_none(), "Template larger than image should return None");
    }
}
