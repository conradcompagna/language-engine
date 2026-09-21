import { initializeGraphemes } from './graphemes.mjs';
import { initializeSmoothing } from './smoothing.mjs';
import { initializeCodepoints } from './codepoints.mjs';
import { initializeSemiticAnalysis } from './semitic-analysis.mjs';
import { initializeSemiticTables } from './semitic-tables.mjs';
import { initializeAlphabetTables } from './alphabet-tables.mjs';
import { initializeJapaneseTables } from './japanese-tables.mjs';
import { initializeHangulTables } from './hangul-tables.mjs';
import { initializeAbugidaTables } from './abugida-tables.mjs';
import { initializeThaiTables } from './thai-tables.mjs';
import { initializeLatinTables } from './latin-tables.mjs';
import { initializeSemiticExtensions } from './semitic-extensions.mjs';
import { initializeAlphabetExtensions } from './alphabet-extensions.mjs';
import { initializeJapaneseExtensions } from './japanese-extensions.mjs';
import { initializeJapaneseSpans } from './japanese-spans.mjs';
import { initializeHangulExtensions } from './hangul-extensions.mjs';
import { initializeAbugidaExtensions } from './abugida-extensions.mjs';
import { initializeThaiExtensions } from './thai-extensions.mjs';
import { initializeLatinExtensions } from './latin-extensions.mjs';
import { initializeAliases } from './aliases.mjs';
import { initializeProfiles } from './profiles.mjs';
import { initializePublicApi } from './public-api.mjs';

/** Initialize features in the original script order. */
function bootstrap() {
  if (!initializeGraphemes()) return;
  if (!initializeSmoothing()) return;
  if (!initializeCodepoints()) return;
  if (!initializeSemiticAnalysis()) return;
  if (!initializeSemiticTables()) return;
  if (!initializeAlphabetTables()) return;
  if (!initializeJapaneseTables()) return;
  if (!initializeHangulTables()) return;
  if (!initializeAbugidaTables()) return;
  if (!initializeThaiTables()) return;
  if (!initializeLatinTables()) return;
  if (!initializeSemiticExtensions()) return;
  if (!initializeAlphabetExtensions()) return;
  if (!initializeJapaneseExtensions()) return;
  if (!initializeJapaneseSpans()) return;
  if (!initializeHangulExtensions()) return;
  if (!initializeAbugidaExtensions()) return;
  if (!initializeThaiExtensions()) return;
  if (!initializeLatinExtensions()) return;
  if (!initializeAliases()) return;
  if (!initializeProfiles()) return;
  if (!initializePublicApi()) return;
}
bootstrap();
