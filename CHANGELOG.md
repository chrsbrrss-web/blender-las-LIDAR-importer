# Changelog

## [1.4.0] - 2026-06-11
### Added
- LiDAR Info panel in the N-panel (View3D sidebar > LiDAR tab) showing LAS version,
  point format, point count, scale, offset, min/max bounds, creation date, GPS time
  type, and return counts for any imported object
- Header metadata stored as custom properties on the Blender object

### Changed
- Pure-Python fallback reader now also extracts and returns header metadata
- `create_blender_object` writes metadata to object custom properties after creation

## [1.3.0] - 2026-06-11
### Added
- Pure-Python fallback LAS reader — standard .las files import with zero dependencies
- `--target` pip install into addon-local site-packages directory (fixes silent failure
  in Blender's sandboxed Python environment)
- `ensurepip` bootstrap before pip install
- sys.modules cache flush after install so laspy is importable without restart
- Install laspy button in the import dialog sidebar (not just Preferences)
- Multi-file import support
- Native Point Cloud object mode (Blender 3.3+)
- Random vs uniform decimation methods
- Intensity-to-vertex-weight option
- Classification color mapping (HSV rainbow by class code)

### Fixed
- Auto-install now actually works in Blender 3.x/4.x/5.x (previous approach wrote
  to read-only internal Python directories and failed silently)

## [1.2.0] - 2026-06-11
### Added
- Initial working release with laspy-based import
- Point decimation with max_points limit
- RGB, intensity, and classification color sources
- Center at origin option
- Addon Preferences panel with install button and status

## [1.0.0] - Initial
- Basic LAS import via laspy
