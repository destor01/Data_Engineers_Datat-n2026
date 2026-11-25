"""Sections A1 and A2 of the ENCOVI 2023 rules file, written as Jev questions.

Source of every rule: Manual del Encuestador ENCOVI 2023 (INE Guatemala); `pages` are the
printed pages. Weights are a proposal (3 = protects the informant or the validity of the data,
2 = explicit procedure, 1 = example or courtesy detail); agree on them before looking at results.
Speaker names in the questions match the labels in the transcript state: ENCUESTADOR, INFORMANTE.
"""
from __future__ import annotations

from rules import Instruction, Kind, Scope, Section, noul, tri_choice

OBL, PRO, CON, EVI = Kind.OBLIGATION, Kind.PROHIBITION, Kind.CONDITIONAL, Kind.EVIDENCE
OPEN, CLOSE, ALL = Scope.OPENING, Scope.CLOSING, Scope.ALL


def _ins(section, id_, text, pages, kind, scope, questions, weight=1, verif="alta", note=""):
    qs = tuple(questions) if isinstance(questions, (list, tuple)) else (questions,)
    return Instruction(id_, section, text, pages, kind, scope, qs, weight, verif, note)


# Shared by A1-04 and A1-09 (asked once, used by both).
Q_PROPOSITO = noul(
    "A1_04_proposito",
    "Al presentar la encuesta, antes de las preguntas del cuestionario, el ENCUESTADOR explica que es una "
    "encuesta para conocer o medir las condiciones de vida de los hogares.",
    true="Explica el propósito con frases como «conocer las condiciones de vida de los hogares» o nombra la "
         "«Encuesta Nacional de Condiciones de Vida».",
    false="Pide información sin decir para qué es, o da una razón que no tiene que ver con las condiciones "
          "de vida de los hogares.",
)

# --------------------------------------------------------------------------------------------
# A1 — Apertura y contacto inicial
# --------------------------------------------------------------------------------------------
A1_RULES = [
    _ins("A1", "A1-01", "Saludar amablemente", "p.39", OBL, OPEN, noul(
        "A1_01_saludo",
        "El ENCUESTADOR saluda amablemente al iniciar el contacto con el hogar.",
        true="Saluda con cortesía (por ejemplo, «buenos días», «buenas tardes», «¿cómo está?») antes de pedir información.",
        false="Empieza a pedir información o a preguntar sin saludar, o saluda de forma brusca o cortante."),
        weight=2),

    _ins("A1", "A1-02", "Decir su nombre y que es encuestador(a) del INE", "p.39", OBL, OPEN, [
        noul("A1_02_nombre",
             "El ENCUESTADOR dice su propio nombre al presentarse.",
             true="Dice su nombre (por ejemplo, «mi nombre es…», «me llamo…»).",
             false="Se presenta solo por su cargo o su institución, o no se presenta."),
        noul("A1_02_ine",
             "El ENCUESTADOR dice que es encuestador(a) del Instituto Nacional de Estadística (INE).",
             true="Dice que viene del INE o del Instituto Nacional de Estadística, o que es encuestador(a) del INE.",
             false="En ningún momento dice para qué institución trabaja.")],
        weight=2),

    _ins("A1", "A1-03", "Entregar la carta de presentación", "p.39", EVI, OPEN, tri_choice(
        "A1_03_carta",
        "¿Qué muestra el fragmento sobre la carta de presentación del INE que el ENCUESTADOR debe entregar al hogar?",
        followed=("entrega_la_carta",
                  "El ENCUESTADOR entrega, muestra o menciona que deja la carta de presentación del INE."),
        broken=("no_entrega_la_carta",
                "El INFORMANTE pide una carta o un documento de presentación y el ENCUESTADOR dice que no lo "
                "tiene o no lo entrega."),
        unknown=("carta_no_mencionada",
                 "Nadie menciona ninguna carta ni documento de presentación en el fragmento.")),
        weight=2, verif="media", note="Entregar la carta puede ser un acto silencioso: sin mención, no se juzga."),

    _ins("A1", "A1-04", "Explicar en forma concisa y clara el propósito: medir las condiciones de vida de los "
         "hogares, “Encuesta Nacional de Condiciones de Vida”", "p.39", OBL, OPEN, Q_PROPOSITO, weight=2),

    _ins("A1", "A1-05", "Decir que el hogar fue seleccionado con base en una muestra estadística", "p.39",
         OBL, OPEN, noul(
        "A1_05_muestra",
        "Al presentar la encuesta, el ENCUESTADOR dice que el hogar o la vivienda fue seleccionada por medio de "
        "una muestra estadística.",
        true="Dice que la vivienda u hogar salió seleccionado en una muestra o por muestreo estadístico.",
        false="No explica cómo se eligió el hogar, o da otra razón (por ejemplo, que alguien lo recomendó o que "
              "es beneficiario de un programa)."),
        weight=1, note="Elemento del modelo de presentación de p.39, que el manual da como ejemplo («podría ser»)."),

    _ins("A1", "A1-06", "Pedir la colaboración de todas las personas del hogar", "p.39", OBL, OPEN, [
        noul("A1_06_colaboracion",
             "Antes de empezar las preguntas del cuestionario, el ENCUESTADOR pide la colaboración del INFORMANTE "
             "para responder la encuesta.",
             true="Pide colaboración, participación o permiso para hacer la encuesta (por ejemplo, «requerimos de "
                  "su valiosa colaboración»).",
             false="Empieza a preguntar sin pedir colaboración ni permiso."),
        noul("A1_06_todo_el_hogar",
             "Al pedir colaboración, el ENCUESTADOR dice que se necesita la de todas las personas del hogar, no "
             "solo la del INFORMANTE.",
             true="Menciona a las demás personas o miembros del hogar al pedir colaboración.",
             false="Solo se dirige a la persona que lo atiende, sin mencionar a los demás miembros del hogar.")],
        weight=2),

    _ins("A1", "A1-07", "Hacer ver la importancia de la encuesta para el país", "p.39", OBL, OPEN, noul(
        "A1_07_importancia_pais",
        "Al presentar la encuesta, el ENCUESTADOR explica que es importante para el país.",
        true="Menciona la importancia de la encuesta para Guatemala, para el país o para conocer la situación de "
             "muchos guatemaltecos.",
        false="No dice por qué la encuesta es importante, o solo dice que es obligatoria o un requisito."),
        weight=1, note="Elemento del modelo de presentación de p.39, que el manual da como ejemplo («podría ser»)."),

    _ins("A1", "A1-08", "Hacer ver la importancia de que las personas con discapacidad del hogar colaboren",
         "p.39", OBL, OPEN, noul(
        "A1_08_discapacidad",
        "Al presentar la encuesta, el ENCUESTADOR dice que es importante que las personas con discapacidad del "
        "hogar también colaboren.",
        true="Menciona expresamente a las personas con discapacidad del hogar y pide o valora su participación.",
        false="Habla de la encuesta y de la colaboración sin mencionar a las personas con discapacidad."),
        weight=2),

    _ins("A1", "A1-09", "Mencionar los objetivos de la encuesta y los patrocinadores", "p.39", OBL, OPEN, [
        Q_PROPOSITO,
        noul("A1_09_patrocinadores",
             "Al presentar la encuesta, el ENCUESTADOR dice qué institución o instituciones la realizan o "
             "patrocinan.",
             true="Nombra a quién realiza o patrocina la encuesta (por ejemplo, «es una encuesta del INE» o «con el "
                  "apoyo de…»).",
             false="Pide colaboración sin decir quién está detrás de la encuesta.")],
        weight=1, note="Objetivos = la misma pregunta que A1-04. El manual no nombra patrocinadores aparte del INE; "
                       "su equipo decide si basta con nombrar al INE."),

    _ins("A1", "A1-10", "Informar que la información es estrictamente confidencial (Ley Orgánica del INE, "
         "Decreto 3-85, art. 25)", "pp.39, 41", OBL, OPEN, noul(
        "A1_10_confidencial",
        "Al presentar la encuesta, antes de las preguntas del cuestionario, el ENCUESTADOR dice que la "
        "información que dé el hogar es confidencial.",
        true="Dice que los datos son confidenciales o que no se publican de forma individual; citar la Ley Orgánica "
             "del INE o el Decreto 3-85 cuenta, pero no es necesario.",
        false="Presenta la encuesta sin hablar de confidencialidad, o solo lo hace más tarde, cuando el INFORMANTE "
              "lo pregunta."),
        weight=3),

    _ins("A1", "A1-11", "Informar que la información se usa solo con fines estadísticos", "pp.39, 41",
         OBL, OPEN, noul(
        "A1_11_fines_estadisticos",
        "Al presentar la encuesta, antes de las preguntas del cuestionario, el ENCUESTADOR dice que la "
        "información se usará solo con fines estadísticos.",
        true="Dice que los datos se usan únicamente para estadísticas o con fines estadísticos.",
        false="Presenta la encuesta sin decir para qué se usará la información, menciona otros usos o solo lo "
              "aclara más tarde."),
        weight=3),

    _ins("A1", "A1-12", "Informar sobre las dos rondas", "p.40", OBL, OPEN, noul(
        "A1_12_dos_rondas",
        "Antes de empezar las preguntas del cuestionario, el ENCUESTADOR informa que la encuesta se hace en dos "
        "visitas o rondas.",
        true="Dice que regresará otro día o que la entrevista se hace en dos rondas o visitas.",
        false="No menciona la segunda visita antes de las preguntas, o solo la menciona al despedirse."),
        weight=2),

    _ins("A1", "A1-13", "Ante el primer informante: explicar de nuevo el objetivo, pedir su colaboración e informar "
         "sobre las dos rondas", "p.40", CON, OPEN, tri_choice(
        "A1_13_primer_informante",
        "Cuando empieza a entrevistar al primer INFORMANTE, ¿el ENCUESTADOR le vuelve a presentar la encuesta?",
        unknown=("mismo_informante",
                 "El primer INFORMANTE es la misma persona que recibió la presentación inicial; no se incorpora "
                 "nadie nuevo."),
        followed=("vuelve_a_presentar",
                  "Se incorpora una persona nueva como primer INFORMANTE y el ENCUESTADOR le explica de nuevo de qué "
                  "se trata la encuesta y le pide su colaboración."),
        broken=("no_vuelve_a_presentar",
                "Se incorpora una persona nueva como primer INFORMANTE y el ENCUESTADOR le empieza a preguntar sin "
                "explicarle la encuesta ni pedirle su colaboración.")),
        weight=2),

    _ins("A1", "A1-14", "Pedir hablar con el jefe(a) del hogar o su esposa(o)/compañera(o); si no están, con una "
         "persona responsable residente del hogar", "p.39", OBL, OPEN, noul(
        "A1_14_informante_inicial",
        "El ENCUESTADOR pide hablar con el jefe o la jefa del hogar o con su pareja, o comprueba que la persona "
        "que lo atiende es una de ellas o una persona responsable que vive en el hogar.",
        true="Pregunta por el jefe(a) del hogar o su pareja (por ejemplo, «¿se encuentra el jefe de hogar?», «¿usted "
             "es la señora de la casa?»), o pregunta si la persona vive en el hogar y puede responder.",
        false="Empieza la entrevista con la persona que abrió sin preguntar quién es ni si vive en el hogar."),
        weight=2),

    _ins("A1", "A1-15", "NO aceptar información de trabajadores domésticos, menores de edad ni personas de otros "
         "hogares (salvo la información propia de cada uno)", "p.39", PRO, ALL, noul(
        "A1_15_informante_no_valido",
        "El ENCUESTADOR acepta información sobre el hogar o sobre otros miembros dada por una trabajadora o "
        "trabajador doméstico, un menor de edad o una persona que no vive en el hogar.",
        true="Una empleada doméstica, un niño, niña o adolescente, o un vecino o visita responde por el hogar o por "
             "otros miembros, y el ENCUESTADOR acepta esas respuestas.",
        false="Responden miembros adultos del hogar, o esas personas solo dan su propia información."),
        weight=3),

    _ins("A1", "A1-16", "Con varios hogares en la vivienda, hablar primero con el hogar principal", "p.62",
         CON, OPEN, tri_choice(
        "A1_16_hogar_principal",
        "Si en la vivienda viven varios hogares (grupos que preparan sus comidas por separado y no comparten "
        "gastos), ¿con cuál habla primero el ENCUESTADOR?",
        unknown=("un_solo_hogar", "En el fragmento no aparece que en la vivienda vivan varios hogares."),
        followed=("primero_hogar_principal",
                  "Hay varios hogares y el ENCUESTADOR habla primero con el hogar principal (por lo general el del "
                  "dueño de la vivienda) para que informe sobre los demás."),
        broken=("primero_otro_hogar",
                "Hay varios hogares y el ENCUESTADOR empieza con un hogar que no es el principal.")),
        weight=2),

    _ins("A1", "A1-17", "Si el informante pide ampliar la información: NO dar datos que desconozca; explicar que la "
         "encuesta es nacional (urbana y rural) para conocer los niveles de vida", "p.40", CON, ALL, tri_choice(
        "A1_17_ampliar_informacion",
        "Si el INFORMANTE pide más información sobre la encuesta, ¿cómo responde el ENCUESTADOR?",
        unknown=("no_pide_mas_informacion", "El INFORMANTE no pide más información sobre la encuesta."),
        followed=("amplia_sin_inventar",
                  "El INFORMANTE pide más información y el ENCUESTADOR explica que la encuesta se hace en todo el "
                  "país, en áreas urbanas y rurales, para conocer los niveles de vida, sin inventar datos."),
        broken=("da_datos_dudosos",
                "El INFORMANTE pide más información y el ENCUESTADOR da datos dudosos o inventados (beneficios, "
                "fechas, resultados) o no responde a lo que se le pregunta.")),
        weight=2),

    _ins("A1", "A1-18", "Dar el teléfono de la oficina departamental, la Dirección Técnica o las oficinas centrales "
         "del INE y pedir que llame para verificar", "p.40", CON, ALL, tri_choice(
        "A1_18_telefono_verificar",
        "Si el INFORMANTE pide más información o quiere asegurarse de que la encuesta es real, ¿el ENCUESTADOR le "
        "da un teléfono del INE para que llame y verifique?",
        unknown=("no_pide_verificar",
                 "El INFORMANTE no pide más información ni duda de que la encuesta sea real."),
        followed=("da_telefono_del_ine",
                  "El INFORMANTE pide más información o duda, y el ENCUESTADOR le da o le ofrece el teléfono de una "
                  "oficina del INE para que llame y verifique."),
        broken=("no_da_telefono",
                "El INFORMANTE pide más información o duda, y el ENCUESTADOR no le ofrece ningún teléfono del INE.")),
        weight=1, note="En el manual va en el mismo párrafo que A1-17 (si el informante pide ampliar la "
                       "información); por eso se modela como condicional."),

    _ins("A1", "A1-19", "Ante renuencia: leer algunas preguntas como ejemplo para dar confianza", "p.40",
         CON, ALL, tri_choice(
        "A1_19_renuencia",
        "Si el INFORMANTE se muestra renuente a dar la entrevista, ¿el ENCUESTADOR le lee algunas preguntas como "
        "ejemplo para darle confianza?",
        unknown=("sin_renuencia", "El INFORMANTE acepta la entrevista sin resistirse."),
        followed=("lee_preguntas_de_ejemplo",
                  "El INFORMANTE duda o se resiste y el ENCUESTADOR le lee algunas preguntas del cuestionario como "
                  "ejemplo."),
        broken=("no_lee_ejemplos",
                "El INFORMANTE duda o se resiste y el ENCUESTADOR no le lee ninguna pregunta de ejemplo.")),
        weight=1),

    _ins("A1", "A1-20", "Si pregunta por qué o cómo fue seleccionado: explicar que la vivienda se eligió en la "
         "oficina con base en el Censo 2018, por muestreo", "p.40", CON, ALL, tri_choice(
        "A1_20_por_que_seleccionado",
        "Si el INFORMANTE pregunta por qué o cómo fue seleccionado su hogar, ¿qué responde el ENCUESTADOR?",
        unknown=("no_pregunta_seleccion", "El INFORMANTE no pregunta por qué ni cómo fue seleccionado su hogar."),
        followed=("explica_muestreo",
                  "El INFORMANTE lo pregunta y el ENCUESTADOR explica que la vivienda se seleccionó en la oficina, "
                  "por muestreo, con base en el Censo 2018 (puede usar un ejemplo, como el del bulto de arroz)."),
        broken=("no_explica_muestreo",
                "El INFORMANTE lo pregunta y el ENCUESTADOR no lo explica, dice que no sabe o da otra razón (por "
                "ejemplo, que alguien lo recomendó).")),
        weight=2),

    _ins("A1", "A1-21", "Si sugiere que su vecino informe mejor: aclarar amablemente que el encuestador está "
         "obligado a entrevistar la vivienda asignada", "p.40", CON, ALL, tri_choice(
        "A1_21_vecino",
        "Si el INFORMANTE sugiere que el ENCUESTADOR entreviste a un vecino o a otra vivienda, ¿cómo responde el "
        "ENCUESTADOR?",
        unknown=("no_sugiere_vecino", "El INFORMANTE no sugiere entrevistar a otra persona ni a otra vivienda."),
        followed=("aclara_vivienda_asignada",
                  "El INFORMANTE lo sugiere y el ENCUESTADOR le aclara con amabilidad que debe entrevistar esta "
                  "vivienda porque es la que le asignaron."),
        broken=("acepta_ir_con_vecino",
                "El INFORMANTE lo sugiere y el ENCUESTADOR acepta ir con el vecino, o no le aclara que debe "
                "entrevistar esta vivienda.")),
        weight=2),

    _ins("A1", "A1-22", "NO sustituir la vivienda asignada por otra", "p.22", PRO, ALL, noul(
        "A1_22_sustituye_vivienda",
        "El ENCUESTADOR decide o propone entrevistar otra vivienda u otro hogar en lugar del que le asignaron.",
        true="Dice que irá a otra casa, que entrevistará al vecino en su lugar o que cambiará de vivienda porque en "
             "esta no lo atienden.",
        false="El ENCUESTADOR solo habla de entrevistar la vivienda y el hogar donde está."),
        weight=3, verif="baja", note="La sustitución casi nunca se dice en voz alta; se confirma con el listado (D-05)."),

    _ins("A1", "A1-23", "Ante rechazo: INSISTIR lo necesario", "p.22", CON, ALL, tri_choice(
        "A1_23_rechazo",
        "Si el INFORMANTE rechaza la entrevista, ¿insiste el ENCUESTADOR para conseguirla?",
        unknown=("sin_rechazo", "El INFORMANTE no rechaza la entrevista."),
        followed=("insiste_con_respeto",
                  "El INFORMANTE la rechaza y el ENCUESTADOR insiste con respeto: explica la importancia o la "
                  "confidencialidad, o propone otro momento."),
        broken=("acepta_el_rechazo",
                "El INFORMANTE la rechaza y el ENCUESTADOR acepta el rechazo de inmediato, sin insistir ni proponer "
                "otro momento.")),
        weight=2, note="Insistir no es presionar: la presión se evalúa en A2-11."),

    _ins("A1", "A1-24", "Ante desconfianza sobre el uso de los datos (p. ej. “no será que esto lo quieren para la "
         "SAT”): re-explicar que es confidencial, solo estadística, y para qué sirve", "pp.19, 407", CON, ALL,
         tri_choice(
        "A1_24_desconfianza_datos",
        "Si el INFORMANTE desconfía del uso que se dará a sus datos (impuestos, SAT, programas, gobierno), ¿cómo "
        "responde el ENCUESTADOR?",
        unknown=("sin_desconfianza", "El INFORMANTE no expresa desconfianza sobre el uso de sus datos."),
        followed=("reexplica_confidencialidad",
                  "El INFORMANTE desconfía y el ENCUESTADOR le explica de nuevo que la información es confidencial, "
                  "que solo se usa con fines estadísticos y para qué sirve la encuesta."),
        broken=("no_aclara_uso",
                "El INFORMANTE desconfía y el ENCUESTADOR ignora la preocupación, cambia de tema o responde sin "
                "aclarar la confidencialidad ni el uso estadístico.")),
        weight=3),
]

# --------------------------------------------------------------------------------------------
# A2 — Conducta y actitud
# --------------------------------------------------------------------------------------------
A2_RULES = [
    _ins("A2", "A2-01", "Mantener una conducta amable y cordial, pero formal", "p.18", PRO, ALL, [
        noul("A2_01_descortes",
             "El ENCUESTADOR trata al INFORMANTE de forma descortés: brusca, impaciente, sarcástica o grosera.",
             true="Responde de mal modo, se burla, regaña, levanta el tono o usa palabras despectivas.",
             false="Trata al INFORMANTE con amabilidad y respeto en todo el fragmento."),
        noul("A2_01_informal",
             "El ENCUESTADOR pierde la formalidad con el INFORMANTE: dice groserías, hace bromas fuera de lugar o "
             "comentarios demasiado personales.",
             true="Dice malas palabras, hace bromas de doble sentido o sobre la persona, coquetea o comenta asuntos "
                  "personales ajenos a la encuesta.",
             false="Mantiene un trato cordial y respetuoso; un saludo amistoso o una broma leve no cuentan.")],
        weight=2),

    _ins("A2", "A2-02", "Mostrar seguridad; NO parecer nervioso, inseguro ni asustadizo", "pp.40, 42", PRO, ALL, noul(
        "A2_02_inseguro",
        "El ENCUESTADOR se muestra nervioso o inseguro al conducir la entrevista.",
        true="Duda una y otra vez sobre qué preguntar o cómo seguir, se disculpa en exceso, se contradice, se pierde "
             "en el cuestionario o le pide al INFORMANTE que le diga qué hacer.",
        false="Conduce la entrevista con fluidez; las pausas normales para leer o anotar no cuentan."),
        weight=1, verif="media", note="El tono de voz no queda en la transcripción."),

    _ins("A2", "A2-03", "NO dar la impresión de ser importante por ser del Estado; NO ser autoritario ni agresivo",
         "p.41", PRO, ALL, [
        noul("A2_03_presume_cargo",
             "El ENCUESTADOR presume de ser del Estado o de su cargo para imponerse al INFORMANTE.",
             true="Usa frases como «soy del gobierno», «usted me tiene que contestar» o se presenta como una "
                  "autoridad para exigir respuestas.",
             false="Menciona al INE solo para presentarse o para explicar la encuesta."),
        noul("A2_03_autoritario",
             "El ENCUESTADOR se comporta de forma autoritaria o agresiva con el INFORMANTE.",
             true="Da órdenes, exige respuestas, amenaza, grita o descalifica al INFORMANTE.",
             false="Pide la información con respeto, aunque insista o repita una pregunta.")],
        weight=2),

    _ins("A2", "A2-04", "Usar un lenguaje semejante al del entrevistado", "p.42", PRO, ALL, noul(
        "A2_04_lenguaje_no_adaptado",
        "El ENCUESTADOR usa palabras técnicas o difíciles que el INFORMANTE no entiende y no las explica con "
        "palabras sencillas.",
        true="El INFORMANTE muestra que no entiende un término (pregunta qué significa o responde otra cosa) y el "
             "ENCUESTADOR lo repite igual o sigue sin explicarlo.",
        false="El INFORMANTE entiende las preguntas, o el ENCUESTADOR explica con palabras sencillas lo que no se "
              "entendió, sin cambiar su sentido."),
        weight=1, verif="media"),

    _ins("A2", "A2-05", "Mostrar simpatía, sensibilidad e interés por el informante", "p.42", PRO, ALL, noul(
        "A2_05_insensible",
        "El ENCUESTADOR se muestra frío o insensible ante algo difícil que cuenta el INFORMANTE.",
        true="El INFORMANTE cuenta una situación difícil (enfermedad, muerte, pobreza, violencia) y el ENCUESTADOR "
             "la ignora y sigue de forma mecánica, o hace un comentario insensible.",
        false="El ENCUESTADOR reconoce con una frase breve lo que cuenta el INFORMANTE, o en el fragmento no surge "
              "ninguna situación difícil."),
        weight=1, verif="media"),

    _ins("A2", "A2-06", "Referirse solo a los temas de la encuesta", "p.42", PRO, ALL, noul(
        "A2_06_temas_ajenos",
        "El ENCUESTADOR habla de temas ajenos a la encuesta.",
        true="Habla de asuntos personales suyos, ofrece ventas o servicios, o conversa de temas que no tienen que ver "
             "con la encuesta.",
        false="Todo lo que dice el ENCUESTADOR es sobre la encuesta, su aplicación o la cortesía básica."),
        weight=1),

    _ins("A2", "A2-07", "Evitar conversaciones o actitudes que puedan generar discusión", "p.42", PRO, ALL, noul(
        "A2_07_discute",
        "El ENCUESTADOR discute o polemiza con el INFORMANTE.",
        true="Le lleva la contraria con insistencia, defiende opiniones propias o responde de forma que provoca una "
             "discusión.",
        false="Cuando hay desacuerdo, aclara con calma o vuelve a la pregunta sin entrar en discusión."),
        weight=2),

    _ins("A2", "A2-08", "NO promover discusiones políticas, religiosas ni de otra índole, ni antes, ni durante, ni "
         "después de la entrevista", "p.20", PRO, ALL, noul(
        "A2_08_politica_religion",
        "El ENCUESTADOR inicia o alimenta una conversación sobre política o religión.",
        true="Opina sobre partidos, candidatos, el gobierno, iglesias o creencias, o sigue una conversación así en "
             "lugar de volver a la encuesta.",
        false="No habla de política ni de religión; si el INFORMANTE saca el tema, no opina y vuelve a la encuesta."),
        weight=3),

    _ins("A2", "A2-09", "NO dar información de la que no tenga plena seguridad", "p.42", PRO, ALL, noul(
        "A2_09_informacion_insegura",
        "El ENCUESTADOR afirma cosas sobre la encuesta o sus consecuencias de las que no puede estar seguro.",
        true="Afirma cosas sobre beneficios, programas, plazos o resultados que no son parte de la explicación de la "
             "encuesta (por ejemplo, «con esto le van a dar una ayuda», «los resultados salen el mes que viene»).",
        false="Se limita a explicar la encuesta, o dice que no sabe o que lo consultará cuando no conoce la respuesta."),
        weight=2, verif="media"),

    _ins("A2", "A2-10", "NO crear falsas expectativas ni hacer ofrecimientos o promesas para ganarse la cooperación",
         "pp.20, 42", PRO, ALL, noul(
        "A2_10_promesas",
        "El ENCUESTADOR ofrece o promete algo al INFORMANTE para conseguir que colabore.",
        true="Promete o insinúa ayudas, programas, regalos, dinero o mejoras para la comunidad a cambio de responder "
             "(por ejemplo, «si contesta, a lo mejor le sale un programa»).",
        false="Pide la colaboración explicando la importancia y la confidencialidad de la encuesta, sin ofrecer nada a "
              "cambio."),
        weight=3),

    _ins("A2", "A2-11", "NO presionar al informante", "p.20", PRO, ALL, noul(
        "A2_11_presiona",
        "El ENCUESTADOR presiona o intimida al INFORMANTE para que responda.",
        true="Amenaza con multas, sanciones u otras consecuencias, o exige una respuesta aunque el INFORMANTE no "
             "quiera o no pueda darla.",
        false="Pide la información con respeto; repreguntar de forma neutral (sondeo) o insistir con amabilidad no "
              "es presionar."),
        weight=3),

    _ins("A2", "A2-12", "NO ofrecer copias del cuestionario, otro material ni nada que no esté autorizado", "p.46",
         PRO, ALL, noul(
        "A2_12_ofrece_material",
        "El ENCUESTADOR ofrece al INFORMANTE una copia del cuestionario, de sus respuestas u otro material o cosa.",
        true="Ofrece dejarle copia del cuestionario o de lo que contestó, folletos, fotos o cualquier objeto o servicio.",
        false="Solo entrega o menciona la carta de presentación del INE, o no ofrece nada."),
        weight=2),

    _ins("A2", "A2-13", "Aceptar las respuestas SIN mostrar reacciones personales, juicios ni ideas preconcebidas, ni "
         "sorpresa en el tono de voz", "p.43", PRO, ALL, noul(
        "A2_13_juzga_respuestas",
        "El ENCUESTADOR reacciona a una respuesta del INFORMANTE con un juicio, sorpresa o comentario personal.",
        true="Comenta o juzga lo que responde el INFORMANTE (por ejemplo, «¡tan poco!», «¿en serio?», «eso no puede "
             "ser», «qué mal»).",
        false="Recibe las respuestas de forma neutral (por ejemplo, «muy bien», «gracias», «entiendo») y sigue con la "
              "siguiente pregunta."),
        weight=2, verif="media", note="La sorpresa en el tono de voz no queda en la transcripción."),

    _ins("A2", "A2-14", "Mostrar interés por la información que da el entrevistado", "p.43", PRO, ALL, noul(
        "A2_14_desinteres",
        "El ENCUESTADOR muestra desinterés por lo que responde el INFORMANTE.",
        true="Ignora lo que el INFORMANTE intenta explicar o lo descarta con frases como «sí, sí, lo que sea» o «no "
             "importa, siga».",
        false="Atiende las respuestas y, cuando hace falta, repregunta o confirma lo que entendió."),
        weight=1, verif="media", note="Volver a hacer una pregunta ya contestada es correcto según el manual "
                                      "(p.43); no cuenta como desinterés."),

    _ins("A2", "A2-15", "Ante interrupciones (un niño, otra persona) o si el informante se retira a otra actividad: NO "
         "mostrar sorpresa ni intervenir con comentarios o indicaciones", "p.43", CON, ALL, tri_choice(
        "A2_15_interrupciones",
        "Cuando la entrevista se interrumpe (interviene un niño u otra persona, o el INFORMANTE se retira a otra "
        "actividad), ¿cómo reacciona el ENCUESTADOR?",
        unknown=("sin_interrupciones", "La entrevista no se interrumpe en el fragmento."),
        followed=("espera_sin_comentar",
                  "Hay una interrupción y el ENCUESTADOR espera o retoma con calma, sin comentar ni dar indicaciones "
                  "sobre la situación."),
        broken=("comenta_la_interrupcion",
                "Hay una interrupción y el ENCUESTADOR muestra sorpresa, se queja, regaña o le dice al INFORMANTE "
                "qué hacer.")),
        weight=1),

    _ins("A2", "A2-16", "Evitar entrevistar en presencia de personas ajenas al hogar", "p.42", CON, ALL, tri_choice(
        "A2_16_personas_ajenas",
        "Si hay personas que no son del hogar presentes durante la entrevista, ¿qué hace el ENCUESTADOR?",
        unknown=("sin_personas_ajenas", "No se nota la presencia de personas ajenas al hogar en el fragmento."),
        followed=("procura_privacidad",
                  "Hay personas ajenas presentes y el ENCUESTADOR procura privacidad: espera, pide seguir a solas o "
                  "propone volver en otro momento."),
        broken=("sigue_con_ajenos",
                "Hay personas ajenas (vecinos, visitas) que escuchan o intervienen y el ENCUESTADOR sigue "
                "preguntando sin buscar privacidad.")),
        weight=1, verif="media"),

    _ins("A2", "A2-17", "NO llevar acompañantes ajenos al equipo de trabajo a la entrevista", "p.19", PRO, ALL, noul(
        "A2_17_acompanante",
        "El ENCUESTADOR está acompañado por alguien que no es del equipo del INE.",
        true="El ENCUESTADOR presenta o menciona a un acompañante que no es del INE (un familiar, un amigo, un líder "
             "comunitario), o esa persona interviene en la entrevista.",
        false="El ENCUESTADOR está solo o con personal del INE, como su supervisor."),
        weight=2, verif="baja"),

    _ins("A2", "A2-18", "NO divulgar, repetir ni comentar con otras personas la información que da el informante",
         "p.19", PRO, ALL, noul(
        "A2_18_divulga",
        "El ENCUESTADOR comenta información de otros hogares o repite a terceros lo que contestó un informante.",
        true="Cuenta lo que respondió otra familia o persona (por ejemplo, «su vecina me dijo que…») o repite a otras "
             "personas presentes lo que contestó el INFORMANTE.",
        false="No menciona información de otros hogares ni comparte las respuestas del INFORMANTE con terceros."),
        weight=3),

    _ins("A2", "A2-19", "Referirse a la persona por su nombre durante la entrevista", "pp.77, 163", PRO, ALL, noul(
        "A2_19_sin_nombre",
        "El ENCUESTADOR se refiere a los miembros del hogar sin usar su nombre, aunque ya lo conoce.",
        true="Ya registró los nombres y aun así pregunta una y otra vez por las personas como «él», «la niña», «su "
             "esposo» o «la persona 3».",
        false="Usa el nombre de cada persona al preguntar por ella, o todavía no se han registrado los nombres."),
        weight=1),

    _ins("A2", "A2-20", "Animar al entrevistado con frases discretas de entusiasmo, comprensión e interés", "p.45",
         PRO, ALL, noul(
        "A2_20_sin_animo",
        "El ENCUESTADOR conduce el fragmento de forma mecánica, sin ninguna frase de ánimo, comprensión o interés.",
        true="Encadena preguntas sin ninguna frase breve de ánimo o agradecimiento («muy bien», «gracias», «ya casi "
             "terminamos», «entiendo») en todo el fragmento.",
        false="Usa de vez en cuando frases breves de ánimo, agradecimiento o comprensión."),
        weight=1),

    _ins("A2", "A2-21", "Dar al informante el tiempo necesario para responder", "p.45", PRO, ALL, noul(
        "A2_21_apura",
        "El ENCUESTADOR interrumpe o apura al INFORMANTE mientras responde.",
        true="Lo corta antes de que termine, responde por él o lo apura (por ejemplo, «rápido», «dígame solo sí o "
             "no») cuando todavía está pensando.",
        false="Espera a que el INFORMANTE termine de responder antes de seguir."),
        weight=2, verif="media", note="Las interrupciones solo se ven si la transcripción marca los turnos cortados."),

    _ins("A2", "A2-22", "Si se desvía del tema de la pregunta, reconducirlo amablemente", "p.45", CON, ALL, tri_choice(
        "A2_22_desvio",
        "Si el INFORMANTE se desvía del tema de la pregunta, ¿cómo lo maneja el ENCUESTADOR?",
        unknown=("no_se_desvia", "El INFORMANTE responde a lo que se le pregunta sin desviarse del tema."),
        followed=("reconduce_con_amabilidad",
                  "El INFORMANTE se desvía y el ENCUESTADOR lo devuelve a la pregunta con amabilidad."),
        broken=("no_reconduce_o_corta",
                "El INFORMANTE se desvía y el ENCUESTADOR lo deja seguir sin volver a la pregunta, o lo corta de forma "
                "brusca.")),
        weight=1),

    _ins("A2", "A2-23", "Si manifiesta cansancio o molestia: decirle que la entrevista no tomará mucho más, mantener "
         "buen ritmo y hacer pausas breves si hace falta", "p.45", CON, ALL, tri_choice(
        "A2_23_cansancio",
        "Si el INFORMANTE muestra cansancio o molestia con la entrevista, ¿cómo responde el ENCUESTADOR?",
        unknown=("sin_cansancio", "El INFORMANTE no expresa cansancio ni molestia con la entrevista."),
        followed=("tranquiliza_y_sigue",
                  "El INFORMANTE expresa cansancio o molestia y el ENCUESTADOR le dice que falta poco, mantiene un "
                  "buen ritmo o propone una pausa breve."),
        broken=("ignora_o_suspende",
                "El INFORMANTE expresa cansancio o molestia y el ENCUESTADOR lo ignora, discute con él o suspende "
                "por largo tiempo sin acordar cómo seguir.")),
        weight=1),

    _ins("A2", "A2-24", "Si el informante decide suspender: preguntarle cortésmente cuándo podría atenderlo y acordar "
         "una nueva cita", "p.45", CON, ALL, tri_choice(
        "A2_24_suspension",
        "Si el INFORMANTE decide suspender la entrevista, ¿qué hace el ENCUESTADOR?",
        unknown=("no_suspende", "El INFORMANTE no pide suspender la entrevista."),
        followed=("acuerda_nueva_cita",
                  "El INFORMANTE decide suspender y el ENCUESTADOR le pregunta con cortesía cuándo puede atenderlo y "
                  "acuerdan una nueva cita."),
        broken=("no_acuerda_cita",
                "El INFORMANTE decide suspender y el ENCUESTADOR se va sin acordar una nueva cita, o insiste en "
                "seguir.")),
        weight=2),

    _ins("A2", "A2-25", "Si no es oportuno entrevistar (visitas, enfermedad de un miembro, etc.): regresar en otro "
         "momento", "p.45", CON, ALL, tri_choice(
        "A2_25_momento_inoportuno",
        "Si el momento no es oportuno para entrevistar (hay visitas, alguien del hogar está enfermo u ocurre otra "
        "situación parecida), ¿qué hace el ENCUESTADOR?",
        unknown=("momento_oportuno", "No hay señales de que el momento sea inoportuno para la entrevista."),
        followed=("propone_regresar",
                  "El momento es inoportuno y el ENCUESTADOR propone regresar en otro momento."),
        broken=("sigue_como_si_nada",
                "El momento es inoportuno y el ENCUESTADOR sigue con la entrevista como si nada.")),
        weight=1),

    _ins("A2", "A2-26", "Al terminar: aprovechar la presencia de los informantes para corregir omisiones o "
         "anotaciones incorrectas", "p.45", EVI, CLOSE, tri_choice(
        "A2_26_corrige_antes_de_irse",
        "Al final de la visita, ¿el ENCUESTADOR aprovecha la presencia del INFORMANTE para corregir o completar datos?",
        unknown=("cierre_sin_revision", "En el cierre no se habla de revisar ni de corregir datos."),
        followed=("revisa_y_completa",
                  "Antes de despedirse, el ENCUESTADOR revisa, confirma o completa datos con el INFORMANTE (por "
                  "ejemplo, «antes de irme, déjeme confirmar…»)."),
        broken=("se_va_con_pendientes",
                "El ENCUESTADOR reconoce que falta un dato o hay un error y se despide sin resolverlo con el "
                "INFORMANTE.")),
        weight=1, verif="baja", note="La revisión del formulario es silenciosa; solo se juzga si se habla de ella."),

    _ins("A2", "A2-27", "Terminar dando las gracias y con cortesía", "p.46", OBL, CLOSE, [
        noul("A2_27_agradece",
             "Al terminar la visita, el ENCUESTADOR da las gracias al INFORMANTE.",
             true="Agradece el tiempo o la información (por ejemplo, «muchas gracias por su tiempo»).",
             false="Termina o se retira sin agradecer."),
        noul("A2_27_despedida_cortes",
             "El ENCUESTADOR se despide del INFORMANTE con cortesía.",
             true="Se despide con amabilidad (por ejemplo, «que tenga buen día», «hasta la próxima visita»).",
             false="Se va de forma brusca o sin despedirse.")],
        weight=1),
]

A1 = Section("A1", "Apertura y contacto inicial", tuple(A1_RULES))
A2 = Section("A2", "Conducta y actitud", tuple(A2_RULES))
SECTIONS = (A1, A2)
