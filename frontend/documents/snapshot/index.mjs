import { initializeFrameLifecycle } from './frame-lifecycle.mjs';
import { initializeTextExtraction } from './text-extraction.mjs';
import { initializePublicApi } from './public-api.mjs';

/** Initialize features in the original script order. */
function bootstrap() {
  if (!initializeFrameLifecycle()) return;
  if (!initializeTextExtraction()) return;
  if (!initializePublicApi()) return;
}
bootstrap();
