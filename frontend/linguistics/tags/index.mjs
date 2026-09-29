import { initializeEastAsian } from './east-asian.mjs';
import { initializeEuropean } from './european.mjs';
import { initializeLatin } from './latin.mjs';
import { initializeSouthAsian } from './south-asian.mjs';
import { initializeWestern } from './western.mjs';
import { initializeAdditionalLanguages } from './additional-languages.mjs';
import { initializeRegistry } from './registry.mjs';
import { initializeAncientGreek } from './ancient-greek.mjs';
import { initializeDependencies } from './dependencies.mjs';
import { initializeFeatures } from './features.mjs';
import { initializeApi } from './api.mjs';

/** Initialize features in the original script order. */
function bootstrap() {
  if (!initializeEastAsian()) return;
  if (!initializeEuropean()) return;
  if (!initializeLatin()) return;
  if (!initializeSouthAsian()) return;
  if (!initializeWestern()) return;
  if (!initializeAdditionalLanguages()) return;
  if (!initializeRegistry()) return;
  if (!initializeAncientGreek()) return;
  if (!initializeDependencies()) return;
  if (!initializeFeatures()) return;
  if (!initializeApi()) return;
}
bootstrap();
