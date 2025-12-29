import React, { useState, useRef, useEffect } from 'react';
import { motion, useMotionValue, useTransform } from 'framer-motion';
import { ChevronDoubleRightIcon } from '@heroicons/react/24/outline';
 

interface ImageComparatorProps {
  originalImage: string | null;
  modifiedImage: string | null;
  enableSlider?: boolean;
}

export const ImageComparator: React.FC<ImageComparatorProps> = ({
  originalImage,
  modifiedImage,
  enableSlider = false,
}) => {
  const [width, setWidth] = useState(0);
  const x = useMotionValue(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const widthRef = useRef(0);
  const [isDragging, setIsDragging] = useState(false);
  const [scale, setScale] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [isPanning, setIsPanning] = useState(false);
  const lastPointRef = useRef<{ x: number; y: number }>({ x: 0, y: 0 });
  const [loadingCount, setLoadingCount] = useState(0);
  const [isLoaded, setIsLoaded] = useState(false);
  const pinchRef = useRef<{ dist: number; cx: number; cy: number } | null>(null);

  // Observe container size to keep slider aligned when layout changes
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const rect = entries[0].contentRect;
      const newW = Math.max(0, rect.width);
      const prevW = widthRef.current;
      widthRef.current = newW;
      setWidth(newW);
      // Preserve slider position as a percentage when width changes
      const prevX = x.get();
      const ratio = prevW > 0 ? prevX / prevW : 0.5;
      const nextX = enableSlider ? Math.max(0, Math.min(newW, ratio * newW)) : 0;
      x.set(nextX);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [enableSlider]);

  // Clamp x while dragging within current bounds

  // Handle Drag Events
  useEffect(() => {
    if (!isDragging) return;

    const handlePointerMove = (e: PointerEvent) => {
      if (!containerRef.current) return;
      
      const rect = containerRef.current.getBoundingClientRect();
      // Calculate X relative to container, clamped within bounds
      const newX = Math.max(0, Math.min(rect.width, e.clientX - rect.left));
      x.set(newX);
    };

    const handlePointerUp = () => {
      setIsDragging(false);
    };

    window.addEventListener('pointermove', handlePointerMove);
    window.addEventListener('pointerup', handlePointerUp);

    return () => {
      window.removeEventListener('pointermove', handlePointerMove);
      window.removeEventListener('pointerup', handlePointerUp);
    };
  }, [isDragging, x]);

  useEffect(() => {
    setIsLoaded(loadingCount >= (originalImage && modifiedImage ? 2 : 1));
  }, [loadingCount, originalImage, modifiedImage]);

  const handleWheel: React.WheelEventHandler<HTMLDivElement> = (e) => {
    const rect = containerRef.current?.getBoundingClientRect();
    const cx = rect ? e.clientX - rect.left : 0;
    const cy = rect ? e.clientY - rect.top : 0;
    const delta = -e.deltaY;
    const factor = delta > 0 ? 1.08 : 0.92;
    const next = Math.max(1, Math.min(6, scale * factor));
    const dx = (cx - offset.x) * (next / scale - 1);
    const dy = (cy - offset.y) * (next / scale - 1);
    setOffset({ x: offset.x - dx, y: offset.y - dy });
    setScale(next);
  };

  const onPointerDown: React.PointerEventHandler<HTMLDivElement> = (e) => {
    if ((e.target as HTMLElement).closest('.pointer-lock')) return;
    setIsPanning(true);
    lastPointRef.current = { x: e.clientX, y: e.clientY };
  };
  useEffect(() => {
    if (!isPanning) return;
    const move = (e: PointerEvent) => {
      const dx = e.clientX - lastPointRef.current.x;
      const dy = e.clientY - lastPointRef.current.y;
      lastPointRef.current = { x: e.clientX, y: e.clientY };
      setOffset((p) => ({ x: p.x + dx, y: p.y + dy }));
    };
    const up = () => setIsPanning(false);
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
    return () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
    };
  }, [isPanning]);

  const onTouchStart: React.TouchEventHandler<HTMLDivElement> = (e) => {
    if (e.touches.length === 2) {
      const t0 = e.touches[0];
      const t1 = e.touches[1];
      const dx = t1.clientX - t0.clientX;
      const dy = t1.clientY - t0.clientY;
      const dist = Math.hypot(dx, dy);
      const rect = containerRef.current?.getBoundingClientRect();
      const cx = rect ? (t0.clientX + t1.clientX) / 2 - rect.left : 0;
      const cy = rect ? (t0.clientY + t1.clientY) / 2 - rect.top : 0;
      pinchRef.current = { dist, cx, cy };
    } else if (e.touches.length === 1) {
      setIsPanning(true);
      lastPointRef.current = { x: e.touches[0].clientX, y: e.touches[0].clientY };
    }
  };
  const onTouchMove: React.TouchEventHandler<HTMLDivElement> = (e) => {
    if (e.touches.length === 2 && pinchRef.current) {
      const t0 = e.touches[0];
      const t1 = e.touches[1];
      const dx = t1.clientX - t0.clientX;
      const dy = t1.clientY - t0.clientY;
      const dist = Math.hypot(dx, dy);
      const factor = dist / pinchRef.current.dist;
      const next = Math.max(1, Math.min(6, scale * factor));
      const cx = pinchRef.current.cx;
      const cy = pinchRef.current.cy;
      const dx2 = (cx - offset.x) * (next / scale - 1);
      const dy2 = (cy - offset.y) * (next / scale - 1);
      setOffset({ x: offset.x - dx2, y: offset.y - dy2 });
      setScale(next);
      pinchRef.current.dist = dist;
    } else if (e.touches.length === 1) {
      const dx = e.touches[0].clientX - lastPointRef.current.x;
      const dy = e.touches[0].clientY - lastPointRef.current.y;
      lastPointRef.current = { x: e.touches[0].clientX, y: e.touches[0].clientY };
      setOffset((p) => ({ x: p.x + dx, y: p.y + dy }));
    }
  };
  const onTouchEnd: React.TouchEventHandler<HTMLDivElement> = () => {
    setIsPanning(false);
    pinchRef.current = null;
  };

  return (
    <div
      ref={containerRef}
      className="relative w-full h-full select-none group bg-[#0b0b0c] overflow-hidden overscroll-none"
      onWheel={handleWheel}
      onPointerDown={onPointerDown}
      onTouchStart={onTouchStart}
      onTouchMove={onTouchMove}
      onTouchEnd={onTouchEnd}
    >
      {!isLoaded && (
        <div className="absolute inset-0 flex items-center justify-center z-30" />
      )}
      <div
        className="absolute inset-0"
        style={{
          transform: `translate(${offset.x}px, ${offset.y}px) scale(${scale})`,
          transition: isPanning ? 'none' : 'transform 0.2s ease-out',
          willChange: 'transform',
          transformOrigin: 'top left'
        }}
      >
      {/* Bottom Image (Modified) */}
      {modifiedImage && (
        <img
          src={modifiedImage}
          className="absolute inset-0 w-full h-full object-contain pointer-events-none"
          alt="Modified"
          onLoad={() => setLoadingCount((c) => c + 1)}
        />
      )}
      {enableSlider && (
        <div className="absolute top-4 right-4 px-3 py-1 bg-black/60 backdrop-blur-md rounded-full text-white text-xs font-medium border border-white/20 pointer-events-none">
          After
        </div>
      )}

      {/* Top Image (Original) - Clipped */}
      <motion.div
        className="absolute inset-0 w-full h-full overflow-hidden"
        style={{
          clipPath: useTransform(x, (val) =>
            enableSlider ? `inset(0 ${width - val}px 0 0)` : `inset(0 ${width}px 0 0)`
          ),
        }}
      >
        {originalImage && (
          <img
            src={originalImage}
            className="absolute inset-0 w-full h-full object-contain pointer-events-none"
            alt="Original"
            onLoad={() => setLoadingCount((c) => c + 1)}
          />
        )}
        {enableSlider && (
          <div className="absolute top-4 left-4 px-3 py-1 bg-black/60 backdrop-blur-md rounded-full text-white text-xs font-medium border border-white/20 pointer-events-none">
            Before
          </div>
        )}
      </motion.div>

      {/* Slider Handle */}
      {enableSlider && (
        <motion.div
          className="absolute top-0 bottom-0 w-0.5 bg-white cursor-ew-resize shadow-[0_0_10px_rgba(0,0,0,0.3)] z-10 touch-none"
          style={{ x }}
          onPointerDown={(e) => {
            setIsDragging(true);
            e.preventDefault(); // Prevent text selection or default touch actions
            e.stopPropagation();
          }}
        >
          {/* Handle Icon */}
          <div className="absolute top-1/2 -left-4 w-8 h-8 bg-white rounded-full shadow-lg flex items-center justify-center transform -translate-y-1/2 cursor-ew-resize hover:scale-110 transition-transform">
            <div className="flex gap-0.5 pointer-events-none">
              <ChevronDoubleRightIcon className="w-4 h-4 text-zinc-400 rotate-180" />
              <ChevronDoubleRightIcon className="w-4 h-4 text-zinc-400" />
            </div>
          </div>
        </motion.div>
      )}
      </div>
    </div>
  );
};
