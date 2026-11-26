/// <reference types="vite/client" />
interface ImportMetaEnv {
  readonly VITE_APP_MODE?: 'demo' | 'api';
  readonly VITE_API_URL?: string;
  readonly VITE_SUPABASE_URL?: string;
  readonly VITE_SUPABASE_ANON_KEY?: string;
  readonly VITE_SUPABASE_PUBLISHABLE_KEY?: string;
  readonly VITE_MAX_AUDIO_MB?: string;
  readonly VITE_MAX_DATA_MB?: string;
}
