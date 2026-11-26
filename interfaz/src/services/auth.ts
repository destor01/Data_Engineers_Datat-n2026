import { createClient, type Session, type SupabaseClient } from '@supabase/supabase-js';
import { demo } from './config';

/**
 * Sesión con Supabase Auth (correo y contraseña). Las cuentas las crea el equipo en
 * Supabase → Authentication → Users; el registro público está desactivado.
 */
const url = import.meta.env.VITE_SUPABASE_URL as string | undefined;
const key = (import.meta.env.VITE_SUPABASE_ANON_KEY ?? import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY) as string | undefined;

export const loginEnabled = !demo && Boolean(url && key);
const client: SupabaseClient | null = loginEnabled ? createClient(url!, key!, {
  auth: { persistSession: true, autoRefreshToken: true, storageKey: 'quality-audit-sesion' }
}) : null;

export async function currentSession(): Promise<Session | null> {
  if (!client) return null;
  const { data } = await client.auth.getSession();
  return data.session;
}

export async function signIn(email: string, password: string): Promise<Session> {
  if (!client) throw new Error('El inicio de sesión no está configurado.');
  const { data, error } = await client.auth.signInWithPassword({ email: email.trim(), password });
  if (error || !data.session) {
    const detail = error?.message ?? '';
    if (detail === 'Invalid login credentials') throw new Error('Correo o contraseña incorrectos.');
    if (/email not confirmed/i.test(detail)) throw new Error('La cuenta no está confirmada. Confírmala en Supabase → Authentication → Users.');
    if (/invalid api key|no api key/i.test(detail)) throw new Error('La llave de Supabase de la interfaz no es válida (VITE_SUPABASE_ANON_KEY).');
    if (/disabled/i.test(detail)) throw new Error('El inicio de sesión con correo está desactivado en Supabase → Sign In / Providers.');
    throw new Error(`No se pudo iniciar sesión${detail ? `: ${detail}` : '.'}`);
  }
  return data.session;
}

export async function signOut(): Promise<void> { await client?.auth.signOut(); }

export function onSessionChange(listener: (session: Session | null) => void): void {
  client?.auth.onAuthStateChange((_event, session) => listener(session));
}

/** Cabecera Authorization para la API (el cliente renueva el token antes de que expire). */
export async function authHeaders(): Promise<Record<string, string>> {
  const session = await currentSession();
  return session ? { Authorization: `Bearer ${session.access_token}` } : {};
}
