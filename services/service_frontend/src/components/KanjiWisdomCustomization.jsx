import { Languages } from 'lucide-react';
import { useUiPrefs } from '../utils/useUiPrefs';

// On/off switch for the daily kanji quote overlay. A browser-side preference (like the
// Nexus navigation mode): it applies immediately and is remembered by this browser only.
const KanjiWisdomCustomization = () => {
  const { kanjiWisdom, setKanjiWisdom } = useUiPrefs();

  return (
    <div>
      <div className="mb-4 flex items-start space-x-2">
        <Languages className="w-5 h-5 text-fui-accent mt-0.5" />
        <div>
          <h3 className="font-tech font-bold text-lg uppercase tracking-widest text-fui-accent">
            Kanji Wisdom
          </h3>
          <p className="text-fui-text text-xs">
            One proverb or word a day in kanji, with its reading and meaning, in the
            bottom-left corner. Applies immediately and is remembered by this browser.
          </p>
        </div>
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={kanjiWisdom}
        onClick={() => setKanjiWisdom(!kanjiWisdom)}
        className={`flex items-center space-x-3 bg-fui-panel border px-4 py-3 font-mono text-sm uppercase tracking-wider transition-colors ${
          kanjiWisdom ? 'border-fui-accent text-fui-accent' : 'border-fui-border text-fui-text hover:border-fui-accent/60'
        }`}
      >
        <span
          className={`inline-block w-8 h-4 border relative ${kanjiWisdom ? 'border-fui-accent' : 'border-fui-border'}`}
        >
          <span
            className={`absolute top-0.5 bottom-0.5 w-3 transition-all ${
              kanjiWisdom ? 'right-0.5 bg-fui-accent' : 'left-0.5 bg-fui-border'
            }`}
          />
        </span>
        <span>{kanjiWisdom ? 'Shown' : 'Hidden'}</span>
      </button>
    </div>
  );
};

export default KanjiWisdomCustomization;
