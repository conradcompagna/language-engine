import { initializeNormalization } from './normalization.mjs';
import { initializeModel } from './model.mjs';
import { initializeIndexLoading } from './index-loading.mjs';
import { initializeSelection } from './selection.mjs';
import { initializeSegmentation } from './segmentation.mjs';
import { initializeCompactIndex } from './compact-index.mjs';
import { initializeFuzzySearch } from './fuzzy-search.mjs';
import { initializeHydration } from './hydration.mjs';

/** Initialize features in the original script order. */
function bootstrap() {
  if (!initializeNormalization()) return;
  if (!initializeModel()) return;
  if (!initializeIndexLoading()) return;
  if (!initializeSelection()) return;
  if (!initializeSegmentation()) return;
  if (!initializeCompactIndex()) return;
  if (!initializeFuzzySearch()) return;
  if (!initializeHydration()) return;
}
bootstrap();
