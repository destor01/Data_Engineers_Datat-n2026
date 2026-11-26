import pilot from '../../survey-audit/templates/pilot.synthetic.json';
import { extensionRequest as api } from './services/extensionsApi';

type Q = { id: string; label: string; type: string; required?: boolean; options?: {code: string; label: string}[];
  visible_when?: {question_id: string; operator: string; value: unknown} };
type Schema = { template_code: string; version: number; questions: Q[] };
type Template = {id: string; status: string; schema: Schema};
type Interview = {id: string; revision: number; status: string; schema: Schema; responses: Record<string, unknown>;
  transcripts: {turns: {id: number; speaker: string; start: number; end: number; text: string}[]}[]};
type Rec = {id: string; institution: string; rule: string; count: number; action: string; source_run_ref: string; rate_reason: string};
type Manual = {id: string; title: string; version: number; status: string; content: string; institution: string};
function node<K extends keyof HTMLElementTagNameMap>(tag: K, text = '') { const el = document.createElement(tag); el.textContent = text; return el; }
function field(parent: HTMLElement, text: string, control: HTMLElement) { const label = node('label', text); label.append(control); parent.append(label); }
function input(type = 'text', value = '') {const el = node('input'); el.type = type; el.value = value; return el;}
function selection(items: [string, string][]) {const el = node('select'); items.forEach(([v,l]) => el.add(new Option(l,v))); return el;}

export function mountExtensions() {
  for (const [id, title] of [['encuestas', 'Survey Audit'], ['mejora', 'Quality Improvement']]) {
    const page = node('section'); page.id = id; page.className = 'page'; page.hidden = true;
    const heading = node('h1', title); heading.id = `${id}Title`; heading.tabIndex = -1; page.setAttribute('aria-labelledby', heading.id);
    const notice = node('p', 'Servicios locales integrados. Usa únicamente datos autorizados; el acceso de producción está pendiente.'); notice.className = 'pilot-note';
    const status = node('p'); status.setAttribute('role', 'status');
    const toolbar = node('div'); toolbar.className = 'form-actions'; const content = node('div');
    page.append(heading, notice, status, toolbar, content); document.querySelector('main')!.append(page);
    const link = node('a', title); link.href = `#${id}`; link.dataset.nav = id; document.querySelector('nav')!.append(link);
    function action(parent: HTMLElement, label: string, run: () => Promise<void> | void) {
      const b = node('button', label); b.type = 'button'; b.className = 'button secondary'; parent.append(b);
      b.onclick = async () => {b.disabled = true; status.textContent = 'Procesando…'; status.classList.remove('error');
        try {await run(); if (status.textContent === 'Procesando…') status.textContent = 'Operación completada.';}
        catch (e) {status.textContent = e instanceof Error ? e.message : 'Operación fallida'; status.classList.add('error');}
        finally {b.disabled = false;}};
    }
    function card(title: string) {const el = node('section'); el.className = 'card'; el.append(node('h2',title)); content.append(el); return el;}
    action(toolbar, 'Comprobar API', async () => {const s = await api<{storage: string}>('extensions/status'); notice.textContent = `Almacenamiento: ${s.storage === 'demo' ? 'demostración local persistente, solo datos sintéticos' : 'PostgreSQL'}. Acceso local sin autenticación de producción.`;});
    async function capture(key: string) {
      let interview = await api<Interview>(`surveys/interviews/${key}`); content.replaceChildren();
      const c = card(`${interview.schema.template_code} · ${interview.status}`); const values = structuredClone(interview.responses);
      const wrappers = new Map<string, HTMLElement>(); const controls = new Map<string, HTMLInputElement | HTMLSelectElement>();
      function applies(q: Q, trail = new Set<string>()): boolean {
        if (!q.visible_when) return true; if (trail.has(q.id)) return false; trail.add(q.id);
        const rule = q.visible_when, parent = interview.schema.questions.find(p => p.id === rule.question_id);
        if (!parent || !applies(parent, trail) || values[parent.id] === undefined) return false;
        return rule.operator === 'eq' ? values[parent.id] === rule.value : rule.operator === 'ne' ? values[parent.id] !== rule.value : Array.isArray(rule.value) && rule.value.includes(values[parent.id]);
      }
      function update() {for (const q of interview.schema.questions) {wrappers.get(q.id)!.hidden = !applies(q); controls.get(q.id)!.disabled = !applies(q) || interview.status !== 'draft';}}
      for (const q of interview.schema.questions) {
        const control = q.options ? selection([['','Sin respuesta'], ...q.options.map(o => [o.code,o.label] as [string,string])]) : input(['integer','decimal'].includes(q.type) ? 'number' : q.type === 'date' ? 'date' : 'text');
        if (control instanceof HTMLInputElement && control.type === 'number') control.step = q.type === 'integer' ? '1' : 'any';
        if (control instanceof HTMLSelectElement && q.type === 'multi_select') {control.multiple = true; control.remove(0);}
        control.value = String(values[q.id] ?? '');
        if (control instanceof HTMLSelectElement && control.multiple) [...control.options].forEach(o => {o.selected = Array.isArray(values[q.id]) && (values[q.id] as unknown[]).includes(o.value);});
        const wrapper = node('div'); field(wrapper, q.label + (q.required ? ' *' : ''), control); c.append(wrapper); wrappers.set(q.id,wrapper); controls.set(q.id,control);
        control.oninput = () => {if (control instanceof HTMLSelectElement && control.multiple) values[q.id] = [...control.selectedOptions].map(o=>o.value); else if (!control.value) delete values[q.id]; else values[q.id] = ['integer','decimal'].includes(q.type) ? Number(control.value) : control.value; update();};
      }
      update();
      async function save() {interview = await api<Interview>(`surveys/interviews/${key}`, 'PATCH', {responses:values, revision:interview.revision});}
      if (interview.status === 'draft') {
        action(c,'Guardar borrador',save);
        action(c,'Validar en servidor',async()=>{await save(); const r = await api<{valid:boolean;findings:unknown[]}>(`surveys/interviews/${key}/validate`,'POST'); status.textContent = r.valid ? 'Sin errores de validación.' : JSON.stringify(r.findings);});
        action(c,'Finalizar entrevista',async()=>{await save(); await api(`surveys/interviews/${key}/submit`,'POST'); await capture(key);});
      }
      const audio = card('Vincular transcripción autorizada');
      const consent = input('checkbox'); field(audio,'Confirmo autorización de uso',consent);
      const file = input('file'); file.accept = '.json'; field(audio,'Resultado JSON de Audio Audit',file);
      action(audio,'Asociar resultado',async()=>{if (!consent.checked || !file.files?.[0]) throw new Error('Confirma autorización y selecciona un resultado JSON'); if(file.files[0].size>10*1024*1024) throw new Error('Máximo 10 MB'); const data=JSON.parse(await file.files[0].text()); await api(`surveys/interviews/${key}/transcripts`,'POST',{consent:true,result:data.result??data,engine_job_id:data.job_id??''}); await capture(key);});
      const transcript=interview.transcripts.at(-1);
      if(transcript){const evidence=card('Comparación con evidencia temporal'); const selected=new Set<number>(); transcript.turns.forEach(t=>{const check=input('checkbox'); field(evidence,`${t.start}–${t.end} s · ${t.speaker}: ${t.text}`,check);check.onchange=()=>{if(check.checked)selected.add(t.id);else selected.delete(t.id);};});
        const role=selection([...new Set(transcript.turns.map(t=>t.speaker))].map(s=>[s,s]));field(evidence,'Confirmar hablante encuestador',role);
        const question=selection(interview.schema.questions.map(q=>[q.id,q.label]));field(evidence,'Pregunta',question);const observed=input();field(evidence,'Respuesta observada o código; vacío si no verificable',observed);
        action(evidence,'Comparar',async()=>{const q=interview.schema.questions.find(q=>q.id===question.value)!;const value=observed.value?(['integer','decimal'].includes(q.type)?Number(observed.value):q.type==='multi_select'?observed.value.split(',').map(v=>v.trim()):observed.value):null;
          const finding=await api<{id:string;status:string}>(`surveys/interviews/${key}/reconcile`,'POST',{question_id:q.id,turn_ids:[...selected],observed_value:value,interviewer:role.value});status.textContent=`Resultado: ${finding.status}`;
          const why=input();field(evidence,'Justificación de revisión',why);for(const [label,state]of [['Confirmar','confirmed'],['Descartar','dismissed']])action(evidence,label,async()=>{await api(`surveys/interviews/${key}/findings/${finding.id}`,'PATCH',{state,justification:why.value});});});}
    }
    if(id==='encuestas') {
      action(toolbar,'Instrumentos',async()=>{const list=await api<Template[]>('surveys/templates');content.replaceChildren();
        const create=card('Nuevo instrumento');const code=input('text',pilot.template_code);field(create,'Código para el piloto sintético',code);
        action(create,'Guardar piloto sintético como borrador',async()=>{await api('surveys/templates','POST',{schema_data:{...structuredClone(pilot),template_code:code.value}});status.textContent='Borrador guardado. Vuelve a Instrumentos para publicarlo.';});
        const pdf=input('file');pdf.accept='.pdf';field(create,'Extraer documento fuente PDF',pdf);action(create,'Extraer PDF para revisión',async()=>{if(!pdf.files?.[0])throw new Error('Selecciona un PDF');const form=new FormData();form.append('file',pdf.files[0]);const r=await api<{warning:string;pages:{page:number;text:string}[]}>('surveys/import','POST',form);const pre=node('pre',r.pages.map(p=>`Página ${p.page}\n${p.text}`).join('\n'));pre.style.whiteSpace='pre-wrap';create.append(pre);status.textContent=r.warning;});
        list.forEach(t=>{const c=card(`${t.schema.template_code} · v${t.schema.version} · ${t.status}`);if(t.status==='draft')action(c,'Publicar versión',async()=>{await api(`surveys/templates/${t.id}/publish`,'POST');status.textContent='Versión publicada';});else action(c,'Nueva entrevista',async()=>{const i=await api<Interview>('surveys/interviews','POST',{template_id:t.id});await capture(i.id);});});
      });
      action(toolbar,'Entrevistas guardadas',async()=>{const list=await api<Interview[]>('surveys/interviews');content.replaceChildren();if(!list.length)card('Todavía no hay entrevistas');list.forEach(i=>{const c=card(`${i.schema.template_code} · ${i.status}`);c.append(node('p',i.id));action(c,'Abrir captura y conciliación',()=>capture(i.id));});});
    } else {
      const institution=selection(['RENAP','PNC','INSIVUMEH','SE-CONRED'].map(s=>[s,s]));field(toolbar,'Institución',institution);
      action(toolbar,'Recomendaciones',async()=>{content.replaceChildren();const c=card('Importar reporte de Data Audit');const file=input('file');file.accept='.json';field(c,'reporte.json',file);const run=input();field(c,'Referencia de ejecución',run);const date=input('date');field(c,'Fecha de ejecución',date);const synthetic=input('checkbox');field(c,'Reporte sintético de demostración',synthetic);
        action(c,'Generar recomendaciones',async()=>{if(!file.files?.[0]||file.files[0].size>10*1024*1024)throw new Error('Selecciona un JSON de hasta 10 MB');await api('improvement/reports','POST',{institution:institution.value,report:JSON.parse(await file.files[0].text()),source_run_ref:run.value,source_run_at:date.value,synthetic:synthetic.checked});status.textContent='Recomendaciones guardadas. Vuelve a abrir esta vista para consultarlas.';});
        const recs=(await api<Rec[]>('improvement/recommendations')).filter(r=>r.institution===institution.value);recs.forEach(r=>{card(`${r.rule}: ${r.count} hallazgos`).append(node('p',r.action),node('p',r.rate_reason),node('p',`Fuente: ${r.source_run_ref}`));});
        action(c,'Crear borrador de manual con estas fuentes',async()=>{await api('improvement/manuals','POST',{institution:institution.value,title:`Manual preventivo ${institution.value}`,source_ids:recs.map(r=>r.id),content:`Objetivo: prevenir errores antes del envío.\n\nEstructura y catálogos: pendientes de validación institucional.\n\nAcciones preventivas:\n${recs.map(r=>`${r.rule}: ${r.action} Fuente: ${r.source_run_ref}`).join('\n')}\n\nChecklist: revisar encabezados, tipos, códigos especiales y catálogos autorizados; ejecutar Data Audit; revisar sugerencias.\n\nIndicador: conteo por regla entre periodos comparables.\nResponsable propuesto: responsable institucional de calidad.\nEjemplo sintético inválido: reemplazar un dato desconocido por un código inventado.`});status.textContent='Manual creado; abre Manuales para revisarlo.';});
      });
      action(toolbar,'Manuales',async()=>{const list=(await api<Manual[]>('improvement/manuals')).filter(m=>m.institution===institution.value);content.replaceChildren();list.forEach(m=>{const c=card(`${m.title} · v${m.version} · ${m.status}`);const text=node('textarea');text.value=m.content;text.rows=18;text.disabled=m.status!=='draft';field(c,'Contenido sin datos personales',text);if(m.status==='draft'){action(c,'Guardar cambios',async()=>{await api(`improvement/manuals/${m.id}`,'PATCH',{title:m.title,content:text.value});});action(c,'Aprobar versión técnica',async()=>{await api(`improvement/manuals/${m.id}/approve`,'POST');text.disabled=true;});}const a=node('a','Descargar manual');a.className='button secondary';a.href=`/api/improvement/manuals/${m.id}/download`;c.append(a);});});
    }
  }
}
