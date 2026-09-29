import { initializeCore } from './core.mjs';
import { initializeSurfaceLookup } from './surface-lookup.mjs';
import { initializeAlignmentInputs } from './alignment-inputs.mjs';
import { initializePublicApi } from './public-api.mjs';

/** Initialize features in the original script order. */
function bootstrap() {
  if (!initializeCore()) return;
  if (!initializeSurfaceLookup()) return;
  if (!initializeAlignmentInputs()) return;
  if (!initializePublicApi()) return;
}
bootstrap();
