
import React, { useRef, useEffect, useState, useMemo } from 'react';
import { 
  PencilIcon, 
  StopIcon, 
  ArrowLongLeftIcon,
  ChatBubbleOvalLeftEllipsisIcon,
  ArrowUturnLeftIcon,
  XMarkIcon, 
  TrashIcon,
  Squares2X2Icon,
  HashtagIcon,
  CheckIcon,
  EyeDropperIcon,
  MagnifyingGlassPlusIcon,
  MagnifyingGlassMinusIcon,
  HandRaisedIcon
} from '@heroicons/react/24/outline';

interface CanvasMaskEditorProps {
  imageSrc: string;
  onMaskGenerated: (maskBlob: Blob) => void;
  onCancel: () => void;
  onSubmit: () => void;
  lang: 'zh' | 'en';
}

type Tool = 'brush' | 'rect' | 'arrow' | 'text' | 'comment' | 'pan';

// Advanced Color Picker Helper
const hexToRgb = (hex: string) => {
  const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
  return result ? {
    r: parseInt(result[1], 16),
    g: parseInt(result[2], 16),
    b: parseInt(result[3], 16)
  } : { r: 0, g: 0, b: 0 };
};

const rgbToHex = (r: number, g: number, b: number) => {
  return "#" + ((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1).toUpperCase();
};

export const CanvasMaskEditor: React.FC<CanvasMaskEditorProps> = ({
  imageSrc,
  onMaskGenerated,
  onCancel,
  onSubmit,
  lang
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const imageRef = useRef<HTMLImageElement>(null);
  
  // Canvas State
  const [context, setContext] = useState<CanvasRenderingContext2D | null>(null);
  const [isDrawing, setIsDrawing] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);
  
  // Tools & Settings
  const [tool, setTool] = useState<Tool>('pan'); // Default to Pan for better UX
  const [color, setColor] = useState('#FF4081'); 
  const [showColorPicker, setShowColorPicker] = useState(false);
  const [brushSize] = useState(8); 
  
  // Viewport State (Zoom/Pan)
  const [scale, setScale] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [isPanning, setIsPanning] = useState(false);
  const [lastMousePos, setLastMousePos] = useState({ x: 0, y: 0 });

  // Annotation State
  const [pendingAnnotation, setPendingAnnotation] = useState<{
      type: 'comment' | 'text';
      x: number; 
      y: number;
      w?: number; // For comment rect
      h?: number;
  } | null>(null);
  const [inputValue, setInputValue] = useState('');

  // History for Undo/Redo
  const [history, setHistory] = useState<ImageData[]>([]);
  const [historyStep, setHistoryStep] = useState(-1);

  // Temporary shape drawing
  const [startPos, setStartPos] = useState<{x: number, y: number} | null>(null);
  const [tempSnapshot, setTempSnapshot] = useState<ImageData | null>(null);

  // Color Picker Internal State
  const [rgb, setRgb] = useState({ r: 255, g: 64, b: 129 });

  // Translations
  const t = useMemo(() => ({
      en: {
          pan: 'Move / Pan',
          comment: 'Comment (Box + Text)',
          arrow: 'Arrow',
          rect: 'Rectangle',
          text: 'Text',
          sketch: 'Sketch',
          undo: 'Undo',
          clear: 'Clear',
          addToChat: '+ Add to chat',
          annotateMode: 'Annotate Mode • Wheel to Zoom',
          addComment: 'Add a comment...',
          addText: 'Add text...',
      },
      zh: {
          pan: '移动 / 拖拽',
          comment: '评论 (选框 + 文本)',
          arrow: '箭头',
          rect: '矩形',
          text: '文本',
          sketch: '涂鸦',
          undo: '撤销',
          clear: '清除',
          addToChat: '+ 添加到对话',
          annotateMode: '标注模式 • 滚轮缩放',
          addComment: '添加评论...',
          addText: '添加文本...',
      }
  }), []);
  const dict = t[lang];

  useEffect(() => {
      setRgb(hexToRgb(color));
  }, [color]);

  // Initialize Canvas
  useEffect(() => {
    const img = new Image();
    img.src = imageSrc;
    img.crossOrigin = "anonymous";
    img.onload = () => {
      if (canvasRef.current && containerRef.current) {
        const canvas = canvasRef.current;
        canvas.width = img.naturalWidth;
        canvas.height = img.naturalHeight;
        
        const ctx = canvas.getContext('2d', { willReadFrequently: true });
        if (ctx) {
          ctx.lineCap = 'round';
          ctx.lineJoin = 'round';
          setContext(ctx);
          
          // Initial Fit
          fitToScreen(img.naturalWidth, img.naturalHeight);

          const blankState = ctx.getImageData(0, 0, canvas.width, canvas.height);
          setHistory([blankState]);
          setHistoryStep(0);
        }
      }
    };
  }, [imageSrc]);

  const fitToScreen = (w: number, h: number) => {
      if (!containerRef.current) return;
      const containerAspect = containerRef.current.clientWidth / containerRef.current.clientHeight;
      const imgAspect = w / h;
      let initScale = 1;
      
      if (imgAspect > containerAspect) {
        initScale = (containerRef.current.clientWidth * 0.95) / w;
      } else {
        initScale = (containerRef.current.clientHeight * 0.95) / h;
      }
      setScale(initScale);
      
      setOffset({
        x: (containerRef.current.clientWidth - w * initScale) / 2,
        y: (containerRef.current.clientHeight - h * initScale) / 2
      });
  };

  // --- Coordinate Helpers ---
  const getCanvasCoordinates = (e: React.MouseEvent | React.TouchEvent) => {
    if (!canvasRef.current || !containerRef.current) return { x: 0, y: 0 };

    let clientX, clientY;
    if ('touches' in e) {
      clientX = e.touches[0].clientX;
      clientY = e.touches[0].clientY;
    } else {
      clientX = (e as React.MouseEvent).clientX;
      clientY = (e as React.MouseEvent).clientY;
    }

    const rect = containerRef.current.getBoundingClientRect();
    const relX = clientX - rect.left;
    const relY = clientY - rect.top;

    return {
      x: (relX - offset.x) / scale,
      y: (relY - offset.y) / scale
    };
  };

  // --- Shape Drawing Functions ---
  const drawArrow = (ctx: CanvasRenderingContext2D, fromX: number, fromY: number, toX: number, toY: number) => {
      const headlen = 25 / scale; 
      const angle = Math.atan2(toY - fromY, toX - fromX);
      
      ctx.beginPath();
      ctx.moveTo(fromX, fromY);
      ctx.lineTo(toX, toY);
      ctx.lineWidth = 6 / scale;
      ctx.stroke();
      
      ctx.beginPath();
      ctx.moveTo(toX, toY);
      ctx.lineTo(toX - headlen * Math.cos(angle - Math.PI / 6), toY - headlen * Math.sin(angle - Math.PI / 6));
      ctx.lineTo(toX - headlen * Math.cos(angle + Math.PI / 6), toY - headlen * Math.sin(angle + Math.PI / 6));
      ctx.lineTo(toX, toY);
      ctx.fill();
  };

  // --- Interaction Handlers ---
  const startAction = (e: React.MouseEvent | React.TouchEvent) => {
    if (tool === 'pan' || (e as React.MouseEvent).button === 1 || (e as React.MouseEvent).ctrlKey) {
        startPan(e);
        return;
    }

    if (pendingAnnotation) {
        return; 
    }

    if (!context || !canvasRef.current) return;
    const { x, y } = getCanvasCoordinates(e);
    
    if (tool === 'text') {
        setPendingAnnotation({ type: 'text', x, y });
        setInputValue('');
        return;
    }
    
    setIsDrawing(true);
    setStartPos({ x, y });
    saveSnapshot();

    context.beginPath();
    context.moveTo(x, y);
    
    context.strokeStyle = color;
    context.fillStyle = color;
    context.lineWidth = brushSize / scale;
    
    // Reset Dash
    context.setLineDash([]);

    if (tool === 'comment') {
        context.setLineDash([10 / scale, 10 / scale]);
        context.lineWidth = 4 / scale;
    }
  };

  const moveAction = (e: React.MouseEvent | React.TouchEvent) => {
    if (isPanning) {
        pan(e);
        return;
    }
    
    if (!isDrawing || !context || !startPos) return;
    const { x, y } = getCanvasCoordinates(e);

    if (tool === 'brush') {
        context.lineTo(x, y);
        context.stroke();
    } else if (tool === 'rect' || tool === 'arrow' || tool === 'comment') {
        restoreSnapshot();
        if (tool === 'rect' || tool === 'comment') {
            const w = x - startPos.x;
            const h = y - startPos.y;
            context.strokeRect(startPos.x, startPos.y, w, h);
        } else if (tool === 'arrow') {
            drawArrow(context, startPos.x, startPos.y, x, y);
        }
    }
  };

  const endAction = (e: React.MouseEvent | React.TouchEvent) => {
    if (isPanning) {
        setIsPanning(false);
        return;
    }
    if (!isDrawing || !startPos) return;
    
    const { x, y } = getCanvasCoordinates(e);
    
    setIsDrawing(false);
    
    if (tool === 'comment') {
        const w = x - startPos.x;
        const h = y - startPos.y;
        setPendingAnnotation({ type: 'comment', x: startPos.x, y: startPos.y, w, h });
        setInputValue('');
    } else {
        setStartPos(null);
        setTempSnapshot(null);
        saveHistory();
        setHasChanges(true);
        generateMaskBlob();
    }
  };

  const commitAnnotation = () => {
      if (!pendingAnnotation || !context) return;
      
      if (inputValue.trim()) {
          context.save();
          context.fillStyle = color;
          context.font = `bold ${24/scale}px sans-serif`;
          context.textBaseline = 'top';
          
          let textX = pendingAnnotation.x;
          let textY = pendingAnnotation.y;
          
          if (pendingAnnotation.type === 'comment' && pendingAnnotation.h) {
              textY = pendingAnnotation.y + pendingAnnotation.h + (10/scale);
              textX = pendingAnnotation.x;
          }

          context.fillStyle = color;
          context.fillText(inputValue, textX, textY);
          context.restore();
          
          saveHistory();
          setHasChanges(true);
          generateMaskBlob();
      } else {
          if (pendingAnnotation.type === 'comment') {
             undo(); 
          }
      }

      setPendingAnnotation(null);
      setTempSnapshot(null); 
      setStartPos(null);
  };

  const cancelAnnotation = () => {
      if (pendingAnnotation) {
          if (pendingAnnotation.type === 'comment') {
              restoreSnapshot();
          }
          setPendingAnnotation(null);
          setTempSnapshot(null);
          setStartPos(null);
      }
  };

  const saveSnapshot = () => {
      if (context && canvasRef.current) {
          setTempSnapshot(context.getImageData(0, 0, canvasRef.current.width, canvasRef.current.height));
      }
  };

  const restoreSnapshot = () => {
      if (context && tempSnapshot) {
          context.putImageData(tempSnapshot, 0, 0);
      }
  };

  const saveHistory = () => {
      if (context && canvasRef.current) {
          const newState = context.getImageData(0, 0, canvasRef.current.width, canvasRef.current.height);
          const newHistory = history.slice(0, historyStep + 1);
          newHistory.push(newState);
          setHistory(newHistory);
          setHistoryStep(newHistory.length - 1);
      }
  };

  const undo = () => {
      if (historyStep > 0 && context) {
          const prev = history[historyStep - 1];
          context.putImageData(prev, 0, 0);
          setHistoryStep(prevStep => prevStep - 1);
          generateMaskBlob();
          if (historyStep - 1 === 0) setHasChanges(false);
      } else if (historyStep === 0 && context) {
          const prev = history[0];
          context.putImageData(prev, 0, 0);
          setHasChanges(false);
      }
  };

  const clearCanvas = () => {
      if (context && canvasRef.current) {
          context.clearRect(0, 0, canvasRef.current.width, canvasRef.current.height);
          saveHistory();
          generateMaskBlob();
          setHasChanges(false);
      }
  };

  const generateMaskBlob = () => {
    if (!canvasRef.current) return;
    const maskCanvas = document.createElement('canvas');
    maskCanvas.width = canvasRef.current.width;
    maskCanvas.height = canvasRef.current.height;
    const maskCtx = maskCanvas.getContext('2d');
    
    if (maskCtx) {
      maskCtx.fillStyle = '#000000';
      maskCtx.fillRect(0, 0, maskCanvas.width, maskCanvas.height);
      maskCtx.drawImage(canvasRef.current, 0, 0);
      maskCtx.globalCompositeOperation = 'source-in';
      maskCtx.fillStyle = '#FFFFFF';
      maskCtx.fillRect(0, 0, maskCanvas.width, maskCanvas.height);
    }

    maskCanvas.toBlob((blob) => {
      if (blob) onMaskGenerated(blob);
    }, 'image/png');
  };

  // --- Zoom/Pan ---
  const startPan = (e: React.MouseEvent | React.TouchEvent) => {
    setIsPanning(true);
    let cx, cy;
    if ('touches' in e) { cx = e.touches[0].clientX; cy = e.touches[0].clientY; }
    else { cx = (e as React.MouseEvent).clientX; cy = (e as React.MouseEvent).clientY; }
    setLastMousePos({ x: cx, y: cy });
  };

  const pan = (e: React.MouseEvent | React.TouchEvent) => {
    let cx, cy;
    if ('touches' in e) { cx = e.touches[0].clientX; cy = e.touches[0].clientY; }
    else { cx = (e as React.MouseEvent).clientX; cy = (e as React.MouseEvent).clientY; }
    setOffset(p => ({ x: p.x + (cx - lastMousePos.x), y: p.y + (cy - lastMousePos.y) }));
    setLastMousePos({ x: cx, y: cy });
  };
  
  const handleWheel = (e: React.WheelEvent) => {
     if (!containerRef.current) return;
     
     // Stop propagation to prevent page scroll
     e.stopPropagation();
     
     const rect = containerRef.current.getBoundingClientRect();
     const mouseX = e.clientX - rect.left;
     const mouseY = e.clientY - rect.top;

     // Calculate point on content under mouse (Image Coordinates)
     const pointX = (mouseX - offset.x) / scale;
     const pointY = (mouseY - offset.y) / scale;

     // Zoom sensitivity
     const delta = -e.deltaY * 0.002;
     const newScale = Math.min(Math.max(0.1, scale + delta), 5);

     // Calculate new offset to keep point under mouse
     // mouseX = newOffsetX + pointX * newScale
     const newOffsetX = mouseX - pointX * newScale;
     const newOffsetY = mouseY - pointY * newScale;

     setScale(newScale);
     setOffset({ x: newOffsetX, y: newOffsetY });
  };

  const zoomToCenter = (targetScale: number) => {
      if (!containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const cx = rect.width / 2;
      const cy = rect.height / 2;
      
      const pointX = (cx - offset.x) / scale;
      const pointY = (cy - offset.y) / scale;
      
      const newScale = Math.min(Math.max(0.1, targetScale), 5);
      
      const newOffsetX = cx - pointX * newScale;
      const newOffsetY = cy - pointY * newScale;
      
      setScale(newScale);
      setOffset({ x: newOffsetX, y: newOffsetY });
  };

  const zoomIn = () => zoomToCenter(scale + 0.5);
  const zoomOut = () => zoomToCenter(scale - 0.5);
  
  const resetZoom = () => {
      if (canvasRef.current) fitToScreen(canvasRef.current.width, canvasRef.current.height);
  };

  const getPopupStyle = () => {
      if (!pendingAnnotation) return { display: 'none' };
      let px = pendingAnnotation.x * scale + offset.x;
      let py = pendingAnnotation.y * scale + offset.y;

      if (pendingAnnotation.type === 'comment' && pendingAnnotation.h) {
          py += (pendingAnnotation.h * scale) + 10;
      } else {
          py += 20;
      }
      
      return {
          left: px + 'px',
          top: py + 'px',
          position: 'absolute' as const,
          zIndex: 100
      };
  };

  const updateColor = (r: number, g: number, b: number) => {
      setRgb({r, g, b});
      setColor(rgbToHex(r, g, b));
  };

  return (
    <div className="relative w-full h-full flex items-center justify-center bg-[#0b0b0c] overflow-hidden select-none group">
      
      {/* Viewport */}
      <div 
        ref={containerRef}
        className="relative w-full h-full overflow-hidden"
        onWheel={handleWheel}
        onMouseDown={startAction}
        onMouseMove={moveAction}
        onMouseUp={endAction}
        onMouseLeave={endAction}
        onTouchStart={startAction}
        onTouchMove={moveAction}
        onTouchEnd={endAction}
        style={{ cursor: tool === 'pan' || isPanning ? 'grab' : 'crosshair' }}
      >
        <div style={{ 
            transform: `translate(${offset.x}px, ${offset.y}px) scale(${scale})`,
            transformOrigin: '0 0',
            transition: isPanning ? 'none' : 'transform 0.1s ease-out'
        }}>
            <img ref={imageRef} src={imageSrc} className="absolute top-0 left-0 pointer-events-none" draggable={false} style={{maxWidth:'none'}}/>
            <canvas ref={canvasRef} className="absolute top-0 left-0" />
        </div>
        
        {pendingAnnotation && (
            <div style={getPopupStyle()}>
                <div className="flex items-center bg-[#1E1E1E] border border-white/20 rounded-full shadow-2xl p-1 animate-in fade-in zoom-in duration-200">
                    <input 
                        autoFocus
                        type="text"
                        value={inputValue}
                        onChange={e => setInputValue(e.target.value)}
                        onKeyDown={e => e.key === 'Enter' && commitAnnotation()}
                        placeholder={pendingAnnotation.type === 'comment' ? dict.addComment : dict.addText}
                        className="bg-transparent border-none outline-none text-white text-sm px-3 py-1 w-48 placeholder-zinc-500"
                    />
                    <button 
                        onClick={commitAnnotation}
                        className="p-1.5 bg-[#333] hover:bg-[#444] rounded-full text-white transition-colors"
                    >
                        <CheckIcon className="w-4 h-4" />
                    </button>
                </div>
            </div>
        )}
      </div>

      {/* --- Zoom Controls --- */}
      <div className="absolute bottom-28 left-1/2 -translate-x-1/2 z-40 flex gap-2">
           <button onClick={zoomOut} className="p-2 bg-[#262626] rounded-full text-zinc-400 hover:text-white border border-white/10 shadow-lg" title="Zoom Out">
               <MagnifyingGlassMinusIcon className="w-5 h-5" />
           </button>
           <button onClick={resetZoom} className="px-3 py-2 bg-[#262626] rounded-full text-zinc-400 hover:text-white text-xs font-medium border border-white/10 shadow-lg">
               {(scale * 100).toFixed(0)}%
           </button>
           <button onClick={zoomIn} className="p-2 bg-[#262626] rounded-full text-zinc-400 hover:text-white border border-white/10 shadow-lg" title="Zoom In">
               <MagnifyingGlassPlusIcon className="w-5 h-5" />
           </button>
      </div>

      {/* --- Annanote Toolbar --- */}
      <div className="absolute bottom-8 left-1/2 -translate-x-1/2 z-50">
          <div className="flex items-center bg-[#262626] rounded-full px-1.5 py-1 shadow-2xl border border-white/10 gap-1" style={{ transform: 'scale(1)', transformOrigin: 'center' }}>
              
              <div className="p-1.5 text-zinc-500 cursor-grab">
                  <Squares2X2Icon className="w-4 h-4" />
              </div>

              {/* Pan Tool */}
              <button
                onClick={() => setTool('pan')}
                className={`p-1.5 rounded-lg transition-all ${tool === 'pan' ? 'bg-[#333] text-white' : 'text-zinc-400 hover:text-zinc-200'}`}
                title={dict.pan}
              >
                  <HandRaisedIcon className="w-4 h-4" />
              </button>

              <div className="w-px h-5 bg-white/10 mx-1"></div>

              <button
                onClick={() => setTool('comment')}
                className={`p-1.5 rounded-lg transition-all ${tool === 'comment' ? 'bg-[#333] text-white' : 'text-zinc-400 hover:text-zinc-200'}`}
                title={dict.comment}
              >
                  <ChatBubbleOvalLeftEllipsisIcon className="w-4 h-4" />
              </button>

              <button
                onClick={() => setTool('arrow')}
                className={`p-1.5 rounded-lg transition-all ${tool === 'arrow' ? 'bg-[#333] text-white' : 'text-zinc-400 hover:text-zinc-200'}`}
                title={dict.arrow}
              >
                  <ArrowLongLeftIcon className="w-4 h-4" />
              </button>

              <button
                onClick={() => setTool('rect')}
                className={`p-1.5 rounded-lg transition-all ${tool === 'rect' ? 'bg-[#333] text-white' : 'text-zinc-400 hover:text-zinc-200'}`}
                title={dict.rect}
              >
                  <StopIcon className="w-4 h-4" />
              </button>

              <button
                onClick={() => setTool('text')}
                className={`p-1.5 rounded-lg transition-all ${tool === 'text' ? 'bg-[#333] text-white' : 'text-zinc-400 hover:text-zinc-200'}`}
                title={dict.text}
              >
                  <HashtagIcon className="w-4 h-4" />
              </button>

              <button
                onClick={() => setTool('brush')}
                className={`p-1.5 rounded-lg transition-all ${tool === 'brush' ? 'bg-[#333] text-white' : 'text-zinc-400 hover:text-zinc-200'}`}
                title={dict.sketch}
              >
                  <PencilIcon className="w-4 h-4" />
              </button>

              {/* Color Picker */}
              <div className="relative mx-1">
                  <button 
                    onClick={() => setShowColorPicker(!showColorPicker)}
                    className="w-5 h-5 rounded-full border border-white/20 flex items-center justify-center hover:scale-110 transition-transform"
                    style={{ backgroundColor: color }}
                  />
                  
                  {showColorPicker && (
                      <div className="absolute bottom-full mb-4 left-1/2 -translate-x-1/2 bg-[#1E1E1E] p-4 rounded-xl shadow-xl border border-white/10 w-64 animate-in slide-in-from-bottom-2 fade-in duration-200">
                          {/* Gradient Area (Simulated) */}
                          <div 
                            className="w-full h-24 rounded-lg mb-3 relative"
                            style={{
                                background: `linear-gradient(to bottom, transparent, #000), linear-gradient(to right, #FFF, hsl(${rgb.r}, 100%, 50%))`
                            }}
                          >
                             <div className="absolute top-2 right-2 w-4 h-4 border-2 border-white rounded-full shadow-md"></div>
                          </div>

                          {/* Hue Slider */}
                          <input 
                            type="range" min="0" max="360" className="w-full h-3 rounded-full mb-4 appearance-none"
                            style={{background: 'linear-gradient(to right, red, yellow, lime, cyan, blue, magenta, red)'}}
                          />

                          {/* RGB Inputs */}
                          <div className="flex gap-2 justify-between mb-3">
                              <div className="flex flex-col items-center">
                                  <input type="number" value={rgb.r} onChange={e => updateColor(Number(e.target.value), rgb.g, rgb.b)} className="w-14 bg-[#333] text-white text-center rounded py-1 text-xs border border-white/10" />
                                  <span className="text-[10px] text-zinc-500 mt-1">R</span>
                              </div>
                              <div className="flex flex-col items-center">
                                  <input type="number" value={rgb.g} onChange={e => updateColor(rgb.r, Number(e.target.value), rgb.b)} className="w-14 bg-[#333] text-white text-center rounded py-1 text-xs border border-white/10" />
                                  <span className="text-[10px] text-zinc-500 mt-1">G</span>
                              </div>
                              <div className="flex flex-col items-center">
                                  <input type="number" value={rgb.b} onChange={e => updateColor(rgb.r, rgb.g, Number(e.target.value))} className="w-14 bg-[#333] text-white text-center rounded py-1 text-xs border border-white/10" />
                                  <span className="text-[10px] text-zinc-500 mt-1">B</span>
                              </div>
                          </div>
                          
                          {/* Preset: Pink */}
                          <div className="flex gap-2 items-center pt-2 border-t border-white/10">
                              <EyeDropperIcon className="w-4 h-4 text-zinc-400" />
                              <button 
                                onClick={() => { setColor('#FF4081'); setRgb(hexToRgb('#FF4081')); }}
                                className="w-6 h-6 rounded-full bg-[#FF4081] border border-white/20"
                              />
                          </div>
                      </div>
                  )}
              </div>

              <div className="w-px h-5 bg-white/10 mx-1"></div>

              <button 
                onClick={undo} 
                disabled={historyStep <= 0} 
                className="p-1.5 text-zinc-400 hover:text-white disabled:opacity-20 transition-colors"
                title={dict.undo}
              >
                  <ArrowUturnLeftIcon className="w-4 h-4" />
              </button>
              
              <button 
                onClick={clearCanvas} 
                className="p-1.5 text-zinc-400 hover:text-white transition-colors"
                title={dict.clear}
              >
                  <TrashIcon className="w-4 h-4" />
              </button>

              <button 
                onClick={() => hasChanges && onSubmit()}
                disabled={!hasChanges}
                className="ml-1 px-3 py-1 bg-[#333] hover:bg-[#444] border border-white/10 rounded-full text-white text-xs font-medium flex items-center gap-2 transition-all disabled:opacity-40 disabled:cursor-not-allowed"
              >
                  {dict.addToChat}
              </button>

              <button onClick={onCancel} className="p-1.5 ml-1 text-zinc-400 hover:text-white">
                  <XMarkIcon className="w-4 h-4" />
              </button>
          </div>
          
          <div className="text-center mt-3 text-[10px] text-zinc-500 font-medium tracking-widest uppercase opacity-50">
              {dict.annotateMode}
          </div>
      </div>

    </div>
  );
};
