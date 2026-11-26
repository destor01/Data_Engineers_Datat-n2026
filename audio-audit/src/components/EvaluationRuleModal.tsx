import React, { useEffect, useState } from "react";
import type {
  EvaluatedInstruction,
  EvaluationRuleEditRequest,
  OverrideStatus,
  RuleCatalogItem,
  RuleOverrideInput,
} from "../types";

interface EvaluationRuleModalProps {
  isOpen: boolean;
  ruleSpec: RuleCatalogItem | null;
  evaluatedRule: EvaluatedInstruction | null;
  onClose: () => void;
  onSaveInterviewAndRule?: (
    ruleId: string,
    payload: EvaluationRuleEditRequest,
    reEvaluateNow: boolean
  ) => Promise<void>;
  onSaveGlobalRuleOnly?: (ruleId: string, payload: RuleOverrideInput) => Promise<void>;
  onResetGlobalRule?: (ruleId: string) => Promise<void>;
}

const ROLE_DISPLAY_NAMES: Record<string, string> = {
  true: "Sí ocurre / Cumple criterio (true)",
  false: "No ocurre / Situación opuesta (false)",
  followed: "Opción: Cumplida",
  broken: "Opción: Incumplida",
  unknown: "Opción: No aplica / Sin evidencia",
};

function formatPct(val: number | undefined | null): string {
  if (val == null || Number.isNaN(val)) return "0 %";
  return `${Math.round(val * 100)} %`;
}

export const EvaluationRuleModal: React.FC<EvaluationRuleModalProps> = ({
  isOpen,
  ruleSpec,
  evaluatedRule,
  onClose,
  onSaveInterviewAndRule,
  onSaveGlobalRuleOnly,
  onResetGlobalRule,
}) => {
  const [overrideStatus, setOverrideStatus] = useState<OverrideStatus>("keep");
  const [selectedWindow, setSelectedWindow] = useState<number | null>(null);
  const [customFollowed, setCustomFollowed] = useState<number>(100);
  const [customBroken, setCustomBroken] = useState<number>(0);
  const [customUnknown, setCustomUnknown] = useState<number>(0);
  const [auditorComment, setAuditorComment] = useState<string>("");

  const [updateFutureRule, setUpdateFutureRule] = useState<boolean>(false);
  const [enabled, setEnabled] = useState<boolean>(true);
  const [customText, setCustomText] = useState<string>("");
  const [weight, setWeight] = useState<1 | 2 | 3>(2);
  const [auditorGuidance, setAuditorGuidance] = useState<string>("");
  const [questionsState, setQuestionsState] = useState<
    Record<string, { instructions: string; criteria: Record<string, string> }>
  >({});

  const [saving, setSaving] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const isGlobalOnlyMode = !evaluatedRule;

  useEffect(() => {
    if (!isOpen || !ruleSpec) return;
    setError(null);

    if (evaluatedRule) {
      const existingMo = evaluatedRule.manual_override;
      if (existingMo && ["followed", "broken", "unknown", "custom"].includes(existingMo.status)) {
        setOverrideStatus(existingMo.status as OverrideStatus);
      } else {
        setOverrideStatus("keep");
      }
      setAuditorComment(existingMo?.comment || "");
      setSelectedWindow(
        evaluatedRule.worst_window?.window ??
          evaluatedRule.windows?.[0]?.window ??
          0
      );
      setCustomFollowed(Math.round((evaluatedRule.p_followed || 0) * 100));
      setCustomBroken(Math.round((evaluatedRule.p_broken || 0) * 100));
      setCustomUnknown(Math.round((evaluatedRule.p_unknown || 0) * 100));
      setUpdateFutureRule(Boolean(ruleSpec.is_customized));
    } else {
      setUpdateFutureRule(true);
    }

    setEnabled(ruleSpec.enabled);
    setCustomText(ruleSpec.text);
    setWeight(ruleSpec.weight);
    setAuditorGuidance(ruleSpec.auditor_guidance || "");

    const qInit: Record<string, { instructions: string; criteria: Record<string, string> }> = {};
    for (const q of ruleSpec.questions) {
      qInit[q.key] = {
        instructions: q.instructions,
        criteria: { ...q.criteria },
      };
    }
    setQuestionsState(qInit);
  }, [isOpen, ruleSpec, evaluatedRule]);

  if (!isOpen || !ruleSpec) return null;

  const buildRuleOverridePayload = (): RuleOverrideInput => {
    const qOut: RuleOverrideInput["questions_override"] = {};
    for (const q of ruleSpec.questions) {
      const edited = questionsState[q.key];
      if (edited) {
        qOut[q.key] = {
          instructions: edited.instructions,
          criteria: { ...edited.criteria },
        };
      }
    }
    return {
      custom_text: customText.trim() || ruleSpec.default_text,
      weight,
      enabled,
      auditor_guidance: auditorGuidance.trim(),
      questions_override: qOut,
    };
  };

  const handleSave = async (reEvaluateNow = false) => {
    setSaving(true);
    setError(null);
    try {
      if (isGlobalOnlyMode) {
        if (onSaveGlobalRuleOnly) {
          await onSaveGlobalRuleOnly(ruleSpec.id, buildRuleOverridePayload());
        }
      } else if (onSaveInterviewAndRule) {
        const totalCustom = customFollowed + customBroken + customUnknown;
        const normDiv = totalCustom > 0 ? totalCustom : 100;
        const payload: EvaluationRuleEditRequest = {
          override_status: overrideStatus,
          custom_probs:
            overrideStatus === "custom"
              ? {
                  p_followed: customFollowed / normDiv,
                  p_broken: customBroken / normDiv,
                  p_unknown: customUnknown / normDiv,
                }
              : null,
          auditor_comment: auditorComment,
          window_index: selectedWindow,
          update_future_rule: updateFutureRule || reEvaluateNow,
          rule_override: updateFutureRule || reEvaluateNow ? buildRuleOverridePayload() : null,
        };
        await onSaveInterviewAndRule(ruleSpec.id, payload, reEvaluateNow);
      }
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al guardar los cambios.");
    } finally {
      setSaving(false);
    }
  };

  const handleResetGlobal = async () => {
    if (!onResetGlobalRule) return;
    setSaving(true);
    setError(null);
    try {
      await onResetGlobalRule(ruleSpec.id);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo restaurar la regla original.");
    } finally {
      setSaving(false);
    }
  };

  const markGlobalEdited = () => {
    if (!updateFutureRule) setUpdateFutureRule(true);
  };

  const findRoleLabel = (qRoles: Record<string, string>, optionKey: string): string => {
    if (optionKey in ROLE_DISPLAY_NAMES) return ROLE_DISPLAY_NAMES[optionKey];
    const matchedRole = Object.entries(qRoles).find(([, optName]) => optName === optionKey)?.[0];
    if (matchedRole && matchedRole in ROLE_DISPLAY_NAMES) {
      return `${ROLE_DISPLAY_NAMES[matchedRole]} (${optionKey})`;
    }
    return `Opción: ${optionKey}`;
  };

  return (
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <div
        className="modal-panel"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="modalRuleTitle"
      >
        <div className="modal-header">
          <div>
            <div className="modal-title-row">
              <span className="rule-id-badge">{ruleSpec.id}</span>
              <span className="pill pill-muted">Sección {ruleSpec.section}</span>
              {ruleSpec.pages && <span className="block-hint">Manual {ruleSpec.pages}</span>}
              {ruleSpec.is_customized && (
                <span className="pill pill-blue">Criterio reescrito activo</span>
              )}
            </div>
            <h2 id="modalRuleTitle" className="modal-title">
              {evaluatedRule
                ? "Editar evaluación y criterio para futuras transcripciones"
                : "Editar criterio de evaluación JEV"}
            </h2>
          </div>
          <button type="button" className="modal-close-btn" onClick={onClose} aria-label="Cerrar">
            ✕
          </button>
        </div>

        <div className="modal-body">
          {/* SECTION 1: Override assessment on the current interview */}
          {evaluatedRule && (
            <div className="modal-section">
              <div className="modal-section-head">
                <h3>1. Corregir dictamen en esta entrevista</h3>
                <span className="block-hint">
                  Puntaje actual: C {formatPct(evaluatedRule.p_followed)} · I{" "}
                  {formatPct(evaluatedRule.p_broken)} · N/A {formatPct(evaluatedRule.p_unknown)}
                  {evaluatedRule.original_outcome && evaluatedRule.manual_override
                    ? ` (JEV original: I ${formatPct(evaluatedRule.original_outcome.p_broken)})`
                    : ""}
                </span>
              </div>

              <div className="override-pills">
                <button
                  type="button"
                  className={`override-choice ${overrideStatus === "keep" ? "active" : ""}`}
                  onClick={() => setOverrideStatus("keep")}
                >
                  Mantener actual
                </button>
                <button
                  type="button"
                  className={`override-choice ok ${overrideStatus === "followed" ? "active" : ""}`}
                  onClick={() => setOverrideStatus("followed")}
                >
                  ✓ Cumplida (100 %)
                </button>
                <button
                  type="button"
                  className={`override-choice bad ${overrideStatus === "broken" ? "active" : ""}`}
                  onClick={() => setOverrideStatus("broken")}
                >
                  ✕ Incumplida (100 %)
                </button>
                <button
                  type="button"
                  className={`override-choice na ${overrideStatus === "unknown" ? "active" : ""}`}
                  onClick={() => setOverrideStatus("unknown")}
                >
                  — No aplica / Sin evidencia
                </button>
                <button
                  type="button"
                  className={`override-choice ${overrideStatus === "custom" ? "active" : ""}`}
                  onClick={() => setOverrideStatus("custom")}
                >
                  % Personalizado
                </button>
                {evaluatedRule.manual_override && (
                  <button
                    type="button"
                    className={`override-choice ${overrideStatus === "reset" ? "active" : ""}`}
                    onClick={() => setOverrideStatus("reset")}
                  >
                    ↺ Restaurar puntaje JEV
                  </button>
                )}
              </div>

              {overrideStatus === "custom" && (
                <div className="custom-probs-grid">
                  <div className="field">
                    <label>Cumplida (%)</label>
                    <input
                      type="number"
                      min={0}
                      max={100}
                      value={customFollowed}
                      onChange={(e) => setCustomFollowed(Number(e.target.value))}
                    />
                  </div>
                  <div className="field">
                    <label>Incumplida (%)</label>
                    <input
                      type="number"
                      min={0}
                      max={100}
                      value={customBroken}
                      onChange={(e) => setCustomBroken(Number(e.target.value))}
                    />
                  </div>
                  <div className="field">
                    <label>No aplica (%)</label>
                    <input
                      type="number"
                      min={0}
                      max={100}
                      value={customUnknown}
                      onChange={(e) => setCustomUnknown(Number(e.target.value))}
                    />
                  </div>
                </div>
              )}

              <div className="field" style={{ marginTop: 12 }}>
                <label htmlFor="auditorCommentInput">
                  Nota / justificación del auditor en esta entrevista (opcional)
                </label>
                <textarea
                  id="auditorCommentInput"
                  rows={2}
                  placeholder="Ej.: El encuestador sí aclaró la confidencialidad en el minuto 00:45 antes de iniciar…"
                  value={auditorComment}
                  onChange={(e) => setAuditorComment(e.target.value)}
                />
              </div>

              {evaluatedRule.windows && evaluatedRule.windows.length > 1 && (
                <div className="field" style={{ marginTop: 10 }}>
                  <label htmlFor="windowSelectInput">
                    Ventana de referencia para calibración JEV
                  </label>
                  <select
                    id="windowSelectInput"
                    value={selectedWindow ?? 0}
                    onChange={(e) => setSelectedWindow(Number(e.target.value))}
                  >
                    {evaluatedRule.windows.map((w) => (
                      <option key={w.window} value={w.window}>
                        Ventana {w.window + 1} (I: {formatPct(w.broken)} · C: {formatPct(w.followed)}
                        {w.p_trigger != null ? ` · Activador: ${formatPct(w.p_trigger)}` : ""})
                      </option>
                    ))}
                  </select>
                </div>
              )}

              <p className="rule-meta-line" style={{ marginTop: 8 }}>
                Al marcar <strong>Cumplida</strong>, <strong>Incumplida</strong> o{" "}
                <strong>No aplica</strong> en evaluaciones reales, se guarda automáticamente la
                probabilidad cruda de JEV, la clave de pregunta y la ventana para entrenar la
                calibración (se activa a partir de ~30 correcciones por tipo de regla).
              </p>
            </div>
          )}

          {/* SECTION 2: Rewrite evaluation criteria for future transcripts */}
          <div className="modal-section modal-section-future">
            <div className="modal-section-head">
              <div>
                <h3>
                  {evaluatedRule
                    ? "2. Reescribir evaluación para próximas transcripciones"
                    : "Definición y criterios para próximas transcripciones"}
                </h3>
                <p className="block-hint" style={{ margin: "2px 0 0" }}>
                  Si la evaluación automática no interpretó bien esta regla, ajusta aquí su criterio. Se guardará en Supabase y se aplicará a todas las siguientes entrevistas.
                </p>
              </div>
              {evaluatedRule && (
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={updateFutureRule}
                    onChange={(e) => setUpdateFutureRule(e.target.checked)}
                  />
                  <span>Guardar para próximas transcripciones</span>
                </label>
              )}
            </div>

            <div className="options-grid" style={{ marginTop: 12 }}>
              <div className="field">
                <label>Severidad / Peso en el puntaje</label>
                <select
                  value={weight}
                  onChange={(e) => {
                    setWeight(Number(e.target.value) as 1 | 2 | 3);
                    markGlobalEdited();
                  }}
                >
                  <option value={1}>Baja (1) — Detalle de cortesía o ejemplo</option>
                  <option value={2}>Media (2) — Procedimiento explícito</option>
                  <option value={3}>Alta (3) — Protege al informante o validez del dato</option>
                </select>
              </div>

              <div className="field">
                <label>Estado en futuras evaluaciones</label>
                <select
                  value={enabled ? "enabled" : "disabled"}
                  onChange={(e) => {
                    setEnabled(e.target.value === "enabled");
                    markGlobalEdited();
                  }}
                >
                  <option value="enabled">Activa (evaluar en próximas transcripciones)</option>
                  <option value="disabled">Desactivada (omitir esta regla)</option>
                </select>
              </div>
            </div>

            <div className="field" style={{ marginTop: 12 }}>
              <label>Enunciado de la regla ENCOVI</label>
              <input
                type="text"
                value={customText}
                onChange={(e) => {
                  setCustomText(e.target.value);
                  markGlobalEdited();
                }}
              />
            </div>

            <div className="field" style={{ marginTop: 12 }}>
              <label>
                Instrucción / aclaración adicional para futuras transcripciones (recomendado)
              </label>
              <textarea
                rows={2}
                placeholder="Ej.: Si el encuestador menciona al INE al presentarse, cuenta como haber mencionado a la institución patrocinadora."
                value={auditorGuidance}
                onChange={(e) => {
                  setAuditorGuidance(e.target.value);
                  markGlobalEdited();
                }}
              />
            </div>

            <details className="jev-questions-editor" open={isGlobalOnlyMode}>
              <summary>
                Ver y reescribir el prompt y criterios exactos enviados al modelo JEV (
                {ruleSpec.questions.length}{" "}
                {ruleSpec.questions.length === 1 ? "pregunta" : "preguntas"})
              </summary>

              <div className="jev-questions-list">
                {ruleSpec.questions.map((q) => {
                  const qVal = questionsState[q.key] || {
                    instructions: q.instructions,
                    criteria: q.criteria,
                  };
                  return (
                    <div key={q.key} className="jev-question-box">
                      <div className="jev-q-head">
                        <span className="rule-id-badge">{q.key}</span>
                        <span className="block-hint">
                          {q.is_trigger
                            ? "Etapa 1 · Activador condicional «si X ocurre» (Noul)"
                            : q.type === "noul"
                            ? "Sí / No (Noul)"
                            : "Etapa 2 · Evaluación de respuesta (Choice)"}
                        </span>
                      </div>

                      <div className="field" style={{ marginTop: 8 }}>
                        <label>Instrucción principal evaluada por JEV</label>
                        <textarea
                          rows={2}
                          value={qVal.instructions}
                          onChange={(e) => {
                            const nextVal = e.target.value;
                            setQuestionsState((prev) => ({
                              ...prev,
                              [q.key]: {
                                ...qVal,
                                instructions: nextVal,
                              },
                            }));
                            markGlobalEdited();
                          }}
                        />
                      </div>

                      <div className="criteria-grid">
                        {Object.entries(qVal.criteria).map(([optKey, optDesc]) => (
                          <div key={optKey} className="field">
                            <label>{findRoleLabel(q.roles, optKey)}</label>
                            <textarea
                              rows={2}
                              value={optDesc}
                              onChange={(e) => {
                                const nextDesc = e.target.value;
                                setQuestionsState((prev) => ({
                                  ...prev,
                                  [q.key]: {
                                    ...qVal,
                                    criteria: {
                                      ...qVal.criteria,
                                      [optKey]: nextDesc,
                                    },
                                  },
                                }));
                                markGlobalEdited();
                              }}
                            />
                          </div>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>
            </details>
          </div>

          {error && <div className="jev-error-inline">{error}</div>}
        </div>

        <div className="modal-footer">
          <div className="btn-group">
            {ruleSpec.is_customized && onResetGlobalRule && (
              <button
                type="button"
                className="btn btn-secondary"
                disabled={saving}
                onClick={handleResetGlobal}
              >
                Restaurar criterio original ENCOVI
              </button>
            )}
          </div>

          <div className="btn-group">
            <button type="button" className="btn btn-secondary" disabled={saving} onClick={onClose}>
              Cancelar
            </button>
            {evaluatedRule && (
              <button
                type="button"
                className="btn btn-secondary"
                disabled={saving}
                onClick={() => handleSave(true)}
                title="Guarda el nuevo criterio global y vuelve a correr JEV sobre esta entrevista"
              >
                {saving ? "Guardando…" : "Guardar criterio y re-evaluar"}
              </button>
            )}
            <button
              type="button"
              className="btn btn-primary"
              disabled={saving}
              onClick={() => handleSave(false)}
            >
              {saving ? "Guardando…" : "Guardar cambios"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
