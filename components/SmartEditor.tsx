
import React, { useState, useEffect, useRef, useMemo } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  ArrowPathIcon,
  AdjustmentsHorizontalIcon,
  CpuChipIcon,
  CheckCircleIcon,
  ArrowsPointingOutIcon,
  SparklesIcon,
  ExclamationTriangleIcon,
  ArrowDownTrayIcon,
  CheckIcon,
  PaperAirplaneIcon,
  ArrowUpTrayIcon,
  PaintBrushIcon,
  XMarkIcon,
  ArrowUturnLeftIcon,
  ArrowUturnRightIcon
} from '@heroicons/react/24/outline';
import { ImageComparator } from './ImageComparator';
import { CanvasMaskEditor } from './CanvasMaskEditor';
import { DNALoader, BlinkingSmileIcon } from './DNALoader';
import { analyzeImage, editImage, urlToBlob, startSmartSession, answerSmartQuestion, generateSmartImage, SmartQuestion, SmartSession } from '../services/gemini';
import { PlanItem } from '../types';

const MagicWandIcon = SparklesIcon;

interface SmartEditorProps {
  imagePreview: string | null;
  imageFile: File | null;
  initialPrompt?: string;
  onReset: () => void;
  lang: 'zh' | 'en';
  startMode?: 'analyze' | 'direct';
  onGoToDownload?: (url: string | null) => void;
  onStatusChange?: (s: 'analyzing'|'ready'|'executing'|'completed') => void;
  onEditedResult?: (url: string) => void;
  initialStatusOverride?: 'completed' | 'ready';
  initialDisplayOverride?: string | null;
}

export const SmartEditor: React.FC<SmartEditorProps> = ({
  imagePreview,
  imageFile,
  initialPrompt = '',
  onReset,
  lang,
  startMode = 'analyze',
  onGoToDownload,
  onStatusChange,
  onEditedResult,
  initialStatusOverride,
  initialDisplayOverride,
}) => {
  const [status, setStatus] = useState<'analyzing' | 'ready' | 'executing' | 'completed'>('analyzing');
  const [planItems, setPlanItems] = useState<PlanItem[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [smartQuestions, setSmartQuestions] = useState<SmartQuestion[]>([]);
  const [smartAnswers, setSmartAnswers] = useState<Record<string, string>>({});
  const [smartSpec, setSmartSpec] = useState<any>(null);
  const [smartTemplate, setSmartTemplate] = useState<string | null>(null);
  const [isSmartFlow, setIsSmartFlow] = useState(false);
  const [userInput, setUserInput] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const [exportFormat, setExportFormat] = useState<'jpeg'|'png'|'webp'|'tiff'>('jpeg');
  const [exportQuality, setExportQuality] = useState(90);
  const [exportCompression, setExportCompression] = useState(6);
  const [isConverting, setIsConverting] = useState(false);
  const [convertProgress, setConvertProgress] = useState(0);
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null);
  const [currentActiveStepIndex, setCurrentActiveStepIndex] = useState(-1);
  const [showDownloadOptions, setShowDownloadOptions] = useState(false);
  
  // History Management
  const [imageHistory, setImageHistory] = useState<string[]>([]);
  const [historyIndex, setHistoryIndex] = useState(-1);

  // Masking State
  const [isMaskingMode, setIsMaskingMode] = useState(false);
  const [currentMaskBlob, setCurrentMaskBlob] = useState<Blob | null>(null);
  
  const listEndRef = useRef<HTMLDivElement>(null);
  const layoutRef = useRef<HTMLDivElement>(null);
  const [leftPct, setLeftPct] = useState(42);
  const [isPreviewCollapsed, setIsPreviewCollapsed] = useState(false);
  const [expandedMap, setExpandedMap] = useState<Record<string, boolean>>({});
  const toggleExpand = (id: string) => setExpandedMap(prev => ({ ...prev, [id]: !prev[id] }));
  const [isResizing, setIsResizing] = useState(false);
  const [summaryText, setSummaryText] = useState('');
  const rightPaneRef = useRef<HTMLDivElement>(null);
  const [isCompactHeader, setIsCompactHeader] = useState(false);
  const [isSummaryCollapsed, setIsSummaryCollapsed] = useState(false);

  // Translations
  const t = useMemo(() => ({
    en: {
        analyzing: 'Analyzing...',
        thinking: 'Identifying improvements...',
        confirm: 'Confirm Edits',
        processing: 'Processing Edits...',
        done: 'Done.',
        exporting: 'Exporting...',
        addCustom: 'Add custom requirement...',
        generate: 'Generate Magic Edit',
        crafting: 'Crafting your masterpiece...',
        manualTouchup: 'Manual Touch-up (Inpaint)',
        annotateGuide: 'Annotate image to guide the editor.',
        doneAddMore: 'Done! Add more edits below:',
        placeholderEdit: 'E.g., Make the sky bluer...',
        placeholderMask: 'Describe your annotation (Optional)...',
        maskTip: 'Use the toolbar on the image to draw and submit.',
        downloadResult: 'Download',
        format: 'Format',
        quality: 'Quality',
        compression: 'Compression',
        formatHelp: 'JPEG: small, photos · PNG: lossless · WEBP: high compression · TIFF: pro',
        smartAssistant: 'Smart Assistant',
        newUpload: 'New Upload',
        addBack: 'Add Back',
        noSuggestions: 'Analysis complete. Add custom edits below.',
        issue: 'Issue Detected',
        userRequest: 'User Request',
        processingStep: 'Processing...',
        optimizing: 'Optimizing Details...',
        applyingEdits: 'Applying Visual Edits...',
    },
    zh: {
        analyzing: '正在分析...',
        thinking: '正在识别优化点...',
        confirm: '确认编辑',
        processing: '正在处理编辑...',
        done: '完成',
        exporting: '正在导出...',
        addCustom: '添加自定义需求...',
        generate: '生成魔法编辑',
        crafting: '正在打造您的杰作...',
        manualTouchup: '手动修饰 (重绘)',
        annotateGuide: '标注图片以引导编辑。',
        doneAddMore: '完成！在下方添加更多编辑：',
        placeholderEdit: '例如：让天空更蓝...',
        placeholderMask: '描述您的标注（可选）...',
        maskTip: '使用图片上的工具栏进行绘制并提交。',
        downloadResult: '下载',
        format: '格式',
        quality: '质量',
        compression: '压缩',
        formatHelp: 'JPEG：体积小，适合照片 · PNG：无损 · WEBP：高压缩 · TIFF：专业无损',
        smartAssistant: '智能助手',
        newUpload: '重新上传',
        addBack: '加回',
        noSuggestions: '分析完成，请在下方添加自定义编辑。',
        issue: '发现问题',
        userRequest: '用户请求',
        processingStep: '处理中...',
        optimizing: '正在优化细节...',
        applyingEdits: '正在应用视觉编辑...',
    }
  }), []);
  const dict = t[lang];

  const getTemplateName = (id: string | null) => {
    if (!id) return '通用优化';
    const map: Record<string, string> = {
      'text_design': '文字/排版设计',
      'sticker_icon': '贴纸/图标生成',
      'product_shot': '电商/产品摄影',
      'landscape_enhance': '风景/自然增强',
      'photoreal_portrait': '写实人像写真',
      'negative_space': '极简/留白构图',
      'photo_retouch': '通用修图优化'
    };
    return map[id] || id;
  };

  // Initial Load & Analysis (Streaming)
  useEffect(() => {
    if (initialStatusOverride) return;
    let isMounted = true;
    const init = async () => {
      if (!imageFile) return;
      
      // Initialize history with original image
      if (imagePreview) {
          setImageHistory([imagePreview]);
          setHistoryIndex(0);
      }
      
      if (startMode === 'direct') {
        if (isMounted) setStatus('ready');
        await executeMagic(undefined, initialPrompt || '');
        return;
      }

      try {
        if (isMounted) setStatus('analyzing');
        
        // Use Smart Session for initial analysis
        const session = await startSmartSession(imageFile, initialPrompt || '');
        if (isMounted) {
          setSessionId(session.session_id);
          setIsSmartFlow(true);
          setSmartSpec(session.spec);
          if ((session as any).template_selected) {
            setSmartTemplate((session as any).template_selected);
          }
          
          if (session.plan_items && session.plan_items.length > 0) {
            setPlanItems(session.plan_items);
          }
          
          if (session.questions && session.questions.length > 0) {
            setSmartQuestions(session.questions);
            setStatus('ready');
          } else {
            setStatus('ready');
          }
        }
      } catch (e) {
        console.warn('Smart flow failed, falling back to old analysis.', e);
        // Fallback to old streaming analysis
        const s = await analyzeImage(imageFile, (newItem) => {
          if (isMounted) {
            setPlanItems(prev => {
              if (prev.find(p => p.id === newItem.id)) return prev;
              return [...prev, newItem];
            });
          }
        }, initialPrompt || '');
        if (isMounted) {
          setSummaryText(s || '');
          setStatus('ready');
        }
      }
    };
    init();

  return () => {
      isMounted = false;
    };
  }, [imageFile, startMode, initialStatusOverride]); 

  // Auto-scroll to bottom as items arrive
  useEffect(() => {
    if (listEndRef.current) {
      listEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [planItems.length, status]);

  useEffect(() => {
    if (onStatusChange) onStatusChange(status);
  }, [status, onStatusChange]);

  useEffect(() => {
    const el = rightPaneRef.current;
    if (!el) return;
    let ticking = false;
    const onScroll = () => {
      if (ticking) return;
      // During loading states, keep the header/summary stable (expanded) to prevent jitter
      if (status === 'analyzing' || status === 'executing') return;
      
      ticking = true;
      requestAnimationFrame(() => {
        const st = el.scrollTop;
        const collapsed = st > 4;
        setIsCompactHeader(collapsed);
        setIsSummaryCollapsed(collapsed);
        ticking = false;
      });
    };
    el.addEventListener('scroll', onScroll);
    return () => {
      el.removeEventListener('scroll', onScroll);
    };
  }, [status]);


  useEffect(() => {
    const clamp = (v: number, min: number, max: number) => Math.min(Math.max(v, min), max);
    const onMove = (e: MouseEvent | TouchEvent) => {
      if (!isResizing || !layoutRef.current) return;
      const rect = layoutRef.current.getBoundingClientRect();
      const clientX = 'touches' in e ? (e as TouchEvent).touches[0].clientX : (e as MouseEvent).clientX;
      const x = clientX - rect.left;
      const pct = clamp((x / rect.width) * 100, 28, 75);
      setLeftPct(pct);
    };
    const onUp = () => setIsResizing(false);
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    window.addEventListener('touchmove', onMove, { passive: false } as any);
    window.addEventListener('touchend', onUp);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
      window.removeEventListener('touchmove', onMove as any);
      window.removeEventListener('touchend', onUp);
    };
  }, [isResizing]);

  // --- History Helpers ---
  const addToHistory = (newImageUrl: string) => {
      const newHistory = imageHistory.slice(0, historyIndex + 1);
      newHistory.push(newImageUrl);
      setImageHistory(newHistory);
      setHistoryIndex(newHistory.length - 1);
      if (onEditedResult) onEditedResult(newImageUrl);
  };

  const handleUndo = () => {
      if (historyIndex > 0) {
          setHistoryIndex(prev => prev - 1);
      }
  };

  const handleRedo = () => {
      if (historyIndex < imageHistory.length - 1) {
          setHistoryIndex(prev => prev + 1);
      }
  };
  
  const currentDisplayImage = historyIndex >= 0 ? imageHistory[historyIndex] : imagePreview;

  useEffect(() => {
    if (initialStatusOverride) {
      setStatus(initialStatusOverride);
      if (initialDisplayOverride) {
        setImageHistory([initialDisplayOverride]);
        setHistoryIndex(0);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // --- Action Handlers ---

  const toggleItem = (id: string) => {
    setPlanItems((prev) => {
      const itemToToggle = prev.find((item) => item.id === id);
      if (!itemToToggle) return prev;

      // 如果是互斥方案 (isOption)
      if (itemToToggle.isOption) {
        return prev.map((item) => {
          if (item.id === id) {
            return { ...item, checked: true }; // 方案类点击总是选中
          }
          if (item.isOption) {
            return { ...item, checked: false }; // 其他方案取消选中
          }
          return item;
        });
      }

      // 常规修图建议 (Checkbox 逻辑)
      return prev.map((item) =>
        item.id === id ? { ...item, checked: !item.checked } : item
      );
    });
  };

  const handleFilterSelect = (itemId: string, option: string) => {
      setPlanItems(prev => prev.map(item => {
          if (item.id === itemId) {
              const label = lang === 'zh' ? `风格滤镜：${option}` : `Filter: ${option}`;
              return { ...item, selectedOption: option, checked: true, solution: label };
          }
          return item;
      }));
  };

  const handleSmartAnswer = async (questionId: string, answer: string) => {
    if (!sessionId) return;
    
    const newAnswers = { ...smartAnswers, [questionId]: answer };
    setSmartAnswers(newAnswers);
    
    // Clear the question that was just answered from the list for UI feedback
    setSmartQuestions(prev => prev.filter(q => q.id !== questionId));
    
    // If all questions in the current batch are answered, send to backend
    // Actually, we can send them one by one or wait. Let's send them all if no more questions in current batch.
    // However, the backend might return MORE questions.
    
    // For simplicity in UI, let's wait until all visible questions are answered
    const remainingCount = smartQuestions.length - 1;
    if (remainingCount === 0) {
      setIsProcessing(true);
      try {
        const session = await answerSmartQuestion(sessionId, newAnswers);
      setSmartSpec(session.spec);
      if ((session as any).template_selected) {
        setSmartTemplate((session as any).template_selected);
      }
      setSmartAnswers({}); // 清空已提交的答案，防止下次重复发送
        
        if (session.plan_items && session.plan_items.length > 0) {
          setPlanItems(session.plan_items);
        }

        if (session.questions && session.questions.length > 0) {
          setSmartQuestions(session.questions);
        } else {
          setSmartQuestions([]);
        }
      } catch (e) {
        setErrorMessage('提交回答失败，请重试');
      } finally {
        setIsProcessing(false);
      }
    }
  };

  const handleSmartGenerate = async () => {
    if (!sessionId) return;
    
    setErrorMessage(null);
    setStatus('executing');
    setIsProcessing(true);
    
    try {
      const result = await generateSmartImage(sessionId);
      if (result.urls && result.urls.length > 0) {
        addToHistory(result.urls[0]);
        setStatus('completed');
      } else {
        throw new Error('No URL returned');
      }
    } catch (e) {
      console.error(e);
      setErrorMessage('生成失败，请稍后重试');
      setStatus('ready');
    } finally {
      setIsProcessing(false);
    }
  };

  const handleUserSubmit = async () => {
    // In masking mode, validation happens in executeMaskedEdit
    if (isMaskingMode) {
        await executeMaskedEdit();
        return;
    }

    if (!userInput.trim()) return;

    const newStep: PlanItem = {
      id: `custom_${Date.now()}`,
      problem: dict.userRequest,
      solution: userInput,
      engine: 'Smart Engine',
      type: 'generative',
      checked: true,
      isCustom: true,
    };

    if (status === 'ready' || status === 'analyzing') {
      if (isSmartFlow && sessionId) {
        setIsProcessing(true);
        try {
          const session = await answerSmartQuestion(sessionId, {}, userInput);
          setSmartSpec(session.spec);
          if ((session as any).template_selected) {
            setSmartTemplate((session as any).template_selected);
          }
          if (session.plan_items && session.plan_items.length > 0) {
            setPlanItems(session.plan_items);
          }
          if (session.questions && session.questions.length > 0) {
            setSmartQuestions(session.questions);
          } else {
            setSmartQuestions([]);
          }
          setUserInput('');
        } catch (e) {
          setErrorMessage('同步指令失败，请重试');
        } finally {
          setIsProcessing(false);
        }
      } else {
        // Add to plan, execute all together later
        setPlanItems((prev) => [...prev, newStep]);
        setUserInput('');
      }
    } else if (status === 'completed') {
      // Iterative phase
      setPlanItems((prev) => [...prev, newStep]);
      setUserInput('');
      await executeMagic(undefined, newStep.solution); 
    }
  };

  const executeMagic = async (itemsOverride?: PlanItem[], specificInstruction?: string) => {
    // Determine Source Image
    let sourceBlob: Blob | null = null;
    let activeSteps: PlanItem[] = [];
    let instruction = "";

    if (status === 'completed' || specificInstruction) {
        if (!currentDisplayImage) return;
        sourceBlob = await urlToBlob(currentDisplayImage);
        activeSteps = []; 
        instruction = specificInstruction || "";
    } else {
        if (!imageFile) return;
        sourceBlob = imageFile;
        const currentItems = itemsOverride || planItems;
        activeSteps = currentItems.filter((item) => item.checked);
        instruction = ""; 
    }

    if (!sourceBlob) return;
    let sendName = 'image.png';
    try {
      const name = (imageFile?.name || '').toLowerCase();
      if (sourceBlob === imageFile && /\.(heic|heif)$/.test(name)) {
        const { convertHeicClientBlob } = await import('../services/gemini');
        sourceBlob = await convertHeicClientBlob(imageFile);
        sendName = 'image.jpg';
      } else if (/\.(jpg|jpeg)$/.test(name)) {
        sendName = imageFile?.name || 'image.jpg';
      } else if (/\.(png|webp)$/.test(name)) {
        sendName = 'image.png';
      } else if (/\.(dng|raw|arw|cr2|nef|raf|orf|rw2)$/.test(name)) {
        sendName = 'image.jpg';
      }
    } catch (e) {}

    setErrorMessage(null);
    setStatus('executing');
    setCurrentActiveStepIndex(0);
    setIsProcessing(true);

    const progressInterval = setInterval(() => {
        setCurrentActiveStepIndex(prev => {
            if (activeSteps.length > 0 && prev < activeSteps.length - 1) {
                return prev + 1;
            }
            return prev; 
        });
    }, 2000); 

    try {
        console.log('[executeMagic] Starting, sourceBlob:', sourceBlob, 'activeSteps:', activeSteps.length);
        const resultUrl = await editImage(sourceBlob, activeSteps, instruction, '1K', sendName, summaryText);
        console.log('[executeMagic] editImage returned URL:', resultUrl);
        
        clearInterval(progressInterval);
        
        if (resultUrl) {
            console.log('[executeMagic] Adding to history:', resultUrl);
            addToHistory(resultUrl);
            setErrorMessage(null);
        } else {
            console.warn('[executeMagic] resultUrl is null/undefined');
        }
        setStatus('completed');
        setCurrentActiveStepIndex(-1);
        console.log('[executeMagic] Success!');
    } catch (e) {
        console.error('[executeMagic] Error caught:', e);
        clearInterval(progressInterval);
        if (status === 'analyzing') setStatus('ready'); 
        else if (status !== 'completed') setStatus('ready');
        else setStatus('completed');
        
        setErrorMessage('生成失败,请稍后重试');
    } finally {
        setIsProcessing(false);
    }
  };
  
  const executeMaskedEdit = async () => {
      if (!currentMaskBlob || !currentDisplayImage) return;
      
      const prompt = userInput.trim() || "Apply edits based on visual annotations.";
      setErrorMessage(null);
      setIsProcessing(true);
      
      // Visual feedback: if we are in initial state, show 'executing' status
      const isInitial = status === 'ready' || status === 'analyzing';
      if (isInitial) setStatus('executing');

      try {
          const baseImageBlob = await urlToBlob(currentDisplayImage);
          
          // If this is the FIRST edit (from Ready state), we should include the selected Plan Items
          // because they haven't been applied yet.
          // If this is a SUBSEQUENT edit (from Completed state), the baseImage already has Plan Items applied,
          // so we don't apply them again.
          const activeSteps = isInitial ? planItems.filter(i => i.checked) : [];
          
          const maskStep: PlanItem = {
            id: `mask_${Date.now()}`,
            problem: 'Manual Annotation',
            solution: prompt,
            engine: 'Generative Fill',
            type: 'generative',
            checked: true,
            isCustom: true,
          };
          setPlanItems(prev => [...prev, maskStep]);
          
          const resultUrl = await editImage(baseImageBlob, activeSteps, prompt, '1K', 'image.png', summaryText, undefined, undefined, currentMaskBlob);
          
          if (resultUrl) {
              addToHistory(resultUrl);
              setIsMaskingMode(false);
              setCurrentMaskBlob(null);
              setUserInput('');
              setStatus('completed'); // Ensure we land in completed state
              setErrorMessage(null);
          }
      } catch (e) {
          console.error(e);
          setErrorMessage('遮罩编辑失败，请稍后重试');
          if (isInitial) setStatus('ready'); // Revert status if failed
      } finally {
        setIsProcessing(false);
      }
  };

  useEffect(() => {
    if (status === 'completed') {
      setErrorMessage(null);
    }
  }, [status]);

  const handleConvertAndDownload = async () => {
    if (!currentDisplayImage) return;
    try {
      setIsConverting(true);
      setConvertProgress(5);
      const timer = setInterval(() => {
        setConvertProgress((p) => Math.min(95, p + Math.floor(Math.random()*7+3)));
      }, 250);
      const blob = await urlToBlob(currentDisplayImage);
      const { convertImage } = await import('../services/gemini');
      const outBlob = await convertImage(blob, exportFormat, { quality: exportQuality, compression: exportCompression });
      clearInterval(timer);
      setConvertProgress(100);
      const url = URL.createObjectURL(outBlob);
      setDownloadUrl(url);
    } catch (e) {
      setErrorMessage('导出失败，请稍后重试');
    } finally {
      setIsConverting(false);
      setTimeout(() => setConvertProgress(0), 800);
    }
  };

  const startMasking = () => {
      setCurrentMaskBlob(null);
      setIsMaskingMode(true);
  };
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const getActiveIndex = (itemId: string) => {
    const activeSteps = planItems.filter((item) => item.checked);
    return activeSteps.findIndex((item) => item.id === itemId);
  };

  const filterItem = planItems.find(item => item.options && item.options.length > 0);

  const getFilterStyle = (name: string): React.CSSProperties => {
    const n = name.toLowerCase();
    const s: string[] = [];
    if (/exposure|brightness|亮度/.test(n)) s.push('brightness(1.15)');
    if (/contrast|对比/.test(n)) s.push('contrast(1.15)');
    if (/warm|温暖|tint/.test(n)) { s.push('sepia(0.2)'); s.push('saturate(1.1)'); s.push('hue-rotate(-8deg)'); }
    if (/cool|冷|blue|蓝/.test(n)) { s.push('saturate(0.95)'); s.push('hue-rotate(18deg)'); }
    if (/vibrance|saturation|饱和/.test(n)) s.push('saturate(1.4)');
    if (/blur|模糊|depth/.test(n)) s.push('blur(2px)');
    if (/bw|b&w|黑白|mono|monochrome|grayscale/.test(n)) s.push('grayscale(100%)');
    if (!s.length) return { filter: 'contrast(1.05) saturate(1.05)' };
    return { filter: s.join(' ') };
  };

  return (
    <div ref={layoutRef} className="bg-[#0b0b0c]" style={{ minHeight: '100vh', display: 'flex', flexDirection: 'row', alignItems: 'stretch', userSelect: isResizing ? 'none' : 'auto' }}>
      <div className="relative bg-zinc-900 flex items-center justify-center overflow-hidden" style={{ width: `${leftPct}%`, height: '100vh' }}>
        
        {/* --- Toolbar (Undo/Redo) --- */}
        {!isMaskingMode && status === 'completed' && (
            <div className="absolute top-6 left-6 z-30 flex gap-2">
                <button 
                    onClick={handleUndo} 
                    disabled={historyIndex <= 0}
                    className="p-3 bg-black/40 hover:bg-black/60 text-white rounded-full backdrop-blur-md disabled:opacity-30 transition-all shadow-lg border border-white/10"
                    title="Undo"
                >
                    <ArrowUturnLeftIcon className="w-5 h-5" />
                </button>
                <button 
                    onClick={handleRedo} 
                    disabled={historyIndex >= imageHistory.length - 1}
                    className="p-3 bg-black/40 hover:bg-black/60 text-white rounded-full backdrop-blur-md disabled:opacity-30 transition-all shadow-lg border border-white/10"
                    title="Redo"
                >
                    <ArrowUturnRightIcon className="w-5 h-5" />
                </button>
            </div>
        )}

        {/* --- Status Badge --- */}
        {!isMaskingMode && (
            <div className="absolute top-6 left-1/2 -translate-x-1/2 z-30 px-4 py-2 bg-black/40 backdrop-blur-md rounded-full text-white text-sm font-medium flex items-center gap-2 border border-white/10 shadow-lg pointer-events-none">
            {status === 'analyzing' && (
                <>
                <BlinkingSmileIcon className="w-4 h-4 text-amber-400" /> {dict.analyzing}
                </>
            )}
            {status === 'ready' && (
                <>
                <AdjustmentsHorizontalIcon className="w-4 h-4" /> 
                {planItems.some(it => it.isOption && it.checked) ? '请选择一个方案' : dict.confirm}
                </>
            )}
            {status === 'executing' && (
                <>
                <CpuChipIcon className="w-4 h-4 animate-pulse text-blue-400" /> {dict.processing}
                </>
            )}
            {status === 'completed' && !isConverting && (
                <>
                <CheckCircleIcon className="w-4 h-4 text-amber-400" /> {dict.done}
                </>
            )}
            {isConverting && (
                <>
                <CpuChipIcon className="w-4 h-4 animate-pulse text-blue-400" /> {dict.exporting}
                </>
            )}
            </div>
        )}

        {!isMaskingMode && downloadUrl && (
            <a
              href={downloadUrl}
              download={`export.${exportFormat==='jpeg'?'jpg':exportFormat}`}
              className="absolute top-6 right-6 z-30 px-3 py-2 bg-amber-500 hover:bg-amber-600 text-black rounded-full text-sm font-medium flex items-center gap-1 shadow-lg border border-amber-400"
            >
              <ArrowDownTrayIcon className="w-4 h-4" /> {dict.downloadResult}
            </a>
        )}

        {/* --- Main Viewport --- */}
        {isMaskingMode && currentDisplayImage ? (
            <CanvasMaskEditor 
                imageSrc={currentDisplayImage} 
                onMaskGenerated={(blob) => setCurrentMaskBlob(blob)}
                onCancel={() => {
                    setIsMaskingMode(false);
                    setCurrentMaskBlob(null);
                }}
                onSubmit={() => {
                    setTimeout(executeMaskedEdit, 50);
                }}
                lang={lang}
            />
        ) : (
            <ImageComparator
                originalImage={imagePreview}
                modifiedImage={currentDisplayImage}
                enableSlider={status === 'completed'}
            />
        )}

        {/* --- Filter Dock --- */}
        {!isMaskingMode && status === 'ready' && filterItem && (
          <div className="absolute bottom-6 left-0 right-0 flex justify-center z-30 px-4">
             <div className="flex gap-3 overflow-x-auto p-2 bg-black/40 backdrop-blur-xl rounded-2xl border border-white/10 max-w-full custom-scrollbar">
                {filterItem.options?.map((opt, idx) => (
                   <button
                     key={idx}
                     onClick={() => handleFilterSelect(filterItem.id, opt)}
                     className={`relative group flex-shrink-0 w-20 h-20 rounded-xl overflow-hidden border-2 transition-all ${filterItem.selectedOption === opt ? 'border-purple-500 scale-105' : 'border-transparent hover:border-white/50'}`}
                   >
                      <img src={imagePreview || ''} style={getFilterStyle(opt)} className="w-full h-full object-cover opacity-80 group-hover:opacity-100 transition-opacity" />
                      <div className="absolute inset-0 bg-gradient-to-t from-black/80 to-transparent flex items-end justify-center p-1">
                          <span className="text-[10px] font-medium text-white text-center leading-tight line-clamp-2">{opt}</span>
                      </div>
                   </button
                   >
                ))}
             </div>
          </div>
        )}

        {/* --- Analysis Scanner (Replaced with DNA) --- */}
        <AnimatePresence>
          {status === 'analyzing' && (
            <DNALoader scanning text={dict.analyzing} />
          )}
        </AnimatePresence>

        {/* --- Processing Overlay (DNALoader) --- */}
        <AnimatePresence>
          {(status === 'executing' || isConverting || (isProcessing && isMaskingMode)) && (
             <DNALoader 
                embedded 
                text={
                    isConverting 
                    ? dict.exporting 
                    : isMaskingMode 
                        ? dict.applyingEdits 
                        : dict.crafting
                } 
             />
          )}
        </AnimatePresence>
      </div>

      <div onMouseDown={() => setIsResizing(true)} onTouchStart={() => setIsResizing(true)} style={{ width: 10, cursor: 'col-resize', height: '100vh', background: 'transparent' }} />
      <div className="bg-[#121212] border-l border-white/10 flex flex-col shadow-2xl z-10 text-white" style={{ width: `${100 - leftPct}%`, height: '100vh' }}>
        <div className={`${isCompactHeader ? 'p-2' : 'p-6'} border-b border-white/10 flex-shrink-0 bg-black/30 transition-all duration-300`}>
          <div className="flex justify-between items-center">
            <h2 className={`${isCompactHeader ? 'text-base' : 'text-xl'} font-bold text-white flex items-center gap-2`}>
              <SparklesIcon className="w-5 h-5 text-purple-600" />
              {dict.smartAssistant}
            </h2>
            <div className="flex items-center gap-3">
              <button
                onClick={() => onGoToDownload?.(currentDisplayImage || imagePreview)}
                title={dict.downloadResult}
                disabled={status !== 'completed'}
                className={`p-2 rounded-full border shadow-sm ${status === 'completed' ? 'bg-amber-500 hover:bg-amber-600 text-black border-amber-400' : 'bg-white/10 text-gray-400 border-white/10 cursor-not-allowed'}`}
              >
                <ArrowDownTrayIcon className="w-4 h-4" />
              </button>
              <button
                onClick={() => {
                  const next = isPreviewCollapsed ? 42 : 24;
                  setLeftPct(next);
                  setIsPreviewCollapsed(!isPreviewCollapsed);
                }}
                className="text-xs px-3 py-1 rounded-full bg-white/10 hover:bg-white/20 text-gray-200 border border-white/10 transition-colors"
              >
                {isPreviewCollapsed ? '展开预览' : '收起预览'}
              </button>
              <button
                onClick={onReset}
                className="text-xs text-gray-300 hover:text-white underline"
              >
                {dict.newUpload}
              </button>
            </div>
          </div>
        </div>

        <div ref={rightPaneRef} className="flex-1 overflow-y-auto p-6 custom-scrollbar">
            {/* Smart Questions */}
            {isSmartFlow && smartQuestions.length > 0 && (
              <div className="mb-6 space-y-4">
                {smartQuestions.map((q) => (
                  <motion.div
                    key={q.id}
                    initial={{ opacity: 0, scale: 0.95 }}
                    animate={{ opacity: 1, scale: 1 }}
                    className="p-5 rounded-2xl bg-purple-600/10 border border-purple-500/30 shadow-lg"
                  >
                    <p className="text-sm font-bold text-purple-300 mb-3 flex items-center gap-2">
                      <SparklesIcon className="w-4 h-4" />
                      {q.text}
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {q.choices ? (
                        q.choices.map((choice) => (
                          <button
                            key={choice}
                            onClick={() => handleSmartAnswer(q.id, choice)}
                            disabled={isProcessing}
                            className="px-4 py-2 bg-purple-600 hover:bg-purple-500 text-white rounded-xl text-xs font-bold transition-all disabled:opacity-50"
                          >
                            {choice}
                          </button>
                        ))
                      ) : (
                        <div className="flex w-full gap-2">
                          <input
                            type="text"
                            placeholder="输入您的回答..."
                            className="flex-1 bg-black/40 border border-purple-500/30 rounded-xl px-4 py-2 text-sm outline-none focus:ring-1 focus:ring-purple-500"
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') {
                                handleSmartAnswer(q.id, (e.target as HTMLInputElement).value);
                                (e.target as HTMLInputElement).value = '';
                              }
                            }}
                          />
                        </div>
                      )}
                    </div>
                  </motion.div>
                ))}
              </div>
            )}

            {/* Smart Plan (Spec) */}
            {isSmartFlow && smartSpec && (
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                className="mb-6 p-5 rounded-2xl bg-amber-500/10 border border-amber-500/30 shadow-lg"
              >
                <div className="flex items-center gap-2 mb-3">
                  <SparklesIcon className="w-5 h-5 text-amber-400" />
                  <h3 className="text-sm font-bold text-amber-400 uppercase tracking-wider">AI 智能方案已就绪</h3>
                </div>
                <div className="space-y-3">
                  <div className="flex items-center justify-between text-xs">
                      <span className="text-gray-400">选用模板</span>
                      <span className="text-white font-mono bg-white/10 px-2 py-0.5 rounded">{getTemplateName(smartTemplate)}</span>
                    </div>
                  {smartSpec.params && Object.keys(smartSpec.params).length > 0 && (
                    <div className="pt-2 border-t border-white/5">
                      <p className="text-[10px] text-gray-500 uppercase mb-2">调整参数</p>
                      <div className="grid grid-cols-2 gap-2">
                        {Object.entries(smartSpec.params).map(([k, v]: [string, any]) => (
                          <div key={k} className="bg-black/20 rounded-lg p-2 flex flex-col">
                            <span className="text-[10px] text-gray-400 truncate">{k}</span>
                            <span className="text-xs text-amber-200 font-medium">{String(v)}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </motion.div>
            )}

            {/* Step List */}
            <div className="grid grid-cols-1 gap-4">
              <style>{`@keyframes shimmer { 0% { transform: translateX(-100%); } 100% { transform: translateX(100%); } }`}</style>
              <AnimatePresence>
                {planItems.map((item, index) => {
                  const activeIndex = getActiveIndex(item.id);
                  const isProcessingThis = status === 'executing' && activeIndex === currentActiveStepIndex;
                  const isDone = status === 'completed' || (status === 'executing' && activeIndex < currentActiveStepIndex);

                  if (!item.checked) {
                      return (
                          <div 
                              key={item.id} 
                              onClick={() => (status === 'ready' || status === 'analyzing') && toggleItem(item.id)}
                              className={`border border-white/10 bg-[#171717] rounded-2xl p-4 transition-all relative group cursor-pointer opacity-60 hover:opacity-100 hover:bg-[#1f1f1f] hover:shadow-sm`}
                          >
                              <div className="flex gap-3 items-center text-gray-400 group-hover:text-gray-600 transition-colors">
                                  <div className="flex-shrink-0"><ExclamationTriangleIcon className="w-5 h-5" /></div>
                                  <div className="flex-1"><p className="text-sm">{item.problem}</p></div>
                              </div>
                          </div>
                      )
                  }

                  return (
                    <motion.div
                      key={item.id}
                      initial={{ opacity: 0, y: 20 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ type: "spring", stiffness: 300, damping: 30 }}
                      className={`group relative overflow-hidden rounded-2xl border transition-all duration-300
                          ${
                            isProcessingThis
                              ? 'bg-purple-900/10 border-purple-500/30 shadow-[0_0_20px_rgba(168,85,247,0.1)]'
                              : isDone
                              ? 'bg-amber-900/10 border-amber-500/30'
                              : 'bg-[#1a1a1a] border-white/5 hover:border-white/10'
                          }
                      `}
                    >
                      {/* Header Section */}
                      <div className="px-4 py-3 flex items-center gap-2.5 border-b border-white/5 bg-white/[0.02]">
                          {item.isCustom || item.isOption ? (
                              <SparklesIcon className={`w-4 h-4 ${isDone ? 'text-amber-400' : 'text-purple-400'}`} />
                          ) : (
                              <ExclamationTriangleIcon className={`w-4 h-4 ${isDone ? 'text-amber-400' : 'text-amber-400'}`} />
                          )}
                          <span className={`text-xs font-bold tracking-wider uppercase ${isDone ? 'text-amber-400' : (item.isCustom || item.isOption ? 'text-purple-400' : 'text-amber-400')}`}>
                              {item.isCustom ? dict.userRequest : (item.category || dict.issue)}
                          </span>
                      </div>

                      {/* Body Section */}
                      <div className="p-4">
                          {/* Problem Description - 方案类条目隐藏此部分，因为标题已包含方案名 */}
                          {!item.isOption && (
                            <>
                              <p className={`text-sm text-gray-300 leading-relaxed font-light ${expandedMap[item.id] ? '' : 'line-clamp-2'} mb-2`}>
                                  {item.problem}
                              </p>
                              {(item.problem && item.problem.length > 28) && (
                                <button
                                  className="text-xs text-gray-400 hover:text-white underline"
                                  onClick={() => toggleExpand(item.id)}
                                >
                                  {expandedMap[item.id] ? '收起' : '展开更多'}
                                </button>
                              )}
                            </>
                          )}

                          {/* Solution Action Button */}
                          <div
                            onClick={() => (status === 'ready' || status === 'analyzing') && toggleItem(item.id)}
                            className={`
                                relative overflow-hidden flex items-center gap-3 p-3 rounded-xl cursor-pointer transition-all border
                                ${
                                  isDone
                                      ? 'bg-green-500/10 border-green-500/20'
                                      : isProcessingThis 
                                        ? 'bg-purple-500/10 border-purple-500/20'
                                        : item.checked
                                            ? 'bg-[#252525] border-white/10 hover:bg-[#2a2a2a] hover:border-purple-500/30 shadow-sm'
                                            : 'bg-[#1f1f1f] border-transparent opacity-70 hover:opacity-100'
                                }
                            `}
                          >
                            {/* Checkbox / Radio */}
                            <div
                              className={`w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0 transition-all
                                    ${
                                      isDone
                                        ? 'bg-amber-500 text-black scale-110'
                                        : item.checked
                                            ? 'bg-purple-600 text-white shadow-[0_0_10px_rgba(147,51,234,0.3)] scale-105'
                                            : 'border-2 border-gray-600 group-hover:border-gray-400'
                                    }
                                `}
                            >
                              {isProcessingThis ? (
                                <BlinkingSmileIcon className="w-3 h-3 text-purple-500" />
                              ) : (
                                (isDone || item.checked) ? (
                                    item.isOption ? (
                                        <div className="w-2 h-2 bg-white rounded-full" />
                                    ) : (
                                        <CheckIcon className="w-3 h-3" />
                                    )
                                ) : null
                              )}
                            </div>

                            {/* Solution Text */}
                            <div className="flex-1">
                              {item.isOption && (
                                <p className={`text-xs font-bold mb-1 ${item.checked ? 'text-purple-400' : 'text-gray-500'}`}>
                                  {item.problem}
                                </p>
                              )}
                              <p className={`text-sm font-medium transition-colors ${item.checked ? 'text-white' : 'text-gray-400'}`}>
                                {item.solution}
                              </p>
                              {isProcessingThis && (
                                <p className="text-xs text-purple-400 font-bold mt-1 animate-pulse">
                                  {dict.processingStep}
                                </p>
                              )}
                            </div>
                          </div>
                      </div>

                      {/* Shimmer Effect for Analyzing */}
                      {status === 'analyzing' && (
                        <div style={{ position:'absolute', inset:0, pointerEvents:'none', background:'linear-gradient(90deg, rgba(255,255,255,0), rgba(255,255,255,0.03), rgba(255,255,255,0))', transform:'translateX(-100%)', animation:'shimmer 2s infinite' }} />
                      )}
                    </motion.div>
                  );
                })}
              </AnimatePresence>

              {/* Streaming Loading Indicator */}
              {status === 'analyzing' && (
                  <motion.div 
                    initial={{ opacity: 0 }} 
                    animate={{ opacity: 1 }} 
                    className="flex items-center gap-3 p-4 rounded-xl border border-white/10 bg-[#181818]"
                  >
                      <BlinkingSmileIcon className="w-5 h-5 text-purple-400" />
                      <span className="text-sm text-gray-300 font-medium animate-pulse">{dict.thinking}</span>
                  </motion.div>
              )}
              
              <div ref={listEndRef} />
              
              {planItems.length === 0 && status === 'ready' && (
                <p className="text-center text-gray-400 text-sm py-4">
                  {dict.noSuggestions}
                </p>
              )}
            </div>
        </div>

        {errorMessage && (
          <div className="px-6 pt-4 bg-[#121212]">
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="p-3 rounded-lg bg-red-500/15 border border-red-500/30 text-red-200 flex items-center justify-between">
              <span className="text-sm">{errorMessage}</span>
              <button onClick={() => setErrorMessage(null)} className="px-2 py-1 text-xs rounded bg-red-500/20 hover:bg-red-500/30">关闭</button>
            </motion.div>
          </div>
        )}

        {summaryText !== undefined && (
          <div className={`px-6 border-t border-white/10 bg-[#121212] transition-all duration-300 ${isSummaryCollapsed ? 'py-0 max-h-0 overflow-hidden' : 'py-4'}`}>
            <div className="max-w-none">
              <h3 className="text-sm font-semibold text-white mb-2">总结</h3>
              {summaryText ? (
                <p className="text-sm text-gray-300 leading-relaxed">{summaryText}</p>
              ) : (
                <div className="h-16 rounded-lg bg-[#181818] border border-white/10" />
              )}
            </div>
          </div>
        )}

        <div className="p-4 border-t border-white/10 bg-[#121212] pb-8 z-20">
          {(status === 'ready' || status === 'analyzing' || status === 'executing') && (
            <div className="space-y-3">
              <div className="flex gap-2 items-center">
                  <div className="relative flex-1">
                    <input
                      type="text"
                      placeholder={dict.addCustom}
                      className="w-full pl-4 pr-12 py-3 bg-white/5 hover:bg-white/10 border border-white/10 rounded-xl text-sm text-gray-200 placeholder-gray-400 focus:ring-2 focus:ring-amber-500 outline-none transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                      value={userInput}
                      onChange={(e) => setUserInput(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && handleUserSubmit()}
                      disabled={status === 'executing'}
                    />
                    <button
                      onClick={handleUserSubmit}
                      disabled={status === 'executing'}
                      className="absolute right-2 top-1.5 p-1.5 bg-white/10 hover:bg-white/20 rounded-lg text-gray-200 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      <ArrowUpTrayIcon className="w-4 h-4 rotate-90" />
                    </button>
                  </div>
                   <button
                    onClick={startMasking}
                    disabled={status === 'executing'}
                    className="p-3 bg-[#1a1a1a] border border-white/10 rounded-xl text-gray-300 hover:text-purple-400 hover:border-purple-300 hover:shadow-md transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                    title={dict.annotateGuide}
                  >
                    <PaintBrushIcon className="w-5 h-5" />
                  </button>
                  <button
                    onClick={() => isSmartFlow ? handleSmartGenerate() : executeMagic()}
                    disabled={
                       status === 'analyzing' || status === 'executing' || isProcessing ||
                       (!isSmartFlow && planItems.filter((i) => i.checked).length === 0 && !userInput) ||
                       (isSmartFlow && smartQuestions.length > 0)
                    }
                    className="px-5 py-3 bg-gradient-to-r from-amber-400 to-purple-600 text-white rounded-xl font-bold text-base shadow-lg hover:shadow-xl hover:scale-[1.02] transition-all flex items-center justify-center gap-2 group disabled:opacity-50 disabled:cursor-not-allowed min-w-[140px]"
                  >
                    {status === 'analyzing' ? (
                         <>
                            <BlinkingSmileIcon className="w-5 h-5 text-amber-400" /> {dict.analyzing}
                         </>
                    ) : status === 'executing' ? (
                         <>
                            <CpuChipIcon className="w-5 h-5 animate-pulse text-white" /> {dict.crafting}
                         </>
                    ) : (
                        <>
                            <MagicWandIcon className="w-6 h-6 group-hover:rotate-12 transition-transform" />{' '}
                            {dict.generate}
                        </>
                    )}
                  </button>
              </div>
            </div>
          )}
          {status === 'completed' && (
            <div className="space-y-3">
              {/* Manual Touch-up Toggle */}
              {!isMaskingMode && (
                <button 
                  onClick={startMasking}
                  disabled={isProcessing}
                  className="w-full py-2 bg-[#1a1a1a] border border-white/10 text-gray-300 rounded-xl font-medium hover:text-purple-400 hover:border-purple-300 transition-all flex items-center justify-center gap-2 text-sm"
                >
                    <PaintBrushIcon className="w-4 h-4" /> {dict.manualTouchup}
                </button>
              )}
              
              <div className={`flex items-center gap-2 text-sm p-2 rounded-lg mb-2 transition-colors
                  ${isMaskingMode ? 'bg-purple-500/10 border border-purple-500/20' : 'bg-amber-500/10 border border-amber-500/20'}
              `}>
                {isMaskingMode ? (
                    <>
                        <PaintBrushIcon className="w-5 h-5 text-purple-400 animate-bounce" />
                        <span className="text-purple-300 font-bold">{dict.annotateGuide}</span>
                    </>
                ) : (
                    <>
                        <CheckCircleIcon className="w-5 h-5 text-amber-400" />
                        <span className="text-amber-300">{dict.doneAddMore}</span>
                    </>
                )}
              </div>
              
              {/* In Masking Mode, hide standard input to let user focus on canvas toolbar */}
              {!isMaskingMode ? (
                <div className="relative">
                    <input
                    type="text"
                    placeholder={dict.placeholderEdit}
                    disabled={isProcessing}
                    className="w-full pl-4 pr-12 py-3 bg-white/5 hover:bg-white/10 border border-white/10 rounded-xl text-sm text-gray-200 placeholder-gray-400 outline-none shadow-sm focus:ring-2 focus:ring-amber-500 transition-all"
                    value={userInput}
                    onChange={(e) => setUserInput(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleUserSubmit()}
                    />
                    <button
                    onClick={handleUserSubmit}
                    disabled={isProcessing}
                    className="absolute right-2 top-1.5 p-1.5 text-white rounded-lg transition-colors bg-amber-500 hover:bg-amber-600 disabled:opacity-50"
                    >
                    {isProcessing ? (
                        <BlinkingSmileIcon className="w-4 h-4 text-amber-400" />
                    ) : (
                        <PaperAirplaneIcon className="w-4 h-4" />
                    )}
                    </button>
                </div>
              ) : (
                 <div className="relative">
                    <input
                    type="text"
                    placeholder={dict.placeholderMask}
                    disabled={isProcessing}
                    className="w-full pl-4 pr-4 py-3 bg-purple-50 border border-purple-200 rounded-xl text-sm text-gray-900 placeholder-purple-400 outline-none shadow-sm focus:ring-2 focus:ring-purple-500 transition-all"
                    value={userInput}
                    onChange={(e) => setUserInput(e.target.value)}
                    />
                    <p className="text-xs text-purple-500 mt-1 ml-1">{dict.maskTip}</p>
                </div>
              )}

              <div className="flex flex-col gap-3 mt-2">
                {!isMaskingMode && (
                  <>
                    
                    {showDownloadOptions && (
                      <>
                        <div className="grid grid-cols-2 gap-3">
                          <div className="col-span-2">
                            <label className="text-xs text-gray-300 mb-1 block">{dict.format}</label>
                            <select value={exportFormat} onChange={(e)=>setExportFormat(e.target.value as any)} className="w-full bg-[#181818] border border-white/10 rounded-xl text-sm text-gray-200 px-3 py-2">
                              <option value="jpeg">JPEG</option>
                              <option value="png">PNG</option>
                              <option value="webp">WEBP</option>
                              <option value="tiff">TIFF</option>
                            </select>
                            <p className="text-xs text-gray-400 mt-1">{dict.formatHelp}</p>
                          </div>
                          {exportFormat !== 'png' && exportFormat !== 'tiff' && (
                            <div>
                              <label className="text-xs text-gray-300 mb-1 block">{dict.quality} {exportQuality}</label>
                              <input type="range" min={60} max={100} value={exportQuality} onChange={(e)=>setExportQuality(parseInt(e.target.value))} className="w-full" />
                            </div>
                          )}
                          {exportFormat === 'png' && (
                            <div>
                              <label className="text-xs text-gray-300 mb-1 block">{dict.compression} {exportCompression}</label>
                              <input type="range" min={0} max={9} value={exportCompression} onChange={(e)=>setExportCompression(parseInt(e.target.value))} className="w-full" />
                            </div>
                          )}
                        </div>
                        {isConverting && (
                          <div className="w-full h-2 rounded bg-white/10 overflow-hidden">
                            <div className="h-2 bg-blue-500" style={{ width: `${convertProgress}%` }} />
                          </div>
                        )}
                      </>
                    )}
                  </>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
