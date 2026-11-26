# Manual de usuario

## Audio Audit

Iniciar el servidor según la [instalación](installation.md) y abrir http://127.0.0.1:8000. Utilizar una grabación simulada o autorizada. Seleccionar el modelo y las opciones de limpieza y diarización disponibles en la interfaz. Si se utiliza diarización, configurar previamente el token de lectura y los permisos del modelo. Los límites mínimo y máximo de hablantes son opcionales; no deben ser contradictorios.

Enviar el audio y esperar a que termine el trabajo. El backend devuelve etapa, progreso, duración, resultado o error. Descargar la transcripción TXT cuando se complete. Revisar manualmente los turnos, las etiquetas y las marcas temporales; una etiqueta de hablante no identifica automáticamente al encuestador. La interfaz no fue inspeccionada directamente, por lo que los nombres exactos de sus botones deben confirmarse.

Ante errores, revisar FFmpeg/FFprobe, el entorno Python, acceso al modelo y disponibilidad de memoria. Si CUDA no está disponible, el código contempla CPU. Para detener el servidor local, usar Ctrl+C en la terminal.

## Data Audit

Preparar PostgreSQL, cargar configuración y diccionarios según la guía de instalación. Ejecutar `python -m qa.cli bases` desde `backend` con el entorno correspondiente para consultar bases disponibles. Ejecutar `python -m qa.cli procesar --base DETENIDOS --archivo RUTA --anio 2026 --mes 10` (ajustar identificador, periodo y ruta).

La carpeta de salida documentada por defecto es `almacen`. Cada carga puede contener `original.*`, `corregido.xlsx`, `bitacora.xlsx` y `reporte.json`. Revisar las hojas Resumen, Hallazgos, Cambios aplicados, Sugerencias y Excluidos. No publicar el original. Las sugerencias requieren aprobación técnica; no se ha verificado una interfaz de aprobación. Conservar evidencia de las decisiones y validar la salida antes de su uso estadístico.

## Data Audit en la plataforma

1. **Nueva auditoría:** elige la base, el año y el mes, y sube el archivo (XLSX, XLS o CSV). El encabezado se ubica solo, aunque el archivo traiga títulos encima o venga en CSV.
2. **Detalle de la auditoría:** al terminar se abre con el puntaje, los registros, los puntajes por dimensión, los hallazgos (filtrables por severidad), los registros excluidos y los archivos guardados (original, base corregida, bitácora y reporte). La descarga del original queda registrada.
3. **Correcciones sugeridas:** cada valor que no existe en el catálogo aparece en la bandeja. Se aprueba la sugerencia, se elige otro código buscando en el catálogo (también cuando no hubo sugerencia) o se rechaza con un motivo. Un valor rechazado no se vuelve a proponer.
4. **Aplicar correcciones aprobadas:** vuelve a validar el mismo archivo y genera una base corregida nueva con lo aprobado.
5. **Decisión técnica:** aprobar o rechazar la base, con un comentario.
6. **Bases subidas:** historial de todas las auditorías (filtrable por base y estado) para volver a abrir cualquiera.
7. **Correcciones guardadas:** cada corrección aprobada queda guardada para la institución y se aplica sola en las siguientes bases. Se puede buscar y quitar.

## Operación desde la interfaz común

Usar [el recorrido integrado](interfaz.md#recorrido-de-usuario) para formularios, reproducción, filtro de severidad, descargas y cancelación de espera. El modo demo solo muestra ejemplos. El modo API usa la API unificada (`/api/*`) y, en el despliegue, pide iniciar sesión con una cuenta creada por el equipo.
