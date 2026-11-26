# Destino de despliegue: Vercel y Supabase

Configuración prevista, sin despliegue realizado.

| Componente | Destino | Estado |
|---|---|---|
| Interfaz TypeScript/Vite | Vercel | vercel.json define instalación, build y salida |
| PostgreSQL compartido | Supabase | Migración aditiva disponible; no ejecutada en nube |
| Identidad y permisos | Supabase Auth y RLS | Integración pendiente |
| Audios, documentos y exportaciones | Supabase Storage privado | Adaptador pendiente |
| API Python y trabajos de motores | Entorno compatible pendiente de definir | No cubierto por vercel.json |

`vercel.json` publica solo la interfaz. No despliega los motores ni convierte el proxy de Vite en un proxy de producción. Las rutas `/api`, `/data-api` y `/audio-service` necesitan un gateway HTTPS de producción hacia la API y los trabajadores. No hay URLs ficticias configuradas.

Supabase aporta PostgreSQL, Auth y Storage; no debe asumirse que ejecuta los procesos Python/CUDA de los motores. Vercel dispone de runtime Python con límites de tamaño, duración y carga de archivos que deben comprobarse para la versión y plan elegidos. No incluir modelos de voz en el paquete frontend. Si el requisito final exige solo estos dos proveedores, se debe resolver expresamente cómo ejecutar el motor de audio existente antes de declarar el despliegue integral viable.

Antes de producción: JWT verificado en backend, autorización por institución y rol, políticas RLS de datos y Storage, subidas privadas con URLs firmadas, trabajos persistentes y reintentos, eliminación/retención y límites de tamaño. Las credenciales de servicio y DATABASE_URL pertenecen al servidor, nunca a variables VITE_.

La migración actual mantiene el esquema de extensiones sin permisos públicos. El frontend no consulta su tabla directamente. No publicar las API locales actuales sin completar autenticación.

Fuentes oficiales:
- https://vercel.com/docs/functions/limitations
- https://vercel.com/docs/functions/runtimes/python
- https://supabase.com/docs/guides/getting-started/architecture
- https://supabase.com/docs/guides/database/postgres/row-level-security
