/* Shared presentation preferences. UI translations never change project data or permissions. */
(function () {
  "use strict";
  var pairs = [
    ["Project changes are frozen", "Los cambios del proyecto están congelados"],
    [
      "Project changes are frozen. A human must authorize any new work.",
      "Los cambios del proyecto están congelados. Una persona responsable debe autorizar cualquier trabajo nuevo.",
    ],
    [
      "A project freeze is scheduled. Check the deadline before taking new work.",
      "Hay un cierre de cambios programado. Comprueba la fecha límite antes de tomar trabajo nuevo.",
    ],
    [
      "The change window has closed. Review the project with the responsible human before starting new work.",
      "El periodo de cambios terminó. Revisa el proyecto con la persona responsable antes de empezar trabajo nuevo.",
    ],
    ["Language", "Idioma"],
    ["English", "English"],
    ["Español", "Español"],
    ["/ setup", "/ configuración"],
    ["Interface profile", "Perfil de la interfaz"],
    ["Agents online", "Agentes en línea"],
    ["Reviews waiting", "Revisiones pendientes"],
    ["Stalled", "Sin avance"],
    ["Needs a human", "Necesita una persona"],
    ["none in the last 30 min", "ninguno en los últimos 30 min"],
    ["none waiting", "ninguna pendiente"],
    ["every task is moving", "todas las tareas avanzan"],
    ["nothing for you", "nada pendiente para ti"],
    [
      "The pace per day shows up after the first two integrations.",
      "El ritmo diario aparece después de las primeras dos integraciones.",
    ],
    [
      "Nothing needs you right now: no review waiting, nothing stalled, nothing for a human.",
      "No hay acciones pendientes para ti: ninguna revisión, tarea sin avance ni solicitud para una persona.",
    ],
    ["Every agent", "Todos los agentes"],
    ["Every task", "Todas las tareas"],
    ["Every kind", "Todos los tipos"],
    ["Search messages", "Buscar mensajes"],
    [" of ", " de "],
    [" tasks integrated.", " tareas integradas."],
    [
      "% counting the work in review and in progress.",
      "% contando el trabajo en revisión y en curso.",
    ],
    [" oldest ", " más antigua "],
    ["oldest ", "más antigua "],
    ["owner ", "responsable "],
    ["owner away", "responsable ausente"],
    [" waits for review", " espera revisión"],
    [" · offered to ", " · ofrecida a "],
    [" has not moved in ", " no ha avanzado en "],
    [" needs a human", " necesita una persona"],
    ["Integrated per day", "Integraciones por día"],
    [" in the last 7 days · best day ", " en los últimos 7 días · mejor día "],
    ["Integrated per day, best day ", "Integraciones por día, mejor día "],
    [" task", " tarea"],
    [" tasks", " tareas"],
    [" message", " mensaje"],
    [" messages", " mensajes"],
    [" recorded", " registrados"],
    [" in range · peak ", " en el intervalo · máximo "],
    ["Show all ", "Mostrar todas: "],
    ["free to claim", "disponible para tomar"],
    ["after ", "después de "],
    ["stalled ", "sin avance: "],
    ["Recently active", "Actividad reciente"],
    ["active in the last 30 min", "activos en los últimos 30 min"],
    ["seen in the last 3 h", "vistos en las últimas 3 h"],
    ["session ended", "sesión terminada"],
    ["not seen recently", "sin actividad reciente"],
    [
      "agent calls per claim and per done",
      "acciones de agentes por reserva y por entrega",
    ],
    ["newest first", "más recientes primero"],
    ["Map / task", "Mapa / tarea"],
    ["Lens / task", "Contexto / tarea"],
    ["Wait / done", "Espera / entrega"],
    ["Polls / done", "Consultas / entrega"],
    [
      "published by every machine with uak tokens",
      "publicado por cada computadora con uak tokens",
    ],
    ["By task", "Por tarea"],
    ["By harness", "Por herramienta"],
    ["By scope", "Por alcance"],
    ["Messages per hour", "Mensajes por hora"],
    ["Messages per day", "Mensajes por día"],
    ["Messages", "Mensajes"],
    ["Freeze in ", "Cierre en "],
    ["Frozen", "Cambios congelados"],
    ["Snapshot · ", "Captura · "],
    ["Live · ", "En vivo · "],
    [" ago", " antes"],
    [
      "data.js is not being refreshed: run uak dash --watch",
      "data.js no se está actualizando: ejecuta uak dash --watch",
    ],
    ["Refreshes every ", "Se actualiza cada "],
    ["loading…", "cargando…"],
    ["View", "Vista"],
    ["Beginner", "Principiante"],
    ["Advanced", "Avanzado"],
    ["Configuration", "Configuración"],
    ["Dashboard", "Panel del proyecto"],
    ["Skip to setup", "Saltar a la configuración"],
    ["Skip to content", "Saltar al contenido"],
    ["Your team starts here.", "Tu equipo empieza aquí."],
    [
      "A few decisions. A clear next step.",
      "Pocas decisiones. Un siguiente paso claro.",
    ],
    ["Welcome", "Bienvenida"],
    ["Your project", "Tu proyecto"],
    ["Your workflow", "Tu forma de trabajar"],
    ["Review & install", "Revisar e instalar"],
    ["Get ready", "Preparar el proyecto"],
    ["Runs on your computer.", "Se ejecuta en tu computadora."],
    [
      "No account or API key is needed for this setup. Your coding tools keep their own sign-in.",
      "Esta configuración no necesita una cuenta ni una clave API. Tus herramientas de programación conservan su propio inicio de sesión.",
    ],
    [
      "A workspace for your AI coding team",
      "Un espacio para tu equipo de programación con IA",
    ],
    ["Build together.", "Construyan juntos."],
    ["Keep a clear path.", "Con un rumbo claro."],
    [
      "Give your coding agents a shared plan, clear responsibilities, and a review before changes ship. We’ll help you set it up.",
      "Da a tus agentes un plan compartido, responsabilidades claras y una revisión antes de integrar cambios. Te ayudamos a configurarlo.",
    ],
    ["Plan", "Planear"],
    ["Build", "Construir"],
    ["Review", "Revisar"],
    ["Ship", "Integrar"],
    ["One step at a time", "Un paso a la vez"],
    [
      "Choose your project and tools. We explain the decisions as you go.",
      "Elige tu proyecto y tus herramientas. Te explicamos cada decisión.",
    ],
    ["You stay in control", "Tú tienes el control"],
    [
      "Review what will change before anything is installed.",
      "Revisa qué cambiará antes de instalar.",
    ],
    ["Set up my project", "Configurar mi proyecto"],
    [
      "Already using the kit? Choose your project to continue configuration.",
      "¿Ya usas el kit? Elige tu proyecto para continuar la configuración.",
    ],
    ["Where are you building?", "¿Dónde está tu proyecto?"],
    [
      "Choose the folder that contains your Git repository. The kit will live alongside your project.",
      "Elige la carpeta que contiene tu repositorio Git. El kit se instalará junto a tu proyecto.",
    ],
    ["Project folder", "Carpeta del proyecto"],
    [
      "Use the full folder path, for example C:\\Projects\\my-app or /Users/you/my-app.",
      "Usa la ruta completa de la carpeta, por ejemplo C:\\Projects\\mi-app o /Users/tu/mi-app.",
    ],
    [
      "The folder needs to be a Git repository. Nothing is installed when you check it.",
      "La carpeta debe ser un repositorio Git. Comprobarla no instala nada.",
    ],
    ["Back", "Atrás"],
    ["Check project folder", "Comprobar carpeta"],
    ["How will your team work?", "¿Cómo trabajará tu equipo?"],
    ["Choose your goal", "Elige tu objetivo"],
    ["Hackathon or prototype", "Hackathon o prototipo"],
    [
      "Build toward a deadline. Reviewed changes can merge automatically after the checks pass.",
      "Construye con una fecha límite. Los cambios revisados pueden integrarse automáticamente al pasar las comprobaciones.",
    ],
    ["Product with real users", "Producto con usuarios reales"],
    [
      "Plan for security and maintainability. A human makes the final merge decision.",
      "Prioriza la seguridad y el mantenimiento. Una persona decide cuándo integrar los cambios.",
    ],
    [
      "Which coding tools do you use?",
      "¿Qué herramientas de programación usas?",
    ],
    [
      "Select the tools you already use. Setup adds their project instructions; it does not install or sign in to them.",
      "Selecciona las herramientas que ya usas. Se añaden sus instrucciones para el proyecto; no se instalan ni se inicia sesión en ellas.",
    ],
    [
      "I’m the only human on this repository",
      "Soy la única persona en este repositorio",
    ],
    [
      "Agent identities review each other. Product mode still leaves the final merge to you.",
      "Los agentes se revisan entre sí. En modo producto, tú sigues decidiendo la integración final.",
    ],
    ["More installation options", "Más opciones de instalación"],
    ["Project technology preset", "Tecnología del proyecto"],
    ["No preset / decide later", "Sin plantilla / decidir después"],
    ["Python data", "Datos con Python"],
    ["AI agent", "Agente de IA"],
    [
      "Keep anonymous kit diagnostics",
      "Conservar diagnósticos anónimos del kit",
    ],
    [
      "Records filtered kit events on your repository’s coordination branch. Those events are public if your repository is public. You can turn this off here or later.",
      "Registra eventos filtrados del kit en la rama de coordinación de tu repositorio. Son públicos si el repositorio es público. Puedes desactivarlos aquí o después.",
    ],
    ["Review installation", "Revisar instalación"],
    ["A quick check before we install.", "Revisa antes de instalar."],
    [
      "These choices control the files added to your project. You can go back to change them.",
      "Estas elecciones determinan los archivos que se añaden a tu proyecto. Puedes volver y cambiarlas.",
    ],
    ["Project", "Proyecto"],
    ["Workflow", "Forma de trabajo"],
    ["Coding tools", "Herramientas"],
    ["Team", "Equipo"],
    [
      "One human, independent agent reviewers",
      "Una persona, agentes revisores independientes",
    ],
    ["Multiple collaborators", "Varios colaboradores"],
    ["Technology preset", "Plantilla de tecnología"],
    ["Kit diagnostics", "Diagnósticos del kit"],
    [
      "On · stored on your coordination branch",
      "Activados · se guardan en la rama de coordinación",
    ],
    ["Off", "Desactivados"],
    [
      "Adds the kit’s coordination tools, project instructions, hooks and review workflow. Existing files are preserved; conflicting versions are saved beside them as .uak-new.",
      "Añade las herramientas de coordinación, instrucciones, hooks y flujo de revisión del kit. Conserva los archivos existentes; las versiones en conflicto se guardan junto a ellos como .uak-new.",
    ],
    [
      "Installation does not commit or push your code. Signing in to a coding tool and approving your project plan remain separate steps.",
      "La instalación no crea commits ni sube tu código. Iniciar sesión en tus herramientas y aprobar el plan del proyecto son pasos separados.",
    ],
    ["Edit choices", "Editar elecciones"],
    ["Install into this project", "Instalar en este proyecto"],
    ["Repair or update this project", "Reparar o actualizar este proyecto"],
    ["Installing your workspace", "Instalando tu espacio de trabajo"],
    ["Checking your next steps", "Comprobando tus siguientes pasos"],
    [
      "Keep this window open while the kit adds the files. We’ll show you what to do next.",
      "Mantén esta ventana abierta mientras se añaden los archivos. Te mostraremos cómo continuar.",
    ],
    ["Your workspace is ready", "Tu espacio de trabajo está listo"],
    ["Let’s resolve this step", "Vamos a resolver este paso"],
    [
      "The kit is installed. Let’s get ready.",
      "El kit está instalado. Preparemos el proyecto.",
    ],
    [
      "Kit files found. Let’s check your project.",
      "Encontramos el kit. Comprobemos tu proyecto.",
    ],
    ["Continue setting up your project", "Continúa configurando tu proyecto"],
    [
      "This can take a moment. Keep the terminal and this page open.",
      "Puede tardar un momento. Mantén abiertas la terminal y esta página.",
    ],
    [
      "Your project passed the existing readiness checks. Continue with the next action below.",
      "Tu proyecto pasó las comprobaciones del kit. Continúa con el siguiente paso indicado.",
    ],
    [
      "Installation is complete. Your project may still need a plan, a remote connection, or approval before agents can work. You can also repair or update the kit.",
      "La instalación terminó. El proyecto aún puede necesitar un plan, una conexión remota o una aprobación para que trabajen los agentes. También puedes reparar o actualizar el kit.",
    ],
    [
      "Your project may still need a plan, a remote connection, or approval before agents can work. You can also repair or update the kit.",
      "El proyecto aún puede necesitar un plan, una conexión remota o una aprobación para que trabajen los agentes. También puedes reparar o actualizar el kit.",
    ],
    [
      "Review the details below, correct the issue, and try again. Existing files are preserved.",
      "Revisa los detalles, corrige el problema y vuelve a intentarlo. Se conservan tus archivos existentes.",
    ],
    [
      "Working in the background. You can expand technical details below.",
      "Trabajando en segundo plano. Puedes desplegar los detalles técnicos.",
    ],
    ["Ready for the next task.", "Listo para la siguiente tarea."],
    [
      "Next: check what your project needs before starting work.",
      "Siguiente paso: comprueba qué necesita tu proyecto antes de empezar.",
    ],
    ["Project preferences", "Preferencias del proyecto"],
    [
      "Changes stay local until you commit and push your project configuration.",
      "Los cambios son locales hasta que crees un commit y subas la configuración de tu proyecto.",
    ],
    ["Anonymous kit diagnostics", "Diagnósticos anónimos del kit"],
    [
      "Store filtered kit events on the coordination branch. A public repository makes these events public.",
      "Guarda eventos filtrados del kit en la rama de coordinación. Si el repositorio es público, también lo son estos eventos.",
    ],
    ["Automatic usage pacing", "Ajuste automático del consumo"],
    [
      "Adjust agent activity to your available usage allowance.",
      "Ajusta la actividad de los agentes al uso que tengas disponible.",
    ],
    ["Save preferences", "Guardar preferencias"],
    [
      "Preferences saved locally. Run the readiness check again.",
      "Preferencias guardadas localmente. Vuelve a comprobar los requisitos.",
    ],
    ["Technical details", "Detalles técnicos"],
    ["Choose another project", "Elegir otro proyecto"],
    ["Repair or update kit", "Reparar o actualizar el kit"],
    ["Check what’s next", "Comprobar siguiente paso"],
    ["Check again", "Comprobar de nuevo"],
    ["Review choices", "Revisar elecciones"],
    ["No technical output yet.", "Todavía no hay salida técnica."],
    [
      "Open your coding tool in this project. The exact next action is available in Technical details.",
      "Abre tu herramienta de programación en este proyecto. La acción exacta está en Detalles técnicos.",
    ],
    [
      "Keep the terminal open while using setup. Stop it with Ctrl+C when you finish.",
      "Mantén la terminal abierta mientras usas la interfaz. Ciérrala con Ctrl+C cuando termines.",
    ],
    [
      "UPIIXIA Agentic Kit · Your coding team, coordinated.",
      "UPIIXIA Agentic Kit · Tu equipo de programación, coordinado.",
    ],
    ["Return to progress", "Volver al progreso"],
    [
      "An operation is running. You can review earlier steps; editing is available when it finishes.",
      "Hay una operación en curso. Puedes consultar los pasos anteriores; podrás editarlos cuando termine.",
    ],
    [
      "Repair preserves the existing workflow and project configuration.",
      "La reparación conserva el modo de trabajo y la configuración del proyecto.",
    ],
    ["Open dashboard", "Abrir panel del proyecto"],
    [
      "Choose a project to see its dashboard.",
      "Elige un proyecto para ver su panel.",
    ],
    ["Loading your project dashboard…", "Cargando el panel de tu proyecto…"],
    ["Refresh dashboard", "Actualizar panel"],
    [
      "No remote is connected. Showing the local plan.",
      "No hay un repositorio remoto conectado. Se muestra el plan local.",
    ],
    [
      "Coordination could not refresh. Showing the local plan.",
      "No se pudo actualizar la coordinación. Se muestra el plan local.",
    ],
    ["Your project at a glance", "Tu proyecto de un vistazo"],
    ["Your next step", "Tu siguiente paso"],
    ["Connect your repository", "Conecta tu repositorio"],
    [
      "Only the local plan is available. Complete the connection checks in Configuration before starting agents.",
      "Solo está disponible el plan local. Completa las comprobaciones de conexión en Configuración antes de iniciar agentes.",
    ],
    ["Create your first plan", "Crea tu primer plan"],
    [
      "Open your coding tool in this project and describe what you want to build. Its planning workflow will help you create the first tasks.",
      "Abre tu herramienta de programación en este proyecto y describe qué quieres construir. Su flujo de planificación te ayudará a crear las primeras tareas.",
    ],
    ["Resolve the blocked work", "Resuelve el trabajo bloqueado"],
    [
      "Review the tasks marked as blocked to see what the team needs.",
      "Revisa las tareas bloqueadas para saber qué necesita el equipo.",
    ],
    [
      "Review changes before they ship",
      "Revisa los cambios antes de integrarlos",
    ],
    [
      "The team has work waiting for an independent review.",
      "Hay trabajo esperando una revisión independiente.",
    ],
    ["Your team is working", "Tu equipo está trabajando"],
    [
      "Follow progress here. Open Advanced to see conversations, reviews and technical activity.",
      "Sigue el progreso aquí. Abre Avanzado para ver conversaciones, revisiones y actividad técnica.",
    ],
    ["Start the next task", "Empieza la siguiente tarea"],
    [
      "Your plan has available work. Continue in your coding tool to claim a task.",
      "Tu plan tiene trabajo disponible. Continúa en tu herramienta de programación para tomar una tarea.",
    ],
    ["The current plan is complete", "El plan actual está completo"],
    [
      "All active tasks are integrated. Review the result with your team before planning more work.",
      "Todas las tareas activas están integradas. Revisa el resultado con tu equipo antes de planear más trabajo.",
    ],
    ["Tasks", "Tareas"],
    ["Completed", "Terminadas"],
    ["Working", "En curso"],
    ["Waiting for review", "Esperando revisión"],
    ["Board", "Tablero"],
    ["Agents", "Agentes"],
    ["Conversation", "Conversaciones"],
    ["Black box", "Caja negra"],
    ["Memory", "Memoria"],
    ["Tokens", "Tokens"],
    ["Available", "Disponibles"],
    ["In progress", "En curso"],
    ["Blocked", "Bloqueadas"],
    ["In review", "En revisión"],
    ["Integrated", "Integradas"],
    ["No agents yet", "Todavía no hay agentes"],
    [
      "An agent appears here after its first uak command.",
      "Un agente aparece aquí después de su primera acción con el kit.",
    ],
    ["No live task", "Sin tarea activa"],
    ["Nothing blocked", "Sin bloqueos"],
    ["Nobody is on a task", "Nadie está trabajando en una tarea"],
    ["Empty", "Vacío"],
    ["No messages yet", "Todavía no hay mensajes"],
    [
      "Reviews, contracts and replies between agents show up here as they happen.",
      "Aquí aparecen las revisiones, acuerdos y respuestas de los agentes.",
    ],
    ["No messages match", "No hay mensajes que coincidan"],
    [
      "Try another agent, task or kind, or clear the filters.",
      "Prueba otro agente, tarea o tipo, o borra los filtros.",
    ],
    ["Clear filters", "Borrar filtros"],
    ["Show less", "Mostrar menos"],
    ["Show more", "Mostrar más"],
    ["Show the latest 12", "Mostrar las 12 más recientes"],
    ["No events yet", "Todavía no hay eventos"],
    [
      "Kit errors and agent notes land here.",
      "Aquí aparecen los errores del kit y las notas de los agentes.",
    ],
    ["Events by kind", "Eventos por tipo"],
    ["Harness adoption", "Uso de las herramientas"],
    ["Agent notes and kit errors", "Notas de los agentes y errores del kit"],
    ["No usage recorded yet.", "Todavía no hay uso registrado."],
    ["The black box is empty.", "La caja negra está vacía."],
    ["Lessons", "Lecciones"],
    ["No lessons yet", "Todavía no hay lecciones"],
    [
      "What an agent learns the hard way shows up here.",
      "Aquí aparece lo que los agentes aprenden al resolver dificultades.",
    ],
    ["Decisions", "Decisiones"],
    ["No decisions yet", "Todavía no hay decisiones"],
    [
      "Agreed contracts and calls land here.",
      "Aquí aparecen los acuerdos y las decisiones del equipo.",
    ],
    ["Tokens spent", "Tokens consumidos"],
    [
      "No machine has published its spend yet: uak tokens --publish",
      "Ninguna computadora ha publicado su consumo: uak tokens --publish",
    ],
    ["Harness", "Herramienta"],
    ["Claims", "Reservas"],
    ["Time", "Hora"],
    ["Kind", "Tipo"],
    ["What happened", "Qué ocurrió"],
    ["Fix", "Solución"],
    ["Theme", "Tema"],
    ["Auto", "Automático"],
    ["Light", "Claro"],
    ["Dark", "Oscuro"],
    ["Today", "Hoy"],
    ["Yesterday", "Ayer"],
    ["Online", "En línea"],
    ["Away", "Ausentes"],
    ["Offline", "Desconectados"],
    ["Needs attention", "Requiere atención"],
    ["Overview", "Resumen"],
    ["Views", "Vistas"],
    ["All agents", "Todos los agentes"],
    ["All tasks", "Todas las tareas"],
    ["All kinds", "Todos los tipos"],
    [
      "This folder does not exist. Choose an existing project folder.",
      "Esta carpeta no existe. Elige una carpeta de proyecto existente.",
    ],
    [
      "Choose the root of a Git repository. Create the repository first if needed.",
      "Elige la carpeta raíz de un repositorio Git. Si hace falta, crea primero el repositorio.",
    ],
    ["Choose a project first.", "Elige primero un proyecto."],
    [
      "Choose at least one coding tool.",
      "Elige al menos una herramienta de programación.",
    ],
    [
      "An operation is running. Wait for it to finish.",
      "Hay una operación en curso. Espera a que termine.",
    ],
    [
      "The installed kit version differs from this setup. Use Repair or update first so the correct engine checks readiness.",
      "La versión del kit instalado es distinta de esta configuración. Usa Reparar o actualizar para comprobar el proyecto con el motor correcto.",
    ],
    [
      "Installation did not finish. Check details, correct the issue, and retry.",
      "La instalación no terminó. Revisa los detalles, corrige el problema y vuelve a intentarlo.",
    ],
    [
      "The operation stopped. Correct the issue and retry.",
      "La operación se detuvo. Corrige el problema y vuelve a intentarlo.",
    ],
    [
      "This setup session expired. Reopen the address printed in the terminal.",
      "La sesión de configuración caducó. Vuelve a abrir la dirección que aparece en la terminal.",
    ],
    [
      "The action could not finish. Please retry.",
      "No se pudo completar la acción. Vuelve a intentarlo.",
    ],
    ["Passed", "Comprobado"],
    ["Action needed", "Acción necesaria"],
    ["Information", "Información"],
  ];
  var es = Object.create(null),
    en = Object.create(null);
  pairs.forEach(function (pair) {
    es[pair[0]] = pair[1];
    en[pair[1]] = pair[0];
  });
  var language = /^es\b/i.test(navigator.language || "") ? "es" : "en";
  try {
    language = localStorage.getItem("uak-language") || language;
  } catch (e) {}
  if (language !== "es") language = "en";
  var originals = new WeakMap(),
    root = null;
  function translate(value) {
    var text = String(value),
      key = en[text] || text;
    return language === "es" ? es[key] || text : key;
  }
  function format(value, values) {
    return translate(value).replace(/\{([a-z]+)\}/gi, function (match, key) {
      return values && key in values ? String(values[key]) : match;
    });
  }
  function apply(container) {
    if (!container) return;
    var walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT),
      node;
    while ((node = walker.nextNode())) {
      var parent = node.parentElement;
      if (
        !parent ||
        parent.closest("script,style,pre,code,textarea,[data-no-i18n]")
      )
        continue;
      var current = node.nodeValue,
        trimmed = current.trim(),
        normalized = trimmed.replace(/\s+/g, " "),
        original = originals.get(node);
      if (!original || (normalized !== original && normalized !== es[original]))
        original = en[normalized] || normalized;
      if (!(original in es)) continue;
      originals.set(node, original);
      var next = current.replace(trimmed, translate(original));
      if (next !== current) node.nodeValue = next;
    }
    container.querySelectorAll("[data-i18n-aria]").forEach(function (el) {
      el.setAttribute("aria-label", translate(el.dataset.i18nAria));
    });
    document.documentElement.lang = language;
  }
  function setLanguage(value) {
    language = value === "es" ? "es" : "en";
    try {
      localStorage.setItem("uak-language", language);
    } catch (e) {}
    if (root) apply(root);
    window.dispatchEvent(new Event("uak:language"));
  }
  function start(container) {
    root = container;
    apply(root);
    new MutationObserver(function () {
      apply(root);
    }).observe(root, { subtree: true, childList: true, characterData: true });
  }
  window.UAKWorkspace = {
    t: translate,
    format: format,
    apply: apply,
    start: start,
    setLanguage: setLanguage,
    language: function () {
      return language;
    },
    catalog: es,
  };
})();
