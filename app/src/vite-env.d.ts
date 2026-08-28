/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_SUPABASE_URL: string;
  readonly VITE_SUPABASE_PUBLISHABLE_KEY: string;
  readonly VITE_AUDIO_BASE_URL: string;
  readonly VITE_CORRECTION_API_URL: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
