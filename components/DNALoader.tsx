
import React from 'react';
import { motion } from 'framer-motion';

interface DNALoaderProps {
  embedded?: boolean;
  scanning?: boolean;
  text?: string;
}

export const DNALoader: React.FC<DNALoaderProps> = ({ 
  embedded = false, 
  scanning = false,
  text = "Initializing Core" 
}) => {
  const bgClass = scanning
    ? 'absolute inset-0 z-20 bg-black/80 backdrop-blur-md'
    : embedded
      ? 'absolute inset-0 z-50 bg-black/80 backdrop-blur-md'
      : 'fixed inset-0 z-[100] bg-[#0a0a0c]';

  const particles = Array.from({ length: 15 });

  return (
    <motion.div
      className={`flex flex-col items-center justify-center ${bgClass}`}
      initial={embedded || scanning ? { opacity: 0 } : undefined}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0, transition: { duration: 0.5, ease: 'easeInOut' } }}
    >
      <div className="relative w-20 h-40 flex items-center justify-center scale-75 md:scale-100">
        <style>{`
          @keyframes moveStrand1 {
            0% { transform: translateX(-18px) scale(0.8); opacity: 0.6; z-index: 0; }
            25% { transform: translateX(0px) scale(1); opacity: 1; z-index: 10; }
            50% { transform: translateX(18px) scale(0.85); opacity: 0.7; z-index: 0; }
            75% { transform: translateX(0px) scale(0.7); opacity: 0.5; z-index: -10; }
            100% { transform: translateX(-18px) scale(0.8); opacity: 0.6; z-index: 0; }
          }
          @keyframes moveStrand2 {
            0% { transform: translateX(18px) scale(0.8); opacity: 0.6; z-index: 0; }
            25% { transform: translateX(0px) scale(0.7); opacity: 0.5; z-index: -10; }
            50% { transform: translateX(-18px) scale(0.85); opacity: 0.7; z-index: 0; }
            75% { transform: translateX(0px) scale(1); opacity: 1; z-index: 10; }
            100% { transform: translateX(18px) scale(0.8); opacity: 0.6; z-index: 0; }
          }
        `}</style>

        {particles.map((_, i) => (
          <div
            key={`s1-${i}`}
            className="absolute w-3 h-3 rounded-full bg-white shadow-[0_0_8px_rgba(255,255,255,0.8)]"
            style={{
              top: `${i * 12}px`,
              animation: `moveStrand1 2s linear infinite`,
              animationDelay: `${-i * 0.15}s`
            }}
          />
        ))}

        {particles.map((_, i) => (
          <div
            key={`s2-${i}`}
            className="absolute w-3 h-3 rounded-full bg-amber-400 shadow-[0_0_8px_rgba(245,197,24,0.8)]"
            style={{
              top: `${i * 12}px`,
              animation: `moveStrand2 2s linear infinite`,
              animationDelay: `${-i * 0.15}s`
            }}
          />
        ))}
      </div>

      <motion.p 
        className="mt-6 text-zinc-300 text-sm font-medium text-center px-4"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.3 }}
      >
        {text}
      </motion.p>
    </motion.div>
  );
};

export const BlinkingSmileIcon: React.FC<{ className?: string }> = ({ className = '' }) => (
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className={className}>
    <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" />
    <motion.circle cx="9.5" cy="9.75" r="0.9" fill="currentColor" style={{ transformOrigin: 'center' }} animate={{ scaleY: [1, 0.15, 1, 1, 1, 1] }} transition={{ duration: 1.8, repeat: Infinity, times: [0, 0.12, 0.24, 0.5, 0.6, 1] }} />
    <motion.circle cx="14.5" cy="9.75" r="0.9" fill="currentColor" style={{ transformOrigin: 'center' }} animate={{ scaleY: [1, 1, 1, 1, 0.15, 1] }} transition={{ duration: 1.8, repeat: Infinity, times: [0, 0.5, 0.6, 0.72, 0.84, 1] }} />
    <path d="M15.182 15.182a4.5 4.5 0 0 1-6.364 0" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);
export const MiniDNAIcon: React.FC<{ className?: string }> = ({ className = '' }) => (
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" className={className}>
    <motion.path d="M6 4 C 10 6, 10 10, 6 12 C 2 14, 2 18, 6 20" stroke="#ffffff" strokeWidth="1.6" strokeLinecap="round" fill="none" strokeDasharray="4 3" animate={{ strokeDashoffset: [0, 7, 0] }} transition={{ duration: 1.4, repeat: Infinity }} />
    <motion.path d="M18 4 C 14 6, 14 10, 18 12 C 22 14, 22 18, 18 20" stroke="#F5C518" strokeWidth="1.6" strokeLinecap="round" fill="none" strokeDasharray="4 3" animate={{ strokeDashoffset: [7, 0, 7] }} transition={{ duration: 1.4, repeat: Infinity }} />
    <motion.line x1="8" y1="6" x2="16" y2="8" stroke="#ffffff" strokeWidth="1.2" strokeLinecap="round" animate={{ opacity: [0.4, 1, 0.4] }} transition={{ duration: 1.2, repeat: Infinity }} />
    <motion.line x1="8" y1="10" x2="16" y2="12" stroke="#F5C518" strokeWidth="1.2" strokeLinecap="round" animate={{ opacity: [1, 0.4, 1] }} transition={{ duration: 1.2, repeat: Infinity, delay: 0.15 }} />
    <motion.line x1="8" y1="14" x2="16" y2="16" stroke="#ffffff" strokeWidth="1.2" strokeLinecap="round" animate={{ opacity: [0.4, 1, 0.4] }} transition={{ duration: 1.2, repeat: Infinity, delay: 0.3 }} />
    <motion.line x1="8" y1="18" x2="16" y2="20" stroke="#F5C518" strokeWidth="1.2" strokeLinecap="round" animate={{ opacity: [1, 0.4, 1] }} transition={{ duration: 1.2, repeat: Infinity, delay: 0.45 }} />
  </svg>
);
