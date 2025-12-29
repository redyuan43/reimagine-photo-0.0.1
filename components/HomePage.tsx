
import React, { useRef, useState, useMemo, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { BlinkingSmileIcon } from './DNALoader';
import { PhotoIcon, PaperAirplaneIcon, ArrowUpTrayIcon, HandThumbUpIcon, StarIcon, BoltIcon, FaceSmileIcon } from '@heroicons/react/24/outline';
import * as THREE from 'three';

interface HomePageProps {
  onStart: (file: File, prompt: string, mode?: 'analyze' | 'direct') => void;
  lang: 'zh' | 'en';
  setLang: (lang: 'zh' | 'en') => void;
}

// --- CONSTANTS ---
const COLOR_NIGHT = '#050505';
const COLOR_DAY = '#87CEEB';

export const HomePage: React.FC<HomePageProps> = ({ onStart, lang, setLang }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const transitionLayerRef = useRef<HTMLDivElement>(null);
  const themeBtnRef = useRef<HTMLButtonElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const generateBtnRef = useRef<HTMLButtonElement>(null);
  const bhContainerRef = useRef<HTMLDivElement>(null);

  // --- STATE ---
  const [isNight, setIsNight] = useState(true);
  const isNightRef = useRef(true); // Ref for animation loop access
  const [promptText, setPromptText] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [filePreview, setFilePreview] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const dragCounter = useRef(0);

  // --- TRANSLATION ---
  const t = useMemo(() => ({
    en: {
      badge: 'LUMINA',
      h1a: 'Redefine Reality',
      h1b: 'Pixel by Pixel',
      sub: 'Harnessing next-gen neural networks to deliver professional studio quality.\nCrystal clear upscaling. Intelligent relighting. Instant mastery.',
      dragTip: 'Drop to Edit',
      describePlaceholder: 'Describe your edits (e.g. "Smooth skin and brighten")',
      example: 'Try',
      examplePrompt: 'Auto fix lighting and smooth skin texture',
      supports: 'Supports JPG, PNG, WEBP, RAW',
      features: [
        { title: 'No Skills Needed', desc: 'No professional Photoshop skills needed' },
        { title: 'Intuitive', desc: 'Intuitive operation is enough' },
        { title: 'Pro Quality', desc: 'Get professional quality results' }
      ]
    },
    zh: {
      badge: 'LUMINA 灵光',
      h1a: '重塑影像',
      h1b: '仅需一瞬',
      sub: '搭载下一代视觉大模型，为照片注入专业级光影与细节。\n4K超清重绘 · 智能光影重塑 · 毫秒级即时响应',
      dragTip: '松开开始编辑',
      describePlaceholder: '描述修图需求 (如：磨皮并提亮画面)...',
      example: '试一试',
      examplePrompt: '自动优化光影，进行人像磨皮美白',
      supports: '支持 JPG、PNG、WEBP、RAW',
      features: [
        { title: '无需技能', desc: '无需专业 Photoshop 技能' },
        { title: '直观操作', desc: '直观操作即可' },
        { title: '专业质感', desc: '获得专业级质感' }
      ]
    },
  }), []);
  const dict = t[lang];

  // --- CANVAS ENGINE ---
  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext('2d');
    if (!canvas || !ctx) return;

    let width = window.innerWidth;
    let height = window.innerHeight;
    
    let animationFrameId: number;
    
    // Mouse State
    let mouse = { x: -1000, y: -1000, vx: 0, vy: 0 };
    let lastMouse = { x: -1000, y: -1000 };

    // Entities
    let backgroundObjects: any[] = [];
    let flyingObjects: any[] = [];
    let particles: any[] = [];
    let colliders: Array<{ left: number; top: number; right: number; bottom: number }> = [];
    
    // Track previous theme to detect switch instantly in loop
    let lastIsNight = isNightRef.current;

    // --- CLASSES ---

    class BgObject {
        x: number = 0;
        y: number = 0;
        size: number = 0;
        baseSize: number = 0;
        maxOpacity: number = 0;
        opacity: number = 0;
        twinkleSpeed: number = 0;
        color: string = '255, 255, 255';
        glow: number = 0;
        pulsePhase: number = 0;

        constructor() {
            this.reset();
        }
        reset() {
            this.x = Math.random() * width;
            this.y = Math.random() * height;
            if (isNightRef.current) {
                this.size = Math.random() * 1.5;
                this.baseSize = this.size; 
                this.maxOpacity = Math.random() * 0.8 + 0.2; 
                this.opacity = this.maxOpacity;
                this.twinkleSpeed = Math.random() * 0.02 + 0.005;
                this.color = '255, 255, 255';
                this.glow = 0; 
                this.pulsePhase = Math.random() * Math.PI * 2;
            }
        }
        draw(ctx: CanvasRenderingContext2D) {
            if (isNightRef.current) {
                const dx = this.x - mouse.x;
                const dy = this.y - mouse.y;
                const dist = Math.sqrt(dx*dx + dy*dy);
                const triggerRange = 20; 
                
                if (dist < triggerRange) {
                    const speed = Math.sqrt(mouse.vx * mouse.vx + mouse.vy * mouse.vy);
                    const force = Math.min(speed * 0.2, 1.0) * (1 - dist / triggerRange);
                    this.glow += force * 0.8; 
                }
                if (this.glow > 1) this.glow = 1;
                if (this.glow > 0) {
                    this.glow -= 0.02;
                    if (this.glow < 0) this.glow = 0;
                }

                this.opacity += this.twinkleSpeed;
                if (this.opacity > 1 || this.opacity < 0.2) this.twinkleSpeed = -this.twinkleSpeed;

                let pulse = 1;
                if (this.glow > 0) {
                    pulse = 1 + Math.sin(Date.now() * 0.02 + this.pulsePhase) * 0.2 * this.glow;
                }

                const finalOpacity = Math.min(1, (this.opacity + this.glow * 1.8) * pulse); 
                const currentSize = (this.baseSize + (this.glow * 3.0)) * pulse;

                ctx.fillStyle = `rgba(${this.color}, ${finalOpacity})`;
                ctx.beginPath();
                ctx.arc(this.x, this.y, currentSize, 0, Math.PI * 2);
                ctx.fill();
            }
        }
    }

    class Flyer {
        mode: 'meteor' | 'sakura';
        x: number = 0; y: number = 0;
        vx: number = 0; vy: number = 0;
        len: number = 0; speed: number = 0; size: number = 0; angle: number = 0;
        life: number = 0; maxLife: number = 0;
        speedY: number = 0; speedX: number = 0; sway: number = 0; swayAmp: number = 0;
        rotation: number = 0; rotationSpeed: number = 0; flip: number = 0; flipSpeed: number = 0;
        color: string = ''; windVx: number = 0; windVy: number = 0;

        constructor() {
            this.mode = isNightRef.current ? 'meteor' : 'sakura';
            this.reset();
        }

        reset() {
            if (this.mode === 'meteor') {
                if (Math.random() < 0.5) {
                    this.x = Math.random() * width * 1.5 - width * 0.2; 
                    this.y = -150; 
                } else {
                    this.x = width + 150; 
                    this.y = Math.random() * height * 0.8; 
                }
                this.len = Math.random() * 80 + 200;
                this.speed = Math.random() * 4 + 8;
                this.size = Math.random() * 1 + 0.5;
                const angleBase = Math.PI * 0.75; 
                this.angle = angleBase + (Math.random() - 0.5) * 0.3;
                this.vx = Math.cos(this.angle) * this.speed;
                this.vy = Math.sin(this.angle) * this.speed;
                this.life = 0;
                this.maxLife = Math.random() * 50 + 80;
            } else {
                this.x = Math.random() * width;
                this.y = -30; 
                this.size = Math.random() * 5 + 4; 
                this.speedY = Math.random() * 0.7 + 0.8; 
                this.speedX = Math.random() * 0.2 - 0.1; 
                this.sway = Math.random() * 0.005 + 0.002; 
                this.swayAmp = Math.random() * 1.0 + 0.5; 
                this.rotation = Math.random() * Math.PI * 2;
                this.rotationSpeed = (Math.random() - 0.5) * 0.008; 
                this.flip = Math.random() * Math.PI; 
                this.flipSpeed = Math.random() * 0.008 + 0.002; 

                const red = 255;
                const green = Math.floor(Math.random() * 50 + 180); 
                const blue = Math.floor(Math.random() * 50 + 190);  
                this.color = `rgba(${red}, ${green}, ${blue}, ${Math.random() * 0.4 + 0.6})`;
                this.windVx = 0;
                this.windVy = 0;
            }
        }

        update() {
            if (this.mode === 'meteor') {
                this.x += this.vx;
                this.y += this.vy;
                this.life++;
            } else {
                const dx = this.x - mouse.x;
                const dy = this.y - mouse.y;
                const dist = Math.sqrt(dx*dx + dy*dy);
                const influenceRadius = 150;

                if (dist < influenceRadius) {
                    const force = (influenceRadius - dist) / influenceRadius;
                    this.windVx += mouse.vx * force * 0.05;
                    this.windVy += mouse.vy * force * 0.05;
                }

                this.windVx *= 0.95;
                this.windVy *= 0.95;

                this.y += this.speedY + this.windVy; 
                this.x += this.speedX + Math.sin(this.y * this.sway) * this.swayAmp + this.windVx; 
                this.rotation += this.rotationSpeed;
                this.flip += this.flipSpeed;
            }
        }

        checkStatus() {
            if (this.mode === 'meteor') {
                const hitEdge = this.y >= height || this.x <= 0;
                const burnedOut = this.life >= this.maxLife;
                for (let i = 0; i < colliders.length; i++) {
                    const c = colliders[i];
                    if (this.x >= c.left && this.x <= c.right && this.y >= c.top && this.y <= c.bottom) {
                        createParticles(this.x, this.y, 'spark');
                        return true;
                    }
                }
                if (hitEdge) {
                    let exX = this.x; 
                    let exY = this.y;
                    if (this.y >= height) exY = height - 5;
                    if (this.x <= 0) exX = 5;
                    if ((exX > -50 && exX < width + 50 && exY > -50 && exY < height + 50)) {
                        createParticles(exX, exY, 'spark');
                    }
                    return true; 
                }
                if (burnedOut) return true;
                if (this.x < -this.len || this.y > height + this.len) return true;
            } else {
                const hitBottom = this.y >= height;
                const hitLeft = this.x <= 0 && this.y > 0;
                const hitRight = this.x >= width && this.y > 0;
                if (hitBottom || hitLeft || hitRight) {
                    let exX = Math.max(0, Math.min(width, this.x));
                    let exY = Math.max(0, Math.min(height, this.y));
                    createParticles(exX, exY, 'pollen');
                    return true;
                }
            }
            return false;
        }

        draw(ctx: CanvasRenderingContext2D) {
            if (this.mode === 'meteor') {
                const opacity = Math.sin((Math.min(this.life, this.maxLife) / this.maxLife) * Math.PI);
                ctx.save();
                ctx.translate(this.x, this.y);
                ctx.rotate(Math.atan2(this.vy, this.vx) - Math.PI);
                const gradient = ctx.createLinearGradient(0, 0, this.len, 0);
                gradient.addColorStop(0, `rgba(255, 255, 255, ${opacity})`);
                gradient.addColorStop(0.1, `rgba(255, 255, 255, ${opacity * 0.8})`);
                gradient.addColorStop(1, 'rgba(255, 255, 255, 0)');
                ctx.fillStyle = gradient;
                ctx.beginPath();
                ctx.moveTo(0, 0);
                ctx.lineTo(this.len, -1);
                ctx.lineTo(this.len, 1);
                ctx.closePath();
                ctx.fill();
                ctx.restore();
            } else {
                const flipScale = Math.abs(Math.cos(this.flip));
                ctx.save();
                ctx.translate(this.x, this.y);
                ctx.rotate(this.rotation);
                ctx.scale(flipScale, 1); 
                ctx.fillStyle = this.color;
                ctx.beginPath();
                const s = this.size;
                ctx.moveTo(0, s * 0.8); 
                ctx.bezierCurveTo(-s * 0.6, s * 0.5, -s, 0, 0, -s);
                ctx.bezierCurveTo(s, 0, s * 0.6, s * 0.5, 0, s * 0.8);
                ctx.fill();
                ctx.restore();
            }
        }
    }

    class Particle {
        x: number; y: number; type: string;
        vx: number; vy: number; life: number; decay: number; gravity: number;
        color: string; size: number;

        constructor(x: number, y: number, type: string) {
            this.x = x; this.y = y; this.type = type;
            const angle = Math.random() * Math.PI * 2;
            if (type === 'spark') {
                const speed = Math.random() * 4 + 2;
                this.vx = Math.cos(angle) * speed;
                this.vy = Math.sin(angle) * speed;
                this.life = 1.0;
                this.decay = Math.random() * 0.02 + 0.015;
                this.gravity = 0.08;
                const colors = ['#FFD700', '#FFA500', '#FFFFE0', '#B8860B'];
                this.color = colors[Math.floor(Math.random() * colors.length)];
                this.size = Math.random() * 2 + 1;
            } else {
                const speed = Math.random() * 3.5 + 1.0; 
                this.vx = Math.cos(angle) * speed;
                this.vy = Math.sin(angle) * speed - 2; 
                this.life = 1.0;
                this.decay = Math.random() * 0.015 + 0.005; 
                this.gravity = 0.1; 
                if (Math.random() < 0.3) {
                    this.color = 'rgba(255, 255, 255, 0.9)'; 
                } else {
                    this.color = `rgba(255, ${Math.floor(Math.random()*50 + 180)}, 220, 1)`; 
                }
                this.size = Math.random() * 2.5 + 1.0; 
            }
        }
        update() {
            this.x += this.vx;
            this.y += this.vy;
            this.vy += this.gravity;
            this.vx *= 0.95; 
            this.vy *= 0.95;
            this.life -= this.decay;
        }
        draw(ctx: CanvasRenderingContext2D) {
            ctx.globalAlpha = Math.max(0, this.life);
            ctx.fillStyle = this.color;
            ctx.beginPath();
            ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
            ctx.fill();
            ctx.globalAlpha = 1.0;
        }
    }

    // --- LOGIC ---
    const createParticles = (x: number, y: number, type: string) => {
        const count = type === 'spark' ? 40 : 50;
        for (let i = 0; i < count; i++) {
            particles.push(new Particle(x, y, type));
        }
    };

    const createBackground = () => {
        backgroundObjects = [];
        if (!isNightRef.current) return;
        const count = Math.floor((width * height) / 3000);
        for (let i = 0; i < count; i++) {
            backgroundObjects.push(new BgObject());
        }
    };

    const updateColliders = () => {
        const rects: Array<{ left: number; top: number; right: number; bottom: number }> = [];
        if (titleRef.current) {
            const r = titleRef.current.getBoundingClientRect();
            rects.push({ left: r.left, top: r.top, right: r.right, bottom: r.bottom });
        }
        if (generateBtnRef.current) {
            const r = generateBtnRef.current.getBoundingClientRect();
            rects.push({ left: r.left, top: r.top, right: r.right, bottom: r.bottom });
        }
        document.querySelectorAll('[data-collider="true"]').forEach((el) => {
            const r = (el as HTMLElement).getBoundingClientRect();
            rects.push({ left: r.left, top: r.top, right: r.right, bottom: r.bottom });
        });
        colliders = rects;
    };

    const resize = () => {
        width = window.innerWidth;
        height = window.innerHeight;
        canvas.width = width;
        canvas.height = height;
        createBackground();
        updateColliders();
    };

    const animate = () => {
        ctx.clearRect(0, 0, width, height);

        // --- THEME SWITCH CLEANUP ---
        // If theme changed since last frame, clear everything instantly to prevent artifacts
        if (isNightRef.current !== lastIsNight) {
            flyingObjects = [];
            particles = [];
            backgroundObjects = [];
            // Regenerate background immediately if switching to night
            if (isNightRef.current) createBackground();
            lastIsNight = isNightRef.current;
        }
        // ----------------------------

        const gradient = ctx.createRadialGradient(width/2, height, 0, width/2, height/2, width);
        if (isNightRef.current) {
            gradient.addColorStop(0, 'rgba(27, 39, 53, 0.4)'); 
            gradient.addColorStop(1, 'rgba(0, 0, 0, 0)'); 
        } else {
            gradient.addColorStop(0, 'rgba(255, 255, 255, 0.4)'); 
            gradient.addColorStop(1, 'rgba(255, 255, 255, 0)');
        }
        ctx.fillStyle = gradient;
        ctx.fillRect(0, 0, width, height);

        backgroundObjects.forEach(obj => obj.draw(ctx));

        // Spawn Rate
        const spawnRate = isNightRef.current ? 0.0288 : 0.032; 
        if (Math.random() < spawnRate) {
            flyingObjects.push(new Flyer());
        }

        for (let i = flyingObjects.length - 1; i >= 0; i--) {
            const obj = flyingObjects[i];
            // Remove objects that don't belong to current theme
            // Sakura in Night OR Meteor in Day
            if ((isNightRef.current && obj.mode === 'sakura') || (!isNightRef.current && obj.mode === 'meteor')) {
                flyingObjects.splice(i, 1);
                continue;
            }

            obj.update();
            obj.draw(ctx);
            if (obj.checkStatus()) {
                flyingObjects.splice(i, 1);
            }
        }

        for (let i = particles.length - 1; i >= 0; i--) {
            // Remove particles incompatible with current theme
            // Spark in Day OR Pollen in Night
            if ((isNightRef.current && particles[i].type !== 'spark') || (!isNightRef.current && particles[i].type === 'spark')) {
                particles.splice(i, 1);
                continue;
            }

            particles[i].update();
            particles[i].draw(ctx);
            if (particles[i].life <= 0) {
                particles.splice(i, 1);
            }
        }
        
        mouse.vx *= 0.8;
        mouse.vy *= 0.8;

        animationFrameId = requestAnimationFrame(animate);
    };

    // --- INIT ---
    resize();
    animate();

    // Events
    const handleMouseMove = (e: MouseEvent) => {
        const currentX = e.clientX;
        const currentY = e.clientY;
        if (lastMouse.x !== -1000) {
            mouse.vx = currentX - lastMouse.x;
            mouse.vy = currentY - lastMouse.y;
        }
        mouse.x = currentX;
        mouse.y = currentY;
        lastMouse.x = currentX;
        lastMouse.y = currentY;
    };

    const handleWindowResize = () => resize();

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('resize', handleWindowResize);
    
    // Global particle trigger hack for clicks outside button
    const handleClick = (e: MouseEvent) => {
         if (!(e.target as HTMLElement).closest('.theme-toggle')) {
            const type = isNightRef.current ? 'spark' : 'pollen';
            createParticles(e.clientX, e.clientY, type);
         }
    };
    window.addEventListener('click', handleClick);

    return () => {
        window.removeEventListener('mousemove', handleMouseMove);
        window.removeEventListener('resize', handleWindowResize);
        window.removeEventListener('click', handleClick);
        cancelAnimationFrame(animationFrameId);
    };
  }, []); // Run once on mount

  // Sync ref with state for animation loop
  useEffect(() => {
    isNightRef.current = isNight;
    // We also need to re-trigger background creation if switching to night
    const canvas = canvasRef.current;
    if(canvas && isNight) {
        // Trigger resize logic implicitly to refill stars
        // Ideally we would expose createBackground but for now resize works
        window.dispatchEvent(new Event('resize')); 
    }
  }, [isNight]);

  useEffect(() => {
    const container = bhContainerRef.current;
    if (!container) return;

    const VERTEX_SHADER = `
      varying vec2 vUv;
      void main() {
        vUv = uv;
        gl_Position = vec4(position, 1.0);
      }
    `;

    const FRAGMENT_SHADER = `
      uniform float iTime;
      uniform vec2 iResolution;
      uniform vec3 iCamPos;
      uniform vec3 iCamTarget;
      varying vec2 vUv;
      #define MAX_STEPS 100
      #define MAX_DIST 60.0
      #define BH_RADIUS 1.5
      #define DISK_INNER 2.2
      #define DISK_OUTER 5.8
      float hash(float n){return fract(sin(n)*43758.5453123);} 
      float noise(vec3 x){
        vec3 p=floor(x);vec3 f=fract(x);f=f*f*(3.0-2.0*f);
        float n=p.x+p.y*57.0+113.0*p.z;
        return mix(mix(mix(hash(n+0.0),hash(n+1.0),f.x),mix(hash(n+57.0),hash(n+58.0),f.x),f.y),mix(mix(hash(n+113.0),hash(n+114.0),f.x),mix(hash(n+170.0),hash(n+171.0),f.x),f.y),f.z);
      }
      float fbm(vec3 p){float f=0.0;float amp=0.5;for(int i=0;i<5;i++){f+=amp*noise(p);p*=2.0;amp*=0.5;}return f;}
      vec3 render(vec3 ro, vec3 rd){
        vec3 col=vec3(0.0);vec3 p=ro;vec3 v=rd;float diskAcc=0.0;vec3 diskCol=vec3(0.0);float distToCenter=0.0;float totDist=0.0;
        for(int i=0;i<MAX_STEPS;i++){
          distToCenter=length(p);
          float gravityStrength=0.15*(1.0/(distToCenter*distToCenter+0.1));
          vec3 toCenter=normalize(-p);
          v=normalize(v+toCenter*gravityStrength);
          float stepSize=max(0.1,distToCenter*0.08);
          p+=v*stepSize;totDist+=stepSize;
          if(distToCenter<BH_RADIUS){return diskCol;}
          float absY=abs(p.y);
          if(absY<0.6){
            float d=length(p.xz);
            if(d>DISK_INNER && d<DISK_OUTER){
              float speed=3.0/(d-0.5);float timeOffset=iTime*speed;
              vec3 noisePos=vec3(p.x*2.5,p.z*2.5,timeOffset);
              float noiseVal=fbm(noisePos);
              float radialFade=smoothstep(DISK_INNER,DISK_INNER+0.8,d)*(1.0-smoothstep(DISK_OUTER-1.5,DISK_OUTER,d));
              float verticalFade=exp(-absY*12.0);
              float intensity=noiseVal*radialFade*verticalFade;
              vec3 sampleColor=mix(vec3(0.8,0.3,0.05),vec3(1.0,0.8,0.5),intensity*2.0);
              vec3 tanDir=normalize(vec3(-p.z,0.0,p.x));
              float doppler=dot(tanDir,normalize(ro));
              intensity*=(1.0+doppler*0.6);
              float alpha=intensity*stepSize*2.5;alpha=clamp(alpha,0.0,1.0);
              diskCol+=sampleColor*alpha*(1.0-diskAcc);
              diskAcc+=alpha; if(diskAcc>=1.0) break;
            }
          }
          if(totDist>MAX_DIST) break;
        }
        return diskCol+col;
      }
      void main(){
        vec2 uv=(gl_FragCoord.xy-0.5*iResolution.xy)/iResolution.y;
        vec3 ro=iCamPos;vec3 ta=iCamTarget;
        vec3 ww=normalize(ta-ro);
        vec3 uu=normalize(cross(ww,vec3(0.0,1.0,0.0)));
        vec3 vv=normalize(cross(uu,ww));
        float fov=1.3;vec3 rd=normalize(uv.x*uu+uv.y*vv+fov*ww);
        vec3 col=render(ro,rd);
        col=pow(col,vec3(0.6));
        col=smoothstep(0.02,1.0,col);
        float vignette=1.0-smoothstep(0.5,1.6,length(uv));
        col*=mix(0.6,1.0,vignette);
        col*=0.5;
        float a = clamp(col.r + col.g + col.b, 0.0, 1.0);
        gl_FragColor=vec4(col, a);
      }
    `;

    const scene = new THREE.Scene();
    const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
    const renderer = new THREE.WebGLRenderer({ antialias: false, alpha: true });
    renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
    renderer.setSize(window.innerWidth, window.innerHeight);
    container.innerHTML = '';
    container.appendChild(renderer.domElement);
    renderer.domElement.style.position = 'absolute';
    renderer.domElement.style.top = '0';
    renderer.domElement.style.left = '0';
    renderer.domElement.style.width = '100%';
    renderer.domElement.style.height = '100%';

    const uniforms = {
      iTime: { value: 0 },
      iResolution: { value: new THREE.Vector2(0, 0) },
      iCamPos: { value: new THREE.Vector3() },
      iCamTarget: { value: new THREE.Vector3(0, 0, 0) },
    };

    const updateResolution = () => {
      const size = new THREE.Vector2();
      renderer.getSize(size);
      const ratio = renderer.getPixelRatio();
      uniforms.iResolution.value.set(size.x * ratio, size.y * ratio);
    };

    updateResolution();

    const geometry = new THREE.PlaneGeometry(2, 2);
    const material = new THREE.ShaderMaterial({ vertexShader: VERTEX_SHADER, fragmentShader: FRAGMENT_SHADER, uniforms, transparent: true });
    const mesh = new THREE.Mesh(geometry, material);
    scene.add(mesh);

    let isDragging = false;
    let lastX = 0, lastY = 0;
    let targetLat = 0.101799, targetLon = -1.5;
    let lat = 0.101799, lon = -1.5;
    let distance = 11.0;
    let parallaxX = 0, parallaxY = 0;

    const onResize = () => {
      renderer.setSize(window.innerWidth, window.innerHeight);
      updateResolution();
    };
    const onMouseDown = (e: MouseEvent) => { isDragging = true; lastX = e.clientX; lastY = e.clientY; };
    const onMouseUp = () => { isDragging = false; };
    const onMouseMove = (e: MouseEvent) => {
      if (isDragging) {
        const dx = e.clientX - lastX; const dy = e.clientY - lastY;
        targetLon -= dx * 0.005; targetLat += dy * 0.005; targetLat = Math.max(-1.4, Math.min(1.4, targetLat));
        lastX = e.clientX; lastY = e.clientY;
      }
      // 保留内部相机交互，不再修改标题位置，避免偏移
    };
    const onWheel = (e: WheelEvent) => { distance += e.deltaY * 0.01; distance = Math.max(5.0, Math.min(20.0, distance)); };
    const onTouchStart = (e: TouchEvent) => { isDragging = true; lastX = e.touches[0].clientX; lastY = e.touches[0].clientY; };
    const onTouchMove = (e: TouchEvent) => {
      if (isDragging) {
        const dx = e.touches[0].clientX - lastX; const dy = e.touches[0].clientY - lastY;
        targetLon -= dx * 0.005; targetLat += dy * 0.005; targetLat = Math.max(-1.4, Math.min(1.4, targetLat));
        lastX = e.touches[0].clientX; lastY = e.touches[0].clientY;
      }
    };
    const onTouchEnd = () => { isDragging = false; };

    let rafId = 0;
    const animate = (time: number) => {
      rafId = requestAnimationFrame(animate);
      uniforms.iTime.value = time * 0.001;
      lat += (targetLat - lat) * 0.05; lon += (targetLon - lon) * 0.05;
      const cx = distance * Math.cos(lat) * Math.sin(lon);
      const cy = distance * Math.sin(lat);
      const cz = distance * Math.cos(lat) * Math.cos(lon);
      uniforms.iCamPos.value.set(cx, cy, cz);
      renderer.render(scene, camera);
    };

    window.addEventListener('resize', onResize);
    window.addEventListener('mousedown', onMouseDown);
    window.addEventListener('mouseup', onMouseUp);
    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('wheel', onWheel, { passive: true } as any);
    window.addEventListener('touchstart', onTouchStart, { passive: true } as any);
    window.addEventListener('touchmove', onTouchMove, { passive: false } as any);
    window.addEventListener('touchend', onTouchEnd, { passive: true } as any);
    animate(0);

    return () => {
      window.removeEventListener('resize', onResize);
      window.removeEventListener('mousedown', onMouseDown);
      window.removeEventListener('mouseup', onMouseUp);
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('wheel', onWheel as any);
      window.removeEventListener('touchstart', onTouchStart as any);
      window.removeEventListener('touchmove', onTouchMove as any);
      window.removeEventListener('touchend', onTouchEnd as any);
      cancelAnimationFrame(rafId);
      geometry.dispose(); material.dispose(); renderer.dispose();
      if (renderer.domElement && renderer.domElement.parentElement) renderer.domElement.parentElement.removeChild(renderer.domElement);
    };
  }, []);

  // --- HANDLERS ---
  const handleThemeSwitch = (e: React.MouseEvent) => {
    if (!themeBtnRef.current || !transitionLayerRef.current) return;

    const rect = themeBtnRef.current.getBoundingClientRect();
    const btnX = rect.left + rect.width / 2;
    const btnY = rect.top + rect.height / 2;
    const maxRadius = Math.hypot(Math.max(btnX, window.innerWidth - btnX), Math.max(btnY, window.innerHeight - btnY)) * 1.2;
    const targetColor = isNight ? COLOR_DAY : COLOR_NIGHT;
    
    const layer = transitionLayerRef.current;
    
    layer.style.transition = 'none';
    layer.style.opacity = '1';
    layer.style.backgroundColor = targetColor;
    layer.style.clipPath = `circle(0px at ${btnX}px ${btnY}px)`;
    // Force reflow
    void layer.offsetHeight; 

    layer.style.transition = 'clip-path 0.8s ease-in-out';
    layer.style.clipPath = `circle(${maxRadius}px at ${btnX}px ${btnY}px)`;

    setTimeout(() => {
        setIsNight(!isNight);
        // Fade out layer
        layer.style.transition = 'opacity 0.8s ease';
        layer.style.opacity = '0';
        setTimeout(() => {
             layer.style.clipPath = `circle(0px at ${btnX}px ${btnY}px)`;
        }, 800);
    }, 800);
  };

  const handleDrag = (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
  };
  const handleDragIn = (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      dragCounter.current++;
      if (e.dataTransfer.items && e.dataTransfer.items.length > 0) {
          setIsDragging(true);
      }
  };
  const handleDragOut = (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      dragCounter.current--;
      if (dragCounter.current === 0) setIsDragging(false);
  };
  const handleDrop = (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setIsDragging(false);
      dragCounter.current = 0;
      if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
          const file = e.dataTransfer.files[0];
          if (file) handleFileSelect(file);
          e.dataTransfer.clearData();
      }
  };
  const handleFileSelect = async (file?: File | null) => {
    if (!file) return;
    const name = (file.name || '').toLowerCase();
    const isImageMime = (file.type || '').startsWith('image/');
    const isHeic = /\.(heic|heif)$/.test(name);
    const isRaw = /\.(dng|raw|arw|cr2|nef|raf|orf|rw2)$/.test(name);
    const isSpecial = isHeic || isRaw;
    
    setSelectedFile(file);
    if (isImageMime && !isSpecial) {
      setFilePreview(URL.createObjectURL(file));
      return;
    }
    try {
      if (isHeic) {
        const { convertHeicClient } = await import('../services/gemini');
        const previewUrl = await convertHeicClient(file);
        setFilePreview(previewUrl);
        (window as any)._previewError = undefined;
        return;
      }
      const { getPreviewForUpload } = await import('../services/gemini');
      const previewUrl = await getPreviewForUpload(file);
      setFilePreview(previewUrl);
      (window as any)._previewError = undefined;
    } catch (e) {
      setFilePreview('');
      (window as any)._previewError = 'HEIC/RAW 预览需要后端依赖，请安装 pillow-heif/rawpy';
    }
  };

  const handleSubmit = () => {
    if (selectedFile && promptText.trim()) {
        setIsLoading(true);
        // Simulate loading for animation demo
        setTimeout(() => {
            onStart(selectedFile, promptText, 'direct');
            setIsLoading(false);
        }, 2000);
    }
  };

  return (
    <div className="relative overflow-hidden font-sans selection:bg-amber-500/30" style={{ backgroundColor: '#0b0b0c', transition: 'background-color 0.8s', minHeight: '100vh', width: '100vw' }}>
      
      {/* 0. Canvas Layers */}
      <canvas ref={canvasRef} className="z-0 block opacity-80" style={{ position: 'absolute', top: 0, right: 0, bottom: 0, left: 0 }} />
      <div className="z-0 absolute inset-0 bg-gradient-to-b from-transparent via-[#0b0b0c]/50 to-[#0b0b0c] pointer-events-none" />
      
      <div ref={bhContainerRef} className="absolute inset-0 z-0 pointer-events-none" aria-hidden="true" />
      {/* Premium Glow */}
      <div className="z-0 absolute top-[-20%] left-[20%] w-[60vw] h-[60vw] bg-purple-900/10 blur-[120px] rounded-full pointer-events-none animate-pulse" style={{ animationDuration: '8s' }} />
      <div className="z-0 absolute bottom-[-10%] right-[-10%] w-[40vw] h-[40vw] bg-amber-600/5 blur-[100px] rounded-full pointer-events-none" />
      
      <div ref={transitionLayerRef} className="z-10 pointer-events-none opacity-0" style={{ position: 'absolute', top: 0, right: 0, bottom: 0, left: 0 }} />

      {/* 1. Top Navigation */}
      <nav className="absolute top-0 left-0 right-0 z-50 p-6 flex justify-between items-center">
         {/* Brand Left (Optional, kept clean for now) */}
         <div className="w-12"></div> 

         {/* Controls Right */}
         <div className="flex items-center gap-4">
            <button 
                onClick={() => setLang(lang === 'en' ? 'zh' : 'en')}
                className="px-4 py-1.5 rounded-full bg-white/5 hover:bg-white/10 backdrop-blur-md border border-white/10 text-white/80 hover:text-white text-xs font-medium tracking-wide transition-all"
            >
                {lang === 'en' ? '中文' : 'EN'}
            </button>
            <button 
                ref={themeBtnRef}
                onClick={handleThemeSwitch}
                className="w-10 h-10 rounded-full bg-white/5 hover:bg-white/10 backdrop-blur-md border border-white/10 flex items-center justify-center text-white/80 hover:text-white transition-all"
            >
                {isNight ? (
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z"></path></svg>
                ) : (
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z"></path></svg>
                )}
            </button>
         </div>
      </nav>

      {/* 2. Main UI Content */}
      <div 
        className="z-30 relative w-full h-screen flex flex-col items-center justify-center px-4 sm:px-6 lg:px-8"
        onDragEnter={handleDragIn}
        onDragLeave={handleDragOut}
        onDragOver={handleDrag}
        onDrop={handleDrop}
      >
         {/* Drag Overlay */}
         <AnimatePresence>
            {isDragging && (
                <motion.div 
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    className="absolute inset-0 z-50 bg-black/60 backdrop-blur-sm border-4 border-white/20 border-dashed m-4 rounded-3xl flex items-center justify-center"
                >
                    <div className="text-center text-white">
                        <ArrowUpTrayIcon className="w-16 h-16 mx-auto mb-6 animate-bounce text-white/80" />
                        <h3 className="text-3xl font-light tracking-tight">{dict.dragTip}</h3>
                    </div>
                </motion.div>
            )}
         </AnimatePresence>

         {/* Content Wrapper */}
         <div className="w-full max-w-5xl mx-auto flex flex-col items-center">
             
            <motion.div 
               initial={{ opacity: 0, y: 20 }}
               animate={{ opacity: 1, y: 0 }}
               transition={{ duration: 0.8, ease: "easeOut" }}
               className="text-center mb-20 relative"
            >
                <h1 ref={titleRef} className="text-7xl md:text-9xl lg:text-[12rem] font-bold tracking-[0.25em] text-transparent bg-clip-text bg-gradient-to-br from-amber-100 via-white to-purple-200 uppercase drop-shadow-2xl select-none">
                   {'LUMINA'}
                </h1>
            </motion.div>

             {/* Input Section */}
             <motion.div 
                initial={{ opacity: 0, scale: 0.98 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ delay: 0.2, duration: 0.6 }}
                className="w-full max-w-3xl mb-16"
             >
                 <div className="group relative bg-white/5 hover:bg-white/10 backdrop-blur-2xl border border-white/10 rounded-2xl p-2 transition-all duration-300 shadow-2xl hover:shadow-amber-500/5 ring-1 ring-white/5 focus-within:ring-amber-500/20">
                     <div className="flex items-center gap-2">
                         {/* Upload Button */}
                         <div className="relative">
                             <input 
                                type="file" 
                                ref={fileInputRef}
                                onChange={(e) => {
                                  const f = e.target.files?.item(0);
                                  if (f) handleFileSelect(f);
                                }}
                                className="hidden"
                                accept="image/*,.heic,.heif,.dng,.raw,.arw,.cr2,.nef,.raf,.orf,.rw2"
                             />
                             <button 
                                onClick={() => fileInputRef.current?.click()}
                                className="w-14 h-14 rounded-xl bg-white/5 hover:bg-white/10 border border-white/5 flex items-center justify-center text-white/70 transition-all overflow-hidden"
                             >
                                 {filePreview ? (
                                     <img src={filePreview} className="w-full h-full object-cover" />
                                 ) : (
                                     <PhotoIcon className="w-6 h-6" />
                                 )}
                             </button>
                         </div>

                         {/* Input Field */}
                         <div className="flex-1 relative">
                             <input 
                                type="text"
                                value={promptText}
                                onChange={(e) => setPromptText(e.target.value)}
                                placeholder={dict.describePlaceholder}
                                className="w-full h-14 bg-transparent text-white placeholder-white/30 px-4 text-lg outline-none font-light"
                                onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
                             />
                         </div>

                        <div className="flex items-center gap-2">
                          <button 
                            onClick={() => selectedFile && onStart(selectedFile, promptText, 'analyze')}
                            disabled={!selectedFile || isLoading}
                            className="h-14 px-6 rounded-xl bg-white/10 hover:bg-white/20 border border-white/20 text-white font-semibold text-base transition-all flex items-center gap-2 shadow-lg disabled:bg-white/10 disabled:text-white/20 disabled:shadow-none disabled:cursor-not-allowed"
                          >
                            <span>{lang === 'zh' ? '分析' : 'Analyze'}</span>
                          </button>
                          <button 
                             ref={generateBtnRef}
                             onClick={handleSubmit}
                             disabled={!selectedFile || isLoading || !promptText.trim()}
                             className="h-14 px-8 rounded-xl bg-white text-black hover:bg-amber-50 disabled:bg-white/10 disabled:text-white/20 font-semibold text-base transition-all flex items-center gap-2 shadow-lg disabled:shadow-none disabled:cursor-not-allowed relative overflow-hidden"
                          >
                              <span className={`transition-opacity duration-200 ${isLoading ? 'opacity-0' : 'opacity-100'}`}>
                                 {lang === 'zh' ? '生成' : 'Generate'}
                              </span>
                              {isLoading && (
                                <div className="absolute inset-0 flex items-center justify-center">
                                  <BlinkingSmileIcon className="w-8 h-8 text-amber-600" />
                                </div>
                              )}
                              {!isLoading && <BlinkingSmileIcon className="w-6 h-6" />}
                          </button>
                        </div>
                     </div>
                 </div>

                 {/* Quick Prompts / Examples */}
                 {!promptText && (
                    <div className="mt-4 flex justify中心">
                        <button 
                            onClick={() => setPromptText(dict.examplePrompt)}
                            className="text-xs text-white/40 hover:text-white/80 transition-colors flex items-center gap-2"
                        >
                            <span className="opacity-50">{dict.example}:</span>
                            <span>"{dict.examplePrompt}"</span>
                        </button>
                    </div>
                 )}
                 {(!filePreview && selectedFile && (window as any)._previewError) && (
                    <div className="mt-3 w-full text-center">
                      <p className="text-xs text-amber-300 bg-amber-500/10 border border-amber-500/20 rounded-lg inline-block px-3 py-1">
                        {(window as any)._previewError}
                      </p>
                    </div>
                 )}
             </motion.div>

             {/* Features Grid */}
             <motion.div 
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.4, duration: 0.6 }}
                className="grid grid-cols-1 md:grid-cols-3 gap-6 w-full max-w-4xl px-4"
             >
                {dict.features.map((feat: any, i: number) => (
                     <div key={i} className="flex flex-col items-center text-center p-4 rounded-2xl hover:bg-white/5 transition-colors duration-500 group">
                         <div className="w-10 h-10 rounded-full bg-white/5 flex items-center justify-center text-white/80 mb-4 group-hover:scale-110 transition-transform duration-500" data-collider="true">
                             {i === 0 && <HandThumbUpIcon className="w-5 h-5" />}
                             {i === 1 && <BoltIcon className="w-5 h-5" />}
                             {i === 2 && <StarIcon className="w-5 h-5" />}
                         </div>
                         <h3 className="text-white font-medium mb-1">{feat.title}</h3>
                         <p className="text-sm text-white/40 font-light">{feat.desc}</p>
                     </div>
                 ))}
             </motion.div>

         </div>
      </div>

    </div>
  );
};
  
