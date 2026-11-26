# Manual de usuario

## Audio Audit

Iniciar el servidor según la [instalación](installation.md) y abrir http://127.0.0.1:8000. Utilizar una grabación simulada o autorizada. Seleccionar el modelo y las opciones de limpieza y diarización disponibles en la interfaz. Si se utiliza diarización, configurar previamente el token de lectura y los permisos del modelo. Los límites mínimo y máximo de hablantes son opcionales; no deben ser contradictorios.

Enviar el audio y esperar a que termine el trabajo. El backend devuelve etapa, progreso, duración, resultado o error. Descargar la transcripción TXT cuando se complete. Revisar manualmente los turnos, las etiquetas y las marcas temporales; una etiqueta de hablante no identifica automáticamente al encuestador. La interfaz no fue inspeccionada directamente, por lo que los nombres exactos de sus botones deben confirmarse.

Ante errores, revisar FFmpeg/FFprobe, el entorno Python, acceso al modelo y disponibilidad de memoria. Si CUDA no está disponible, el código contempla CPU. Para detener el servidor local, usar Ctrl+C en la terminal.

## Data Audit

Preparar PostgreSQL, cargar configuración y diccionarios según la guía de instalación. Ejecutar `python -m qa.cli bases` desde `backend` con el entorno correspondiente para consultar bases disponibles. Ejecutar `python -m qa.cli procesar --base DETENIDOS --archivo RUTA --anio 2026 --mes 10` (ajustar identificador, periodo y ruta).

La carpeta de salida documentada por defecto es `almacen`. Cada carga puede contener `original.*`, `corregido.xlsx`, `bitacora.xlsx` y `reporte.json`. Revisar las hojas Resumen, Hallazgos, Cambios aplicados, Sugerencias y Excluidos. No publicar el original. Las sugerencias requieren aprobación técnica; no se ha verificado una interfaz de aprobación. Conservar evidencia de las decisiones y validar la salida antes de su uso estadístico.

## Operación desde la interfaz común

Usar [el recorrido integrado](interfaz.md#recorrido-de-usuario) para formularios, reproducción, filtro de severidad, descargas y cancelación de espera. El modo demo solo muestra ejemplos. El modo API usa los servicios de 8000 y 8001 a través del proxy.
