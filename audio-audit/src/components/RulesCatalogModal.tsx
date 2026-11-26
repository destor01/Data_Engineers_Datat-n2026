import React, { useMemo, useState } from "react";
import type { RuleCatalogItem } from "../types";

interface RulesCatalogModalProps {
  isOpen: boolean;
  rules: RuleCatalogItem[];
  onClose: () => void;
  onSelectRuleToEdit: (rule: RuleCatalogItem) => void;
}

const KIND_LABELS: Record<string, string> = {
  obligation: "Obligación",
  prohibition: "Prohibición",
  conditional: "Condicional",
  evidence: "Evidencia",
};

export const RulesCatalogModal: React.FC<RulesCatalogModalProps> = ({
  isOpen,
  rules,
  onClose,
  onSelectRuleToEdit,
}) => {
  const [sectionFilter, setSectionFilter] = useState<string>("ALL");
  const [onlyCustomized, setOnlyCustomized] = useState<boolean>(false);
  const [search, setSearch] = useState<string>("");

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return rules.filter((r) => {
      if (sectionFilter !== "ALL" && r.section !== sectionFilter) return false;
      if (onlyCustomized && !r.is_customized) return false;
      if (q) {
        const hay = `${r.id} ${r.text} ${r.auditor_guidance || ""}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [rules, sectionFilter, onlyCustomized, search]);

  if (!isOpen) return null;

  return (
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <div
        className="modal-panel modal-wide"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <div className="modal-header">
          <div>
            <h2 className="modal-title">Catálogo de 51 Evaluaciones ENCOVI (A1 y A2)</h2>
            <p className="block-hint" style={{ margin: "4px 0 0" }}>
              Edita o reescribe cualquier criterio de evaluación para las próximas transcripciones. Los cambios se guardan en Supabase.
            </p>
          </div>
          <button type="button" className="modal-close-btn" onClick={onClose} aria-label="Cerrar">
            ✕
          </button>
        </div>

        <div className="modal-body">
          <div className="rules-secondary-filters" style={{ marginBottom: 14 }}>
            <select value={sectionFilter} onChange={(e) => setSectionFilter(e.target.value)}>
              <option value="ALL">Todas las secciones (A1 y A2)</option>
              <option value="A1">Solo A1 — Apertura</option>
              <option value="A2">Solo A2 — Conducta y actitud</option>
            </select>
            <input
              type="search"
              placeholder="Buscar por código (ej. A1-10) o texto…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={onlyCustomized}
                onChange={(e) => setOnlyCustomized(e.target.checked)}
              />
              <span>Solo reglas reescritas</span>
            </label>
          </div>

          <div className="rules-table-wrap">
            <table className="rules-table">
              <thead>
                <tr>
                  <th>Regla</th>
                  <th>Tipo</th>
                  <th>Peso</th>
                  <th>Estado</th>
                  <th>Acción</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((r) => (
                  <tr key={r.id}>
                    <td>
                      <span className="rule-id-badge">{r.id}</span> {r.text}
                      {r.auditor_guidance && (
                        <div className="auditor-note-inline">
                          <strong>Guía del auditor:</strong> {r.auditor_guidance}
                        </div>
                      )}
                    </td>
                    <td>{KIND_LABELS[r.kind] || r.kind}</td>
                    <td>{r.weight}</td>
                    <td>
                      {!r.enabled ? (
                        <span className="pill pill-muted">Desactivada</span>
                      ) : r.is_customized ? (
                        <span className="pill pill-blue">Reescrita</span>
                      ) : (
                        <span className="pill pill-ok">Original</span>
                      )}
                    </td>
                    <td>
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={() => onSelectRuleToEdit(r)}
                      >
                        Editar criterio
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="modal-footer">
          <span className="block-hint">Mostrando {filtered.length} de {rules.length} reglas</span>
          <button type="button" className="btn btn-primary" onClick={onClose}>
            Listo
          </button>
        </div>
      </div>
    </div>
  );
};
