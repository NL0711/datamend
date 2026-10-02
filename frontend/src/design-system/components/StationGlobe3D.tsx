import React, { useEffect, useRef, useState, useCallback } from 'react';
import * as THREE from 'three';
import { Station } from '../../types';
import { Globe, ZoomIn, ZoomOut, Compass, Activity, MapPin, RotateCw, CheckCircle2, Radio } from 'lucide-react';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';

interface StationGlobe3DProps {
  stations: Station[];
  selectedStationId?: string;
  onSelectStation?: (stationId: string) => void;
  className?: string;
}

export const StationGlobe3D: React.FC<StationGlobe3DProps> = ({
  stations,
  selectedStationId,
  onSelectStation,
  className = '',
}) => {
  const mountRef = useRef<HTMLDivElement | null>(null);
  
  const [hoveredStation, setHoveredStation] = useState<Station | null>(null);
  const [hoverPos, setHoverPos] = useState<{ x: number; y: number }>({ x: 0, y: 0 });

  const [showArcs, setShowArcs] = useState<boolean>(true);
  const [isAutoRotating, setIsAutoRotating] = useState<boolean>(true);
  const [modelStatus, setModelStatus] = useState<'loading' | 'loaded' | 'fallback'>('loading');

  // Mutable refs to prevent scene re-creation
  const isAutoRotatingRef = useRef<boolean>(isAutoRotating);
  isAutoRotatingRef.current = isAutoRotating;

  const onSelectStationRef = useRef(onSelectStation);
  onSelectStationRef.current = onSelectStation;

  const stationsRef = useRef<Station[]>(stations);
  stationsRef.current = stations;

  const selectedStationIdRef = useRef<string | undefined>(selectedStationId);
  selectedStationIdRef.current = selectedStationId;

  const showArcsRef = useRef<boolean>(showArcs);
  showArcsRef.current = showArcs;

  // Three.js Core Object Refs
  const sceneRef = useRef<THREE.Scene | null>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const globeGroupRef = useRef<THREE.Group | null>(null);
  const stationPinsGroupRef = useRef<THREE.Group | null>(null);
  const consensusArcsGroupRef = useRef<THREE.Group | null>(null);
  const raycasterRef = useRef<THREE.Raycaster>(new THREE.Raycaster());
  const mouseRef = useRef<THREE.Vector2>(new THREE.Vector2());
  
  const isDraggingRef = useRef<boolean>(false);
  const previousMousePositionRef = useRef<{ x: number; y: number }>({ x: 0, y: 0 });
  const targetRotationRef = useRef<{ x: number; y: number }>({ x: 0.32, y: 1.4 });
  const currentRotationRef = useRef<{ x: number; y: number }>({ x: 0.32, y: 1.4 });

  /**
   * Calibrated WGS84 Geodetic to 3D Cartesian Conversion:
   * Aligns with the 135° azimuthal baseline of the earth-globe-atlas mesh geometry.
   * Latitude: [-90, +90] -> Y axis [-1, +1]
   * Longitude: [-180, +180] -> XZ Plane with 135° prime-meridian offset
   */
  const latLonToVector3 = useCallback((lat: number, lon: number, radius: number): THREE.Vector3 => {
    const phi = lat * (Math.PI / 180);
    const theta = (135 - lon) * (Math.PI / 180);
    
    const y = radius * Math.sin(phi);
    const rHoriz = radius * Math.cos(phi);
    const x = rHoriz * Math.cos(theta);
    const z = rHoriz * Math.sin(theta);
    return new THREE.Vector3(x, y, z);
  }, []);

  // Update Dynamic Pins and Spatial Consensus Arcs
  const updatePinsAndArcs = useCallback(() => {
    if (!stationPinsGroupRef.current || !consensusArcsGroupRef.current) return;

    const pinsGroup = stationPinsGroupRef.current;
    const arcsGroup = consensusArcsGroupRef.current;

    // Clean old children
    while (pinsGroup.children.length > 0) {
      const child = pinsGroup.children[0] as THREE.Mesh;
      if (child.geometry) child.geometry.dispose();
      pinsGroup.remove(child);
    }
    while (arcsGroup.children.length > 0) {
      const child = arcsGroup.children[0] as THREE.Line;
      if (child.geometry) child.geometry.dispose();
      arcsGroup.remove(child);
    }

    const R = 1.0; 
    const currentStations = stationsRef.current;
    const currentSelectedId = selectedStationIdRef.current;
    const stationCoords: { [id: string]: THREE.Vector3 } = {};

    currentStations.forEach((st) => {
      const lat = st.latitude ?? 28.6139;
      const lon = st.longitude ?? 77.2090;
      const pos = latLonToVector3(lat, lon, R);
      
      stationCoords[st.station_id] = pos;

      const isSelected = st.station_id === currentSelectedId;
      const health = st.health_score ?? 98;
      const isCritical = health < 50;
      const isWarning = health >= 50 && health < 75;

      const pinColor = isSelected ? 0x38bdf8 : isCritical ? 0xef4444 : isWarning ? 0xf59e0b : 0x10b981;

      // 1. Sleek Glowing Pin Head
      const pinHeadGeo = new THREE.SphereGeometry(isSelected ? 0.026 : 0.018, 16, 16);
      const pinHeadMat = new THREE.MeshStandardMaterial({ 
        color: pinColor,
        emissive: pinColor,
        emissiveIntensity: isSelected ? 1.0 : 0.7,
        roughness: 0.2,
        metalness: 0.8,
      });
      const pinHeadMesh = new THREE.Mesh(pinHeadGeo, pinHeadMat);
      pinHeadMesh.position.copy(pos.clone().multiplyScalar(1.045));
      pinHeadMesh.userData = { station: st };

      // 2. Slender Vertical Elevation Stem
      const stemGeo = new THREE.CylinderGeometry(0.002, 0.002, 0.04, 8);
      const stemMat = new THREE.MeshBasicMaterial({ color: pinColor, transparent: true, opacity: 0.85 });
      const stemMesh = new THREE.Mesh(stemGeo, stemMat);
      stemMesh.position.copy(pos.clone().multiplyScalar(1.02));
      stemMesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), pos.clone().normalize());
      stemMesh.userData = { station: st };

      // 3. Ground Contact Geographic Target Ring
      const groundRingGeo = new THREE.RingGeometry(0.006, 0.016, 16);
      const groundRingMat = new THREE.MeshBasicMaterial({
        color: pinColor,
        side: THREE.DoubleSide,
        transparent: true,
        opacity: isSelected ? 0.95 : 0.7,
      });
      const groundRing = new THREE.Mesh(groundRingGeo, groundRingMat);
      groundRing.position.copy(pos.clone().multiplyScalar(1.002));
      groundRing.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), pos.clone().normalize());
      groundRing.userData = { station: st };

      pinsGroup.add(pinHeadMesh);
      pinsGroup.add(stemMesh);
      pinsGroup.add(groundRing);

      // 4. Radar Halo Pulse Disk for Selected or Anomaly Stations
      if (isSelected || isCritical) {
        const pulseGeo = new THREE.RingGeometry(0.018, 0.034, 16);
        const pulseMat = new THREE.MeshBasicMaterial({
          color: pinColor,
          side: THREE.DoubleSide,
          transparent: true,
          opacity: isSelected ? 0.85 : 0.6,
        });
        const pulseMesh = new THREE.Mesh(pulseGeo, pulseMat);
        pulseMesh.position.copy(pos.clone().multiplyScalar(1.004));
        pulseMesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), pos.clone().normalize());
        pinsGroup.add(pulseMesh);
      }
    });

    // 5. Great-Circle Tier 3.5 Consensus Arcs
    if (showArcsRef.current) {
      const stationList = Object.entries(stationCoords);
      for (let i = 0; i < stationList.length; i++) {
        for (let j = i + 1; j < stationList.length; j++) {
          const [, p1] = stationList[i];
          const [, p2] = stationList[j];
          const dist = p1.distanceTo(p2);

          // Connect stations within spatial consensus neighbor correlation window
          if (dist > 0.05 && dist < 0.75) {
            const mid = p1.clone().add(p2).multiplyScalar(0.5);
            mid.normalize().multiplyScalar(R * (1.06 + dist * 0.12));

            const curve = new THREE.QuadraticBezierCurve3(p1, mid, p2);
            const points = curve.getPoints(24);
            const arcGeo = new THREE.BufferGeometry().setFromPoints(points);
            const arcMat = new THREE.LineBasicMaterial({
              color: 0x38bdf8,
              transparent: true,
              opacity: 0.4,
            });
            const arcLine = new THREE.Line(arcGeo, arcMat);
            arcsGroup.add(arcLine);
          }
        }
      }
    }
  }, [latLonToVector3]);

  // Main Three.js Scene Setup (Runs strictly ONCE on mount)
  useEffect(() => {
    const container = mountRef.current;
    if (!container) return;

    let isDestroyed = false;

    const width = container.clientWidth || 640;
    const height = container.clientHeight || 460;

    // 1. Scene
    const scene = new THREE.Scene();
    sceneRef.current = scene;

    // 2. Camera
    const camera = new THREE.PerspectiveCamera(42, width / height, 0.1, 1000);
    camera.position.set(0, 0, 2.9);
    cameraRef.current = camera;

    // 3. High-Precision Renderer
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'high-performance' });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setClearColor(0x080e1b, 1.0);
    rendererRef.current = renderer;

    while (container.firstChild) {
      container.removeChild(container.firstChild);
    }
    container.appendChild(renderer.domElement);

    // 4. Lighting System
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.85);
    scene.add(ambientLight);

    const dirLight1 = new THREE.DirectionalLight(0xffffff, 1.4);
    dirLight1.position.set(5, 3, 5);
    scene.add(dirLight1);

    const dirLight2 = new THREE.DirectionalLight(0x38bdf8, 0.7);
    dirLight2.position.set(-5, -2, -5);
    scene.add(dirLight2);

    // 5. Starfield Particles
    const starGeo = new THREE.BufferGeometry();
    const starCount = 350;
    const starPositions = new Float32Array(starCount * 3);
    for (let i = 0; i < starCount * 3; i += 3) {
      starPositions[i] = (Math.random() - 0.5) * 20;
      starPositions[i + 1] = (Math.random() - 0.5) * 20;
      starPositions[i + 2] = (Math.random() - 0.5) * 20 - 4;
    }
    starGeo.setAttribute('position', new THREE.BufferAttribute(starPositions, 3));
    const starMat = new THREE.PointsMaterial({ color: 0x94a3b8, size: 0.04, transparent: true, opacity: 0.6 });
    const stars = new THREE.Points(starGeo, starMat);
    scene.add(stars);

    // 6. Globe Group
    const globeGroup = new THREE.Group();
    globeGroupRef.current = globeGroup;
    scene.add(globeGroup);

    // Atmospheric Outer Rim Glow
    const atmosphereGeo = new THREE.SphereGeometry(1.025, 32, 32);
    const atmosphereMat = new THREE.MeshBasicMaterial({
      color: 0x38bdf8,
      transparent: true,
      opacity: 0.12,
      side: THREE.BackSide,
    });
    const atmosphereMesh = new THREE.Mesh(atmosphereGeo, atmosphereMat);
    globeGroup.add(atmosphereMesh);

    // Fallback Textured Baseline Sphere
    const textureLoader = new THREE.TextureLoader();
    const fallbackGeo = new THREE.SphereGeometry(1.0, 48, 48);
    const fallbackMat = new THREE.MeshStandardMaterial({
      color: 0x1e3a5f,
      roughness: 0.8,
      metalness: 0.1,
    });
    
    textureLoader.load(
      '/assets/earth/earth_map.jpg',
      (tex) => {
        fallbackMat.map = tex;
        fallbackMat.color.setHex(0xffffff);
        fallbackMat.needsUpdate = true;
      },
      undefined,
      () => {
        fallbackMat.color.setHex(0x162b4d);
      }
    );

    const fallbackMesh = new THREE.Mesh(fallbackGeo, fallbackMat);
    globeGroup.add(fallbackMesh);

    // Dynamic Station Pins Group
    const pinsGroup = new THREE.Group();
    stationPinsGroupRef.current = pinsGroup;
    globeGroup.add(pinsGroup);

    // Dynamic Spatial Consensus Arcs Group
    const arcsGroup = new THREE.Group();
    consensusArcsGroupRef.current = arcsGroup;
    globeGroup.add(arcsGroup);

    // Initial Data Sync
    updatePinsAndArcs();

    // 7. Load User's Actual 3D Mesh (earth-globe-atlas / earth-globe.glb)
    const gltfLoader = new GLTFLoader();
    gltfLoader.load(
      '/assets/earth/earth-globe.glb',
      (gltf: any) => {
        if (isDestroyed) return;
        const loadedModel = gltf.scene;

        // Auto-scale calibration to ensure R=1.0 for the model
        const box = new THREE.Box3().setFromObject(loadedModel);
        const size = new THREE.Vector3();
        box.getSize(size);
        const maxDim = Math.max(size.x, size.y, size.z);
        if (maxDim > 0) {
          const scaleFactor = 2.0 / maxDim; // 2.0 diameter -> R = 1.0
          loadedModel.scale.set(scaleFactor, scaleFactor, scaleFactor);
          
          // Re-center model at origin
          const newBox = new THREE.Box3().setFromObject(loadedModel);
          const center = new THREE.Vector3();
          newBox.getCenter(center);
          loadedModel.position.sub(center);
        }

        // Configure PBR materials for crisp contrast
        loadedModel.traverse((child: any) => {
          if (child.isMesh && child.material) {
            child.material.side = THREE.DoubleSide;
            child.material.roughness = 0.75;
            child.material.metalness = 0.1;
            child.material.needsUpdate = true;
          }
        });

        // Hide fallback baseline and display loaded physical mesh
        fallbackMesh.visible = false;
        globeGroup.add(loadedModel);
        setModelStatus('loaded');
      },
      undefined,
      (err: any) => {
        console.warn('GLB load note (using baseline):', err);
        if (!isDestroyed) {
          setModelStatus('fallback');
        }
      }
    );

    // 8. User Interaction Listeners
    const handleMouseDown = (e: MouseEvent) => {
      isDraggingRef.current = true;
      previousMousePositionRef.current = { x: e.clientX, y: e.clientY };
    };

    const handleMouseMove = (e: MouseEvent) => {
      const rect = container.getBoundingClientRect();
      const mouseX = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      const mouseY = -((e.clientY - rect.top) / rect.height) * 2 + 1;
      mouseRef.current.set(mouseX, mouseY);

      setHoverPos({
        x: e.clientX - rect.left,
        y: e.clientY - rect.top,
      });

      if (cameraRef.current && stationPinsGroupRef.current) {
        raycasterRef.current.setFromCamera(mouseRef.current, cameraRef.current);
        const intersects = raycasterRef.current.intersectObjects(stationPinsGroupRef.current.children, true);
        if (intersects.length > 0) {
          const st = intersects[0].object.userData.station as Station;
          if (st) {
            setHoveredStation(st);
            container.style.cursor = 'pointer';
          }
        } else {
          setHoveredStation(null);
          container.style.cursor = isDraggingRef.current ? 'grabbing' : 'grab';
        }
      }

      if (!isDraggingRef.current) return;

      const deltaX = e.clientX - previousMousePositionRef.current.x;
      const deltaY = e.clientY - previousMousePositionRef.current.y;

      targetRotationRef.current.y += deltaX * 0.006;
      targetRotationRef.current.x = Math.max(-0.85, Math.min(0.85, targetRotationRef.current.x + deltaY * 0.006));

      previousMousePositionRef.current = { x: e.clientX, y: e.clientY };
    };

    const handleMouseUp = (_e: MouseEvent) => {
      isDraggingRef.current = false;
      container.style.cursor = 'grab';

      if (cameraRef.current && stationPinsGroupRef.current) {
        raycasterRef.current.setFromCamera(mouseRef.current, cameraRef.current);
        const intersects = raycasterRef.current.intersectObjects(stationPinsGroupRef.current.children, true);
        if (intersects.length > 0) {
          const st = intersects[0].object.userData.station as Station;
          if (st && onSelectStationRef.current) {
            onSelectStationRef.current(st.station_id);
          }
        }
      }
    };

    const handleWheel = (e: WheelEvent) => {
      e.preventDefault();
      if (!cameraRef.current) return;
      const newZ = Math.max(1.7, Math.min(4.8, cameraRef.current.position.z + e.deltaY * 0.002));
      cameraRef.current.position.setZ(newZ);
    };

    container.addEventListener('mousedown', handleMouseDown);
    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
    container.addEventListener('wheel', handleWheel, { passive: false });

    // 9. Damped Render Loop
    let animationFrameId: number;
    let lastTime = performance.now();

    const animate = (time: number) => {
      const delta = (time - lastTime) / 1000;
      lastTime = time;

      if (globeGroupRef.current) {
        if (isAutoRotatingRef.current && !isDraggingRef.current) {
          targetRotationRef.current.y += delta * 0.08;
        }

        currentRotationRef.current.y += (targetRotationRef.current.y - currentRotationRef.current.y) * 0.08;
        currentRotationRef.current.x += (targetRotationRef.current.x - currentRotationRef.current.x) * 0.08;

        globeGroupRef.current.rotation.y = currentRotationRef.current.y;
        globeGroupRef.current.rotation.x = currentRotationRef.current.x;
      }

      renderer.render(scene, camera);
      animationFrameId = requestAnimationFrame(animate);
    };
    animationFrameId = requestAnimationFrame(animate);

    // 10. Resize Observer
    const handleResize = () => {
      if (!container || !rendererRef.current || !cameraRef.current) return;
      const w = container.clientWidth;
      const h = container.clientHeight || 460;
      cameraRef.current.aspect = w / h;
      cameraRef.current.updateProjectionMatrix();
      rendererRef.current.setSize(w, h);
    };
    window.addEventListener('resize', handleResize);

    return () => {
      isDestroyed = true;
      container.removeEventListener('mousedown', handleMouseDown);
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
      container.removeEventListener('wheel', handleWheel);
      window.removeEventListener('resize', handleResize);
      cancelAnimationFrame(animationFrameId);
      
      if (rendererRef.current && rendererRef.current.domElement) {
        rendererRef.current.dispose();
      }
    };
  }, [updatePinsAndArcs]);

  // Synchronize Pins and Arcs when stations, selection, or layer toggles change
  useEffect(() => {
    updatePinsAndArcs();
  }, [stations, selectedStationId, showArcs, updatePinsAndArcs]);

  // Smooth camera orbit to focused station upon selection
  useEffect(() => {
    if (!selectedStationId) return;
    const selected = stations.find((s) => s.station_id === selectedStationId);
    if (selected) {
      const lat = selected.latitude ?? 28.6139;
      const lon = selected.longitude ?? 77.2090;
      const pos = latLonToVector3(lat, lon, 1.0);

      // Rotate globe so that the selected station point faces directly toward +Z
      const targetYaw = -Math.atan2(pos.x, pos.z);
      const targetPitch = -Math.asin(Math.max(-0.95, Math.min(0.95, pos.y)));

      targetRotationRef.current = {
        x: Math.max(-0.85, Math.min(0.85, targetPitch * 0.75)),
        y: targetYaw,
      };
      setIsAutoRotating(false);
    }
  }, [selectedStationId, stations, latLonToVector3]);

  const handleZoom = (delta: number) => {
    if (!cameraRef.current) return;
    const newZ = Math.max(1.7, Math.min(4.8, cameraRef.current.position.z + delta));
    cameraRef.current.position.setZ(newZ);
  };

  const handleResetCamera = () => {
    targetRotationRef.current = { x: 0.32, y: 1.4 };
    if (cameraRef.current) cameraRef.current.position.set(0, 0, 2.9);
    setIsAutoRotating(true);
  };

  return (
    <div className={`relative bg-[#152033] border border-[#263B5E] rounded-xl overflow-hidden shadow-2xl flex flex-col ${className}`}>
      {/* Top Header Overlay */}
      <div className="absolute top-3 left-3 right-3 z-20 flex flex-wrap items-center justify-between gap-2 pointer-events-none">
        <div className="flex items-center gap-2 bg-[#1B2A44]/95 backdrop-blur-md px-3 py-1.5 rounded-lg border border-white/[0.08] pointer-events-auto shadow-md">
          <Globe className="w-4 h-4 text-sky-400" />
          <span className="text-xs font-bold font-mono text-white tracking-wide uppercase">
            GEOSPATIAL DIGITAL TWIN (WGS84)
          </span>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-sky-500/15 text-sky-300 border border-sky-500/30 font-semibold">
            {stations.length} LIVE NODES
          </span>
        </div>

        <div className="flex items-center gap-1.5 bg-[#1B2A44]/95 backdrop-blur-md p-1 rounded-lg border border-white/[0.08] pointer-events-auto shadow-md text-xs font-mono">
          <button 
            onClick={() => setShowArcs(!showArcs)} 
            className={`px-2 py-1 rounded text-[11px] font-medium transition-colors ${showArcs ? 'bg-sky-500/20 text-sky-300 border border-sky-500/30' : 'text-slate-400 hover:text-white'}`}
          >
            Arcs
          </button>
          <button 
            onClick={() => setIsAutoRotating(!isAutoRotating)} 
            className={`p-1.5 rounded transition-colors ${isAutoRotating ? 'text-sky-400 bg-sky-500/20' : 'text-slate-400 hover:text-white'}`}
            title="Toggle Auto-Rotation"
          >
            <RotateCw className="w-3.5 h-3.5" />
          </button>
          <button 
            onClick={() => handleZoom(-0.3)} 
            className="p-1.5 rounded text-slate-400 hover:text-white hover:bg-white/[0.06] transition-colors"
            title="Zoom In"
          >
            <ZoomIn className="w-3.5 h-3.5" />
          </button>
          <button 
            onClick={() => handleZoom(0.3)} 
            className="p-1.5 rounded text-slate-400 hover:text-white hover:bg-white/[0.06] transition-colors"
            title="Zoom Out"
          >
            <ZoomOut className="w-3.5 h-3.5" />
          </button>
          <button 
            onClick={handleResetCamera} 
            className="p-1.5 rounded text-slate-400 hover:text-white hover:bg-white/[0.06] transition-colors"
            title="Reset Orientation"
          >
            <Compass className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Main 3D Canvas Viewport */}
      <div className="relative w-full h-[460px] bg-[#080E1B]">
        <div
          ref={mountRef}
          className="w-full h-full cursor-grab active:cursor-grabbing"
        />
      </div>

      {/* Interactive Station Hover Dossier Tooltip */}
      {hoveredStation && (
        <div
          className="absolute z-40 pointer-events-none bg-[#111A2B]/95 backdrop-blur-md border border-[#38BDF8]/40 rounded-lg p-3 shadow-2xl text-xs font-mono text-white min-w-[240px]"
          style={{
            left: Math.min(window.innerWidth - 280, Math.max(10, hoverPos.x + 15)),
            top: Math.min(380, Math.max(10, hoverPos.y - 50)),
          }}
        >
          <div className="flex items-center justify-between border-b border-white/[0.1] pb-1.5 mb-1.5">
            <div className="flex items-center gap-1.5">
              <Radio className="w-3.5 h-3.5 text-sky-400 animate-pulse" />
              <span className="font-bold text-sky-300">{hoveredStation.station_id}</span>
            </div>
            <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${(hoveredStation.health_score ?? 98) >= 75 ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40' : (hoveredStation.health_score ?? 98) >= 50 ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40' : 'bg-rose-500/20 text-rose-300 border border-rose-500/40'}`}>
              {hoveredStation.health_status || 'NOMINAL'}
            </span>
          </div>

          <div className="text-[11px] text-slate-100 font-semibold mb-2 flex items-center gap-1">
            <MapPin className="w-3 h-3 text-sky-400" />
            <span>{hoveredStation.name}</span>
          </div>

          <div className="grid grid-cols-2 gap-1.5 text-[10px] text-slate-300">
            <div>
              <span className="text-slate-400 block text-[9px]">Coordinates</span>
              <span className="text-sky-300">{hoveredStation.latitude?.toFixed(2)}°N, {hoveredStation.longitude?.toFixed(2)}°E</span>
            </div>
            <div>
              <span className="text-slate-400 block text-[9px]">Elevation</span>
              <span>{hoveredStation.elevation ?? 216} m MSL</span>
            </div>
            <div>
              <span className="text-slate-400 block text-[9px]">Health Score</span>
              <span className="text-emerald-400 font-bold">{hoveredStation.health_score ?? 98}%</span>
            </div>
            <div>
              <span className="text-slate-400 block text-[9px]">Status</span>
              <span className="text-sky-300">{hoveredStation.status || 'ACTIVE'}</span>
            </div>
          </div>

          <div className="mt-2 pt-1.5 border-t border-white/[0.06] text-[9px] text-slate-400 flex items-center justify-between">
            <span className="text-sky-400">Click node to focus camera</span>
            <span className="text-emerald-400 font-semibold">Tier 3.5 Consensus</span>
          </div>
        </div>
      )}

      {/* Bottom Status Footer */}
      <div className="px-4 py-2.5 bg-[#10192A] border-t border-[#263B5E] flex flex-wrap items-center justify-between gap-3 text-xs font-mono">
        <div className="flex items-center gap-4 text-slate-300">
          <div className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-emerald-400 shadow-[0_0_8px_#10b981]" />
            <span className="text-[11px]">Nominal (Active)</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-amber-400 shadow-[0_0_8px_#f59e0b]" />
            <span className="text-[11px]">Degraded</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-rose-500 shadow-[0_0_8px_#ef4444]" />
            <span className="text-[11px]">Critical</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-sky-400 shadow-[0_0_8px_#38bdf8]" />
            <span className="text-[11px]">Selected Target</span>
          </div>
        </div>

        <div className="flex items-center gap-2 text-[11px] text-slate-400">
          <Activity className="w-3.5 h-3.5 text-sky-400" />
          <span className="flex items-center gap-1">
            <span>Mesh:</span>
            {modelStatus === 'loaded' ? (
              <span className="text-emerald-400 font-bold flex items-center gap-1"><CheckCircle2 className="w-3 h-3" /> EarthGlobe Atlas (Calibrated WGS84)</span>
            ) : modelStatus === 'loading' ? (
              <span className="text-sky-400 font-semibold">Calibrating Projection...</span>
            ) : (
              <span className="text-slate-300">Calibrated Geospatial Surface</span>
            )}
          </span>
        </div>
      </div>
    </div>
  );
};
