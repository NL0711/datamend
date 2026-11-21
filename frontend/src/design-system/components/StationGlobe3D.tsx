// The globe keeps its place in the design system, but its code stays in `src/globe/StationGlobe3D.tsx`: that file IS the original globe of
// commit ab3b0b3 (same scene, textures, lighting, controls and hover card), changed only so it draws honest data: pins come from the real
// station catalogue and stored checks (no default health score of 98, no "LIVE NODES" count, no invented consensus arcs).
export { StationGlobe3D } from '../../globe/StationGlobe3D';
export type { GlobeStation } from '../../globe/StationGlobe3D';
