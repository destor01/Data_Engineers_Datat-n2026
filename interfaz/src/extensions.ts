import './modulos.css';
import { demo } from './services/config';
import { mountImprovement } from './improvement';
import { mountSurvey } from './survey';
import { h } from './ui';

/** Agrega las páginas de Survey Audit y Quality Improvement; cada una se carga la primera vez que se abre. */
export function mountExtensions() {
  const modulos: [string, string, string, (page: HTMLElement) => void][] = [
    ['encuestas', 'Survey Audit', '☑', mountSurvey],
    ['mejora', 'Quality Improvement', '↗', mountImprovement],
  ];
  const montados = new Set<string>();
  for (const [id, titulo, icono] of modulos) {
    const page = h('section', { id, class: 'page', 'aria-labelledby': `${id}Title`, hidden: true });
    document.querySelector('main')!.append(page);
    const link = h('a', { href: `#${id}` }, h('span', { 'aria-hidden': 'true', text: icono }), ` ${titulo}`);
    link.dataset.nav = id;
    document.querySelector('nav')!.append(link);
  }
  const activar = () => {
    const actual = location.hash.slice(1);
    const modulo = modulos.find(([id]) => id === actual);
    if (!modulo || montados.has(actual)) return;
    const page = document.getElementById(actual)!;
    if (!document.getElementById('app') || document.getElementById('app')!.hidden) return;
    montados.add(actual);
    if (demo) {
      page.append(h('h1', { id: `${actual}Title`, tabindex: -1, text: modulo[1] }),
        h('p', { class: 'empty', text: 'Este módulo funciona con el servidor conectado. Inicia la plataforma en modo conectado para usarlo.' }));
      return;
    }
    modulo[3](page);
  };
  window.addEventListener('hashchange', activar);
  // La aplicación se muestra después del inicio de sesión.
  new MutationObserver(activar).observe(document.getElementById('app')!, { attributes: true, attributeFilter: ['hidden'] });
  activar();
}
