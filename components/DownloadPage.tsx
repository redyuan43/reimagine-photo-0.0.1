import React, { useEffect, useMemo, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ArrowDownTrayIcon, CheckCircleIcon } from '@heroicons/react/24/outline';
import { getApiBaseUrl, getAuthHeaders, urlToBlob } from '../services/gemini';

interface DownloadPageProps {
  sourceUrl: string | null;
  onConfirmDone?: () => void;
  onBack?: () => void;
}

type ResolutionKey = '1K' | '2K' | '4K' | '8K';
type FormatKey = 'jpeg' | 'png' | 'tiff';
type ColorMode = 'RGB' | 'GRAY';

export const DownloadPage: React.FC<DownloadPageProps> = ({ sourceUrl, onConfirmDone, onBack }) => {
  const [imgSize, setImgSize] = useState<{ w: number; h: number } | null>(null);
  const [resKey, setResKey] = useState<ResolutionKey | null>(null);
  const [format, setFormat] = useState<FormatKey>('jpeg');
  const [quality, setQuality] = useState(90);
  const [compression, setCompression] = useState(6);
  const [colorMode, setColorMode] = useState<ColorMode>('RGB');
  const [copyright, setCopyright] = useState('© 2025 Your Studio. All Rights Reserved.');
  const [cameraInfo, setCameraInfo] = useState('Camera: Unknown • Lens: Unknown • ISO: Auto');
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null);
  const [isConverting, setIsConverting] = useState(false);
  const [wmEnabled, setWmEnabled] = useState(false);
  const [wmText, setWmText] = useState('© Your Studio');
  const [wmPos, setWmPos] = useState<'BR'|'TL'>('BR');
  const [wmOpacity, setWmOpacity] = useState(0.3);
  const [wmSize, setWmSize] = useState(24);

  useEffect(() => {
    const loadSize = async () => {
      if (!sourceUrl) return;
      try {
        const blob = await urlToBlob(sourceUrl);
        const url = URL.createObjectURL(blob);
        const img = new Image();
        img.onload = () => {
          setImgSize({ w: img.naturalWidth || img.width, h: img.naturalHeight || img.height });
          URL.revokeObjectURL(url);
        };
        img.src = url;
      } catch {}
    };
    loadSize();
  }, [sourceUrl]);

  const pixelSizes = useMemo(() => {
    const src = imgSize;
    const map: Record<ResolutionKey, { w: number; h: number } | null> = { '1K': null, '2K': null, '4K': null, '8K': null };
    if (!src) return map;
    const targets: Record<ResolutionKey, number> = { '1K': 1024, '2K': 2048, '4K': 3840, '8K': 7680 };
    const landscape = src.w >= src.h;
    for (const k of Object.keys(targets) as ResolutionKey[]) {
      const maxSide = targets[k];
      if (landscape) {
        const w = maxSide;
        const h = Math.round(src.h * maxSide / src.w);
        map[k] = { w, h };
      } else {
        const h = maxSide;
        const w = Math.round(src.w * maxSide / src.h);
        map[k] = { w, h };
      }
    }
    return map;
  }, [imgSize]);

  const canDownload = !!(resKey && format && imgSize);

  const handleConfirm = async () => {
    if (!sourceUrl || !resKey) return;
    const dims = pixelSizes[resKey];
    if (!dims) return;
    try {
      setIsConverting(true);
      const blob = await urlToBlob(sourceUrl);
      const fd = new FormData();
      fd.append('image', blob, 'source.bin');
      fd.append('format', format);
      fd.append('quality', String(quality));
      fd.append('compression', String(compression));
      fd.append('resize_w', String(dims.w));
      fd.append('resize_h', String(dims.h));
      fd.append('color', colorMode);
      fd.append('copyright', copyright);
      const author = (copyright.match(/©\s*\d{4}\s*(.+?)(?:\.|$)/) || [])[1] || 'Author';
      const exif = {
        ImageDescription: cameraInfo,
        Copyright: copyright,
        Artist: author,
        Software: 'Lumima Retouch',
        DateTime: new Date().toISOString(),
      };
      const iptc = {
        ObjectName: 'Exported Image',
        Caption: cameraInfo,
        Keywords: [],
        Byline: author,
        Credit: author,
        CopyrightNotice: copyright,
      };
      fd.append('metadata', JSON.stringify({ camera: cameraInfo, exif, iptc }));
      if (wmEnabled) {
        fd.append('wm_text', wmText);
        fd.append('wm_pos', wmPos);
        fd.append('wm_opacity', String(wmOpacity));
        fd.append('wm_size', String(wmSize));
      }
      const res = await fetch(`${getApiBaseUrl()}/convert`, { method: 'POST', body: fd, headers: getAuthHeaders() });
      if (!res.ok) throw new Error(await res.text());
      const out = await res.blob();
      const url = URL.createObjectURL(out);
      setDownloadUrl(url);
      if (onConfirmDone) onConfirmDone();
      try {
        const a = document.createElement('a');
        a.href = url;
        a.download = `export.${format==='jpeg'?'jpg':format}`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
      } catch {}
    } catch (e) {
      console.error(e);
    } finally {
      setIsConverting(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#0b0b0c] text-white flex flex-col">
      <div className="flex-1 grid grid-cols-1 md:grid-cols-2 gap-6 p-6">
        <div className="bg-[#121212] border border-white/10 rounded-2xl p-4 flex flex-col">
          <div className="flex-1 flex items-start justify-center bg-black/20 rounded-xl overflow-hidden">
            <AnimatePresence>
              {sourceUrl && (
                <motion.img
                  key={sourceUrl}
                  src={sourceUrl}
                  alt="Preview"
                  className="max-w-full max-h-full object-contain"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ duration: 0.3 }}
                />
              )}
            </AnimatePresence>
          </div>
          <p className="text-xs text-gray-400 mt-2">确保预览图保持原始比例与清晰度，无失真</p>
        </div>

        <div className="bg-[#121212] border border-white/10 rounded-2xl p-4 space-y-4">
          <div>
            <label className="text-xs text-gray-300 mb-2 block">分辨率</label>
            <div className="grid grid-cols-4 gap-2">
              {(['1K','2K','4K','8K'] as ResolutionKey[]).map(k => {
                const dims = pixelSizes[k];
                const label = dims ? `${k} · ${dims.w}×${dims.h}px` : `${k}`;
                return (
                  <button
                    key={k}
                    onClick={() => setResKey(k)}
                    className={`px-2 py-2 rounded-lg text-xs border transition-colors ${resKey===k ? 'bg-amber-500 text-black border-amber-400' : 'bg-white/5 text-gray-200 border-white/10 hover:bg-white/10'}`}
                  >
                    {label}
                  </button>
                );
              })}
            </div>
            <p className="text-xs text-gray-500 mt-1">每个选项显示实际像素尺寸，按最长边标准（1K=1024，2K=2048，4K=3840，8K=7680）</p>
          </div>

          <>
            <div>
              <label className="text-xs text-gray-300 mb-2 block">文件格式</label>
              <div className="flex gap-2">
                {(['jpeg','png','tiff'] as FormatKey[]).map(f => (
                  <button
                    key={f}
                    onClick={() => setFormat(f)}
                    className={`px-3 py-2 rounded-lg text-xs border transition-colors ${format===f ? 'bg-white text-black border-white' : 'bg-white/5 text-gray-200 border-white/10 hover:bg-white/10'}`}
                  >
                    {f.toUpperCase()}
                  </button>
                ))}
              </div>
              <p className="text-xs text-gray-500 mt-1">JPG：高兼容性 · PNG：无损 · TIFF：专业工作流</p>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-gray-300 mb-1 block">色彩模式</label>
                <select value={colorMode} onChange={(e)=>setColorMode(e.target.value as ColorMode)} className="w-full bg-[#181818] border border-white/10 rounded-xl text-sm text-gray-200 px-3 py-2">
                  <option value="RGB">RGB</option>
                  <option value="GRAY">GRAY</option>
                </select>
                <p className="text-xs text-gray-500 mt-1">RGB：通用显示 · 灰度：黑白作品/稿件</p>
              </div>
              {format !== 'png' && (
                <div>
                  <label className="text-xs text-gray-300 mb-1 block">质量 {quality}</label>
                  <input type="range" min={60} max={100} value={quality} onChange={(e)=>setQuality(parseInt(e.target.value))} className="w-full" />
                </div>
              )}
              {format === 'png' && (
                <div>
                  <label className="text-xs text-gray-300 mb-1 block">压缩 {compression}</label>
                  <input type="range" min={0} max={9} value={compression} onChange={(e)=>setCompression(parseInt(e.target.value))} className="w-full" />
                </div>
              )}
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-gray-300 mb-1 block">水印</label>
                <div className="flex items-center gap-2">
                  <input type="checkbox" checked={wmEnabled} onChange={(e)=>setWmEnabled(e.target.checked)} />
                  <input value={wmText} onChange={(e)=>setWmText(e.target.value)} placeholder="水印文本" className="flex-1 bg-[#181818] border border-white/10 rounded-xl text-sm text-gray-200 px-3 py-2" />
                </div>
                <div className="flex items-center gap-2 mt-2">
                  <select value={wmPos} onChange={(e)=>setWmPos(e.target.value as any)} className="bg-[#181818] border border-white/10 rounded-xl text-sm text-gray-200 px-3 py-2">
                    <option value="BR">右下</option>
                    <option value="TL">左上</option>
                  </select>
                  <input type="range" min={0} max={1} step={0.05} value={wmOpacity} onChange={(e)=>setWmOpacity(parseFloat(e.target.value))} className="flex-1" />
                  <input type="number" min={12} max={96} value={wmSize} onChange={(e)=>setWmSize(parseInt(e.target.value))} className="w-20 bg-[#181818] border border-white/10 rounded-xl text-sm text-gray-200 px-2 py-2" />
                </div>
                <p className="text-xs text-gray-500 mt-1">可选叠加水印，位置与透明度可控</p>
              </div>
              <div>
                <label className="text-xs text-gray-300 mb-1 block">EXIF/IPTC 字段清单</label>
                <div className="bg-white/5 border border-white/10 rounded-xl p-3 text-xs text-gray-300 space-y-2">
                  <div className="font-medium">EXIF</div>
                  <div>ImageDescription：{cameraInfo || '未填写'}</div>
                  <div>Artist：{(copyright.match(/©\s*\d{4}\s*(.+?)(?:\.|$)/) || [])[1] || '未填写'}</div>
                  <div>Copyright：{copyright || '未填写'}</div>
                  <div>Software：Lumima Retouch</div>
                  <div>DateTime：{new Date().toISOString()}</div>
                  <div className="font-medium mt-2">IPTC</div>
                  <div>ObjectName：Exported Image</div>
                  <div>Caption/Abstract：{cameraInfo || '未填写'}</div>
                  <div>Keywords：无</div>
                  <div>Byline：{(copyright.match(/©\s*\d{4}\s*(.+?)(?:\.|$)/) || [])[1] || '未填写'}</div>
                  <div>Credit：{(copyright.match(/©\s*\d{4}\s*(.+?)(?:\.|$)/) || [])[1] || '未填写'}</div>
                  <div>CopyrightNotice：{copyright || '未填写'}</div>
                  <div className="mt-2 text-gray-400">PNG/TIFF写入以上字段；JPEG显示依赖查看工具</div>
                </div>
              </div>
            </div>

            <div>
              <label className="text-xs text-gray-300 mb-1 block">版权声明</label>
              <input value={copyright} onChange={(e)=>setCopyright(e.target.value)} className="w-full bg-[#181818] border border-white/10 rounded-xl text-sm text-gray-200 px-3 py-2" />
              <label className="text-xs text-gray-300 mb-1 block mt-3">拍摄参数</label>
              <input value={cameraInfo} onChange={(e)=>setCameraInfo(e.target.value)} className="w-full bg-[#181818] border border-white/10 rounded-xl text-sm text-gray-200 px-3 py-2" />
              <p className="text-xs text-gray-500 mt-1">将作为元数据信息嵌入输出文件（兼容格式下）</p>
            </div>

            <div className="mt-2">
              <button
                disabled={!canDownload || isConverting}
                onClick={handleConfirm}
                className={`w-full py-3 rounded-xl font-medium flex items-center justify-center gap-2 border transition-colors ${canDownload ? 'bg-amber-500 text-black border-amber-400 hover:bg-amber-600' : 'bg-white/5 text-gray-300 border-white/10 cursor-not-allowed'}`}
              >
                {isConverting ? (
                  <span>正在生成...</span>
                ) : (
                  <>
                    <CheckCircleIcon className="w-5 h-5" /> 最终确认并生成
                  </>
                )}
              </button>
            </div>
          </>
        </div>
      </div>
    </div>
  );
};
