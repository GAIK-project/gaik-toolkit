export interface AzureConfig {
  apiKey: string;
  resourceName: string;
  apiVersion: string;
}

export interface OpenAIConfig {
  apiKey: string;
}

export function getAzureConfig(): AzureConfig | null {
  const apiKey = process.env.AZURE_API_KEY;
  const resourceName = process.env.AZURE_RESOURCE_NAME;

  if (!apiKey || !resourceName) return null;

  return {
    apiKey,
    resourceName,
    apiVersion: process.env.AZURE_API_VERSION ?? '2025-04-01-preview',
  };
}

export function getOpenAIConfig(): OpenAIConfig | null {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) return null;
  return { apiKey };
}

export function validateEnv(): void {
  const azure = getAzureConfig();
  const openai = getOpenAIConfig();

  if (!azure && !openai) {
    throw new Error(
      'No AI provider configured. Please set either AZURE_API_KEY + AZURE_RESOURCE_NAME or OPENAI_API_KEY.'
    );
  }
}

export function requireAzureConfig(): AzureConfig {
  const cfg = getAzureConfig();
  if (!cfg) {
    throw new Error('Azure OpenAI not configured. Set AZURE_API_KEY and AZURE_RESOURCE_NAME.');
  }
  return cfg;
}

export function requireOpenAIConfig(): OpenAIConfig {
  const cfg = getOpenAIConfig();
  if (!cfg) {
    throw new Error('OpenAI not configured. Set OPENAI_API_KEY.');
  }
  return cfg;
}
