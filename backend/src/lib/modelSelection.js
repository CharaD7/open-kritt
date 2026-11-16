import { prisma } from '../db.js';
import { modelCatalogEntry } from './modelCatalog.js';
import { isModelProviderConfigured } from './modelProviders.js';
import { ValidationError } from './validation.js';

async function findCatalog(provider) {
  return prisma.modelCatalog.findUnique({ where: { provider } });
}

export async function assertModelSelectionAvailable(
  { modelProvider, model, thinkingEffort },
  { providerConfigured = isModelProviderConfigured, getCatalog = findCatalog } = {}
) {
  if (!(await providerConfigured(modelProvider))) {
    throw new ValidationError([{ field: 'model_provider', message: 'The selected model provider is not configured.' }]);
  }

  if (modelProvider === 'openrouter') return;

  const catalog = modelCatalogEntry(modelProvider, await getCatalog(modelProvider));
  if (catalog.status !== 'ready') {
    throw new ValidationError([
      { field: 'model', message: `The ${modelProvider} model catalog is not available yet.` },
    ]);
  }

  const selectedModel = catalog.models.find((candidate) => candidate.id === model);
  if (!selectedModel) {
    throw new ValidationError([
      { field: 'model', message: `Model "${model}" is not available for provider "${modelProvider}".` },
    ]);
  }

  // A model with no declared reasoning-effort variants (for example
    // Foundation-Sec, which is not a reasoning model) accepts the harness
    // default. An empty list means "no variants", not "no effort is valid" -
    // without this, such models could never be selected at all.
    const effortDeclared = Array.isArray(selectedModel.thinkingEfforts)
      && selectedModel.thinkingEfforts.length > 0;
    if (effortDeclared && thinkingEffort
        && !selectedModel.thinkingEfforts.includes(thinkingEffort)) {
      throw new ValidationError([
        {
          field: 'thinking_effort',
          message: `Thinking effort "${thinkingEffort}" is not available for model "${model}".`,
        },
      ]);
    }
}
