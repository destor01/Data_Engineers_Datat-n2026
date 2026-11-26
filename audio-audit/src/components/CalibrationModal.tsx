import React, { useState } from "react";
import type { CalibrationStatus } from "../types";

interface CalibrationModalProps {
  isOpen: boolean;
  calibration: CalibrationStatus | null;
  onClose: () => void;
  onRefit: () => Promise<void>;
}

const GROUP_LABELS: Record<string, string> = {
  "noul/obligation": "Obligaciones (Apertura / Cierre · Platt)",
  "noul/prohibition": "Conducta / Prohibiciones (Platt)",
  "noul/trigger": "Activadores condicionales «si X» (Platt)",
  "noul/gate": "Compuertas de apertura / cierre (Platt)",
  "choice/conditional": "Condicionales — respuesta «hacer Y» (Temperatura)",
  "choice/evidence": "Evidencia silenciosa (Temperatura)",
};

const ALL_EXPECTED_GROUPS = [
  "noul/prohibition",
  "noul/obligation",
  "noul/trigger",
  "choice/conditional",
  "choice/evidence",
];

export const CalibrationModal: React.FC<CalibrationModalProps> = ({
  isOpen,
  calibration,
  onClose,
  onRefit,
}) => {
  const [fitting, setFitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const minLabels = calibration?.min_labels ?? 30;
  const groups = calibration?.groups || {};
  const orderedKeys = Array.from(new Set([...ALL_EXPECTED_GROUPS, ...Object.keys(groups)]));

  const handleRefit = async () => {
    setFitting(true);
    setError(null);
    try {
      await onRefit();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error ajustando calibración.");
    } finally {
      setFitting(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <div
        className="modal-panel"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <div className="modal-header">
          <div>
            <div className="modal-title-row">
              <span className={`pill ${calibration?.is_calibrated ? "pill-ok" : "pill-warn"}`}>
                {calibration?.is_calibrated ? "Calibración activa" : "Sin calibrar (identidad)"}
              </span>
              <span className="pill pill-muted">
                Modelo: {calibration?.model_version || "typesafe/jev-1.14"}
              </span>
            </div>
            <h2 className="modal-title">Calibración automática desde correcciones del supervisor</h2>
          </div>
          <button type="button" className="modal-close-btn" onClick={onClose} aria-label="Cerrar">
            ✕
          </button>
        </div>

        <div className="modal-body">
          <p className="notice-text" style={{ margin: 0 }}>
            Cada vez que corriges una evaluación real (<em>Cumplida</em>, <em>Incumplida</em> o{" "}
            <em>No aplica</em>), el sistema guarda la probabilidad cruda de JEV, la clave de pregunta
            y la ventana. Al reunir al menos <strong>{minLabels} correcciones por tipo de regla</strong>{" "}
            (con ejemplos positivos y negativos para reglas Sí/No), se ajusta automáticamente el
            calibrador Platt / temperatura y se aplica a las siguientes entrevistas.
          </p>

          <div className="rules-table-wrap">
            <table className="rules-table">
              <thead>
                <tr>
                  <th>Tipo de regla</th>
                  <th>Correcciones</th>
                  <th>Estado</th>
                  <th>Parámetros / Error (Brier · ECE)</th>
                </tr>
              </thead>
              <tbody>
                {orderedKeys.map((gk) => {
                  const info = groups[gk];
                  const n = info?.n ?? 0;
                  const pct = Math.min(100, Math.round((n / minLabels) * 100));
                  const fitted = Boolean(info?.fitted);
                  return (
                    <tr key={gk}>
                      <td>
                        <strong>{GROUP_LABELS[gk] || gk}</strong>
                        <div className="rule-meta-line">{gk}</div>
                      </td>
                      <td>
                        <div>
                          <strong>{n}</strong> / {minLabels}
                        </div>
                        <div className="cal-progress-track">
                          <div className="cal-progress-fill" style={{ width: `${pct}%` }} />
                        </div>
                      </td>
                      <td>
                        {fitted ? (
                          <span className="pill pill-ok">Calibrado</span>
                        ) : (
                          <span className="pill pill-muted">
                            Faltan {Math.max(0, minLabels - n)}
                          </span>
                        )}
                      </td>
                      <td>
                        {fitted && info ? (
                          info.temperature != null ? (
                            <div className="rule-meta-line">
                              T = {info.temperature} · Precisión ={" "}
                              {info.accuracy != null ? `${Math.round(info.accuracy * 100)} %` : "—"}
                            </div>
                          ) : (
                            <div className="rule-meta-line">
                              a = {info.a}, b = {info.b} · Brier {info.brier_raw} →{" "}
                              <strong>{info.brier_cal_in_sample}</strong> · ECE {info.ece_raw} →{" "}
                              <strong>{info.ece_cal_in_sample}</strong>
                            </div>
                          )
                        ) : info && n > 0 ? (
                          <div className="rule-meta-line">
                            {info.positives != null
                              ? `${info.positives} sí / ${info.negatives} no`
                              : `Precisión bruta: ${
                                  info.accuracy != null ? `${Math.round(info.accuracy * 100)} %` : "—"
                                }`}
                          </div>
                        ) : (
                          <span className="rule-meta-line">Sin correcciones aún</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {error && <div className="jev-error-inline">{error}</div>}
        </div>

        <div className="modal-footer">
          <span className="block-hint">
            Total de etiquetas válidas (no mock): {calibration?.total_labels ?? 0}
          </span>
          <div className="btn-group">
            <button
              type="button"
              className="btn btn-secondary"
              disabled={fitting}
              onClick={handleRefit}
            >
              {fitting ? "Recalibrando…" : "Recalibrar ahora"}
            </button>
            <button type="button" className="btn btn-primary" onClick={onClose}>
              Cerrar
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
