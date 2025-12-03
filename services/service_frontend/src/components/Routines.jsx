import { motion } from 'framer-motion';
import { useState } from 'react';
import { Plus, Play } from 'lucide-react';
import { useTheme } from '../utils/useTheme';

const Routines = () => {
  const { themeColors } = useTheme();
  const [canvasBlocks, setCanvasBlocks] = useState([]);

  const blocks = [
    { id: 'when', label: 'WHEN', color: 'bg-warning/20 border-warning' },
    { id: 'if', label: 'IF', color: 'bg-error/20 border-error' },
    { id: 'then', label: 'THEN', color: 'bg-success/20 border-success' },
  ];

  const addBlock = (blockType) => {
    const newBlock = {
      id: Date.now(),
      type: blockType,
      x: Math.random() * 400,
      y: Math.random() * 300,
    };
    setCanvasBlocks([...canvasBlocks, newBlock]);
  };

  return (
    <div>
      <h2 className="text-2xl font-bold text-primary mb-6 drop-shadow-lg">Automation Routines</h2>

      <div className="flex space-x-6">
        {/* Sidebar */}
        <div className="w-48">
          <h3 className="text-lg font-semibold text-text-secondary mb-4">Blocks</h3>
          <div className="space-y-3">
            {blocks.map((block) => (
              <motion.button
                key={block.id}
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                onClick={() => addBlock(block.id)}
                className={`w-full p-3 rounded-lg border-2 ${block.color} text-text-primary hover:drop-shadow-lg transition-all`}
              >
                {block.label}
              </motion.button>
            ))}
          </div>
        </div>

        {/* Canvas */}
        <div className="flex-1 glass rounded-lg p-4 min-h-[400px] relative overflow-hidden">
          <div className="absolute inset-0 opacity-10">
            <div className="w-full h-full" style={{
              backgroundImage: `radial-gradient(circle, ${themeColors.accent} 1px, transparent 1px)`,
              backgroundSize: '20px 20px'
            }}></div>
          </div>

          {canvasBlocks.map((block) => (
            <motion.div
              key={block.id}
              drag
              dragConstraints={{ left: 0, top: 0, right: 400, bottom: 300 }}
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              className={`absolute p-3 rounded-lg border-2 cursor-move ${
                blocks.find(b => b.id === block.type)?.color
              } text-text-primary drop-shadow-lg`}
            >
              {blocks.find(b => b.id === block.type)?.label}
            </motion.div>
          ))}

          {canvasBlocks.length === 0 && (
            <div className="flex items-center justify-center h-full text-text-tertiary">
              <div className="text-center">
                <Plus className="w-12 h-12 mx-auto mb-4 opacity-50" />
                <p>Drag blocks here to create routines</p>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Run Button */}
      <div className="mt-6 flex justify-end">
        <motion.button
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          className="flex items-center space-x-2 px-6 py-3 bg-primary/20 border border-primary rounded-lg text-primary hover:bg-primary/30 transition-colors drop-shadow-lg"
        >
          <Play className="w-5 h-5" />
          <span>Run Routine</span>
        </motion.button>
      </div>
    </div>
  );
};

export default Routines;
