import { initializeBridge } from './bridge.mjs';
import { initializeTextLayer } from './text-layer.mjs';
import { initializeEvents } from './events.mjs';

/** Initialize features in the original script order. */
function bootstrap() {
  if (!initializeBridge()) return;
  if (!initializeTextLayer()) return;
  if (!initializeEvents()) return;
}
bootstrap();
