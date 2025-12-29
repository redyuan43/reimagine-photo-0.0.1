
import { AnalysisResponse, PlanItem } from "../types";

// --- API Configuration ---
// 使用当前主机名构建API地址，避免硬编码IP导致跨域
const getApiBaseUrl = () => {
  if (typeof window !== 'undefined') {
    return `http://${window.location.hostname}:8000`;
  }
  return 'http://localhost:8000';
};

// --- MOCK DATA ---

const MOCK_ITEMS: PlanItem[] = [
    {
      id: "1",
      problem: "Poor Lighting Detected",
      solution: "Adjust exposure and contrast",
      engine: "Adjustment",
      type: "adjustment",
      checked: true
    },
    {
      id: "2",
      problem: "Distracting Background",
      solution: "Remove clutter & blur depth",
      engine: "Generative",
      type: "generative",
      checked: true
    },
    {
      id: "3",
      problem: "Skin Tone Imbalance",
      solution: "Correct warmth & tint",
      engine: "Adjustment",
      type: "adjustment",
      checked: true
    },
    {
      id: "filter_opt",
      problem: "",
      solution: "Apply Artistic Filter",
      engine: "Filter",
      type: "adjustment",
      checked: false, // Default unchecked for filters
      options: [
        "Cinematic Warm",
        "Cool Breeze",
        "Vintage 90s",
        "Cyberpunk",
        "Soft Pastel",
        "B&W Noir"
      ]
    }
];

// --- API Key Management (Mocked) ---
export const checkAndRequestApiKey = async (): Promise<boolean> => {
  console.log("Mock: API Key check bypassed for UI dev");
  return true; 
};

// --- Helper (Unchanged) ---
export const urlToBlob = async (url: string): Promise<Blob> => {
  const isHttp = /^https?:\/\//i.test(url);
  const proxied = isHttp ? `${getApiBaseUrl()}/proxy_image?url=${encodeURIComponent(url)}` : url;
  const res = await fetch(proxied);
  return await res.blob();
};

// --- Analysis Service (Streaming Mock) ---
// Now accepts a callback to stream items one by one
export const analyzeImage = async (
  file: File,
  onPartialResult: (item: PlanItem) => void
): Promise<string | undefined> => {
  try {
    const fd = new FormData();
    fd.append('image', file);
    fd.append('prompt', '');
    const sse = await fetch(`${getApiBaseUrl()}/analyze_stream`, { method: 'POST', body: fd });
    if (sse.ok && sse.headers.get('content-type')?.includes('text/event-stream')) {
      const reader = sse.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let summary: string | undefined = undefined;
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split('\n\n');
        buffer = parts.pop() || '';
        for (const part of parts) {
          const line = part.trim();
          if (!line.startsWith('data:')) continue;
          try {
            const payload = JSON.parse(line.slice(5));
            if (payload.type === 'item' && payload.item) {
              onPartialResult(payload.item as PlanItem);
            } else if (payload.type === 'final') {
              summary = payload.summary as string | undefined;
            }
          } catch {}
        }
      }
      return summary;
    }
    const res = await fetch(`${getApiBaseUrl()}/analyze`, { method: 'POST', body: fd });
    if (res.ok) {
      const data = await res.json() as { analysis?: PlanItem[], summary?: string };
      const items = data.analysis || [];
      for (const it of items) {
        await new Promise(r => setTimeout(r, 150));
        onPartialResult(it);
      }
      return data.summary || undefined;
    }
  } catch (e) {
    console.warn('Backend analyze failed, falling back to mock.', e);
  }

  await new Promise(r => setTimeout(r, 800));
  for (const item of MOCK_ITEMS) {
    await new Promise(r => setTimeout(r, Math.random() * 800 + 400));
    onPartialResult({ ...item });
  }
  await new Promise(r => setTimeout(r, 500));
  return undefined;
};

// --- Editing Service (Mocked) ---
export const editImage = async (
  imageBlob: Blob,
  activeSteps: PlanItem[],
  userInstruction: string,
  resolution: '1K' | '2K' | '4K' = '1K',
  filename: string = "image.png",
  analysisSummary?: string,
  aspectRatio?: string, // 新增：比例参数
  stepIndex?: number    // 新增：步骤索引
): Promise<string | null> => {
  const sanitizeSummary = (txt?: string): string => {
    const s = (txt || '').trim();
    if (!s) return '';
    const pat = /(建议|推荐|滤镜|建议效果|风格化推荐)/;
    const parts = s.split(/(?<=[。！？!?;；\n])/);
    return parts.filter(p => !pat.test(p)).join('').trim();
  };
  const getImageSize = (blob: Blob): Promise<{ w: number; h: number }> => new Promise((resolve) => {
    const url = URL.createObjectURL(blob);
    const img = new Image();
    img.onload = () => {
      const w = img.naturalWidth || img.width;
      const h = img.naturalHeight || img.height;
      URL.revokeObjectURL(url);
      resolve({ w, h });
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      resolve({ w: 1024, h: 1024 });
    };
    img.src = url;
  });

  try {
    const fd = new FormData();
    console.log('Uploading image blob size:', (imageBlob as any)?.size ?? 'unknown');
    fd.append('image', imageBlob, filename);

    const typeWeight = (t?: string) => {
      const v = (t || '').toLowerCase();
      if (v === 'generative') return 300;
      if (v === 'adjustment') return 200;
      return 100;
    };
    const categoryWeight = (c?: string) => {
      const v = (c || '').toLowerCase();
      if (v.includes('构图') || v.includes('composition')) return 280;
      if (v.includes('光线') || v.includes('色彩') || v.includes('light') || v.includes('color')) return 240;
      if (v.includes('细节') || v.includes('detail')) return 200;
      if (v.includes('风格') || v.includes('滤镜') || v.includes('style') || v.includes('filter')) return 120;
      return 160;
    };
    const enginePenalty = (e?: string, p?: string, s?: string, c?: string) => {
      const ev = (e || '').toLowerCase();
      const txt = `${p || ''} ${s || ''} ${c || ''}`.toLowerCase();
      if (ev.includes('filter') || txt.includes('滤镜') || txt.includes('filter') || txt.includes('风格')) return -80;
      return 0;
    };
    const prioWeight = (p?: 'high'|'medium'|'low') => p === 'high' ? 900 : p === 'medium' ? 600 : p === 'low' ? 300 : 0;

    const decorated = (activeSteps || []).map((s, idx) => {
      const pw = prioWeight(s.priority);
      const tw = typeWeight(s.type);
      const cw = categoryWeight(s.category);
      const ep = enginePenalty(s.engine, s.problem, s.solution, s.category);
      const w = pw || (tw + cw + ep);
      return { idx, w, s };
    });
    decorated.sort((a, b) => {
      if (b.w !== a.w) return b.w - a.w;
      const ah = (a.s.priority || '').toLowerCase() === 'high';
      const bh = (b.s.priority || '').toLowerCase() === 'high';
      if (ah && bh) {
        const ac = (a.s.category || '').toLowerCase();
        const bc = (b.s.category || '').toLowerCase();
        const aIsComp = ac.includes('构图') || ac.includes('composition');
        const bIsComp = bc.includes('构图') || bc.includes('composition');
        if (aIsComp && !bIsComp) return -1;
        if (!aIsComp && bIsComp) return 1;
      }
      return a.idx - b.idx;
    });

    const lines: string[] = [];
    for (const d of decorated) {
      const problem = d.s.problem?.trim();
      const solution = d.s.solution?.trim();
      const line = [problem, solution].filter(Boolean).join(': ');
      if (line) lines.push(`- ${line}`);
    }
    const combinedSteps = lines.join('\n');
    const cleanSummary = sanitizeSummary(analysisSummary);
    const context = cleanSummary ? `\n[Image Context & Style]\n${cleanSummary}` : "";
    const finalPrompt = [userInstruction?.trim(), combinedSteps, context].filter(Boolean).join('\n');
    console.log("Qwen Image Edit Prompt:", finalPrompt);
    fd.append('prompt', finalPrompt);

    fd.append('n', '1');
    const { w, h } = await getImageSize(imageBlob);
    fd.append('size', `${w}*${h}`);
    fd.append('watermark', 'false');
    fd.append('prompt_extend', 'true');
    
    // 新增：向后端传递分辨率、比例和步骤
    fd.append('resolution', resolution);
    if (aspectRatio) fd.append('aspect_ratio', aspectRatio);
    if (stepIndex !== undefined) fd.append('step', stepIndex.toString());

    const res = await fetch(`${getApiBaseUrl()}/magic_edit`, { method: 'POST', body: fd });
    console.log('magic_edit response status:', res.status, res.ok);
    if (res.ok) {
      const data = await res.json() as { urls?: string[] };
      console.log('magic_edit response data:', data);
      const url = (data.urls && data.urls[0]) || null;
      console.log('Extracted URL:', url);
      if (!url) {
        console.error('No URL found in response, data:', data);
        throw new Error('No URLs returned');
      }
      console.log('Returning URL:', url);
      return url;
    }
    const txt = await res.text();
    console.error('magic_edit failed, status:', res.status, 'response:', txt);
    throw new Error(`magic_edit failed ${res.status}: ${txt}`);
  } catch (e) {
    throw e;
  }
};

export const getPreviewForUpload = async (file: File): Promise<string> => {
  const fd = new FormData();
  fd.append('image', file);
  const res = await fetch(`${getApiBaseUrl()}/preview`, { method: 'POST', body: fd });
  if (!res.ok) {
    const txt = await res.text().catch(() => '');
    throw new Error(txt || `preview failed ${res.status}`);
  }
  const blob = await res.blob();
  return URL.createObjectURL(blob);
};

export const convertHeicClient = async (file: File): Promise<string> => {
  try {
    const heic2any = (await import('heic2any')).default as any;
    const outputBlob = await heic2any({
      blob: file,
      toType: 'image/jpeg',
      quality: 0.9,
    });
    return URL.createObjectURL(outputBlob);
  } catch (e) {
    throw e;
  }
};

export const convertHeicClientBlob = async (file: File): Promise<Blob> => {
  const heic2any = (await import('heic2any')).default as any;
  const outputBlob = await heic2any({ blob: file, toType: 'image/jpeg', quality: 0.9 });
  return outputBlob as Blob;
};

export const convertImage = async (
  imageBlob: Blob,
  format: 'jpeg' | 'png' | 'webp' | 'tiff',
  opts: { quality?: number; compression?: number }
): Promise<Blob> => {
  const fd = new FormData();
  fd.append('image', imageBlob, 'export.bin');
  fd.append('format', format);
  if (typeof opts.quality === 'number') fd.append('quality', String(opts.quality));
  if (typeof opts.compression === 'number') fd.append('compression', String(opts.compression));
  const res = await fetch(`${getApiBaseUrl()}/convert`, { method: 'POST', body: fd });
  if (!res.ok) throw new Error(await res.text());
  return await res.blob();
};
