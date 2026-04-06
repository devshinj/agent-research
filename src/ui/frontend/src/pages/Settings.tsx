import { useCallback, useEffect, useState } from "react";
import { useApi } from "../hooks/useApi";

type SystemStatus = "running" | "paused" | "unknown";

type ConfigValues = {
  paper_trading: {
    initial_balance: number;
    max_position_pct: number;
    max_open_positions: number;
    fee_rate: number;
    slippage_rate: number;
    min_order_krw: number;
  };
  risk: {
    stop_loss_pct: number;
    take_profit_pct: number;
    trailing_stop_pct: number;
    max_daily_loss_pct: number;
    max_daily_trades: number;
    consecutive_loss_limit: number;
    cooldown_minutes: number;
  };
  screening: {
    min_volume_krw: number;
    min_volatility_pct: number;
    max_volatility_pct: number;
    max_coins: number;
    refresh_interval_min: number;
    always_include: string[];
  };
  strategy: {
    lookahead_minutes: number;
    threshold_pct: number;
    retrain_interval_hours: number;
    min_confidence: number;
  };
  collector: {
    candle_timeframe: number;
    max_candles_per_market: number;
    market_refresh_interval_min: number;
  };
  data: {
    db_path: string;
    model_dir: string;
    stale_candle_days: number;
    stale_model_days: number;
    stale_order_days: number;
  };
};

const FIELD_META: {
  section: keyof ConfigValues;
  label: string;
  fields: { key: string; label: string; type: "number" | "text"; suffix?: string }[];
}[] = [
  {
    section: "paper_trading",
    label: "모의매매",
    fields: [
      { key: "initial_balance", label: "초기 잔고", type: "number", suffix: "KRW" },
      { key: "max_position_pct", label: "최대 포지션 비중", type: "number" },
      { key: "max_open_positions", label: "최대 동시 포지션", type: "number" },
      { key: "fee_rate", label: "수수료율", type: "number" },
      { key: "slippage_rate", label: "슬리피지율", type: "number" },
      { key: "min_order_krw", label: "최소 주문금액", type: "number", suffix: "KRW" },
    ],
  },
  {
    section: "risk",
    label: "리스크",
    fields: [
      { key: "stop_loss_pct", label: "손절 비율", type: "number" },
      { key: "take_profit_pct", label: "익절 비율", type: "number" },
      { key: "trailing_stop_pct", label: "트레일링 스탑", type: "number" },
      { key: "max_daily_loss_pct", label: "일일 최대 손실", type: "number" },
      { key: "max_daily_trades", label: "일일 최대 거래", type: "number" },
      { key: "consecutive_loss_limit", label: "연속 손실 한도", type: "number" },
      { key: "cooldown_minutes", label: "쿨다운 시간", type: "number", suffix: "분" },
    ],
  },
  {
    section: "screening",
    label: "스크리닝",
    fields: [
      { key: "min_volume_krw", label: "최소 거래량", type: "number", suffix: "KRW" },
      { key: "min_volatility_pct", label: "최소 변동성", type: "number", suffix: "%" },
      { key: "max_volatility_pct", label: "최대 변동성", type: "number", suffix: "%" },
      { key: "max_coins", label: "최대 코인 수", type: "number" },
      { key: "refresh_interval_min", label: "갱신 주기", type: "number", suffix: "분" },
      { key: "always_include", label: "항상 포함", type: "text" },
    ],
  },
  {
    section: "strategy",
    label: "전략",
    fields: [
      { key: "lookahead_minutes", label: "예측 시간", type: "number", suffix: "분" },
      { key: "threshold_pct", label: "임계값", type: "number" },
      { key: "retrain_interval_hours", label: "재학습 주기", type: "number", suffix: "시간" },
      { key: "min_confidence", label: "최소 신뢰도", type: "number" },
    ],
  },
  {
    section: "collector",
    label: "수집",
    fields: [
      { key: "candle_timeframe", label: "캔들 주기", type: "number", suffix: "분" },
      { key: "max_candles_per_market", label: "마켓당 최대 캔들", type: "number" },
      { key: "market_refresh_interval_min", label: "마켓 갱신 주기", type: "number", suffix: "분" },
    ],
  },
  {
    section: "data",
    label: "데이터",
    fields: [
      { key: "db_path", label: "DB 경로", type: "text" },
      { key: "model_dir", label: "모델 디렉토리", type: "text" },
      { key: "stale_candle_days", label: "캔들 유효기간", type: "number", suffix: "일" },
      { key: "stale_model_days", label: "모델 유효기간", type: "number", suffix: "일" },
      { key: "stale_order_days", label: "주문 유효기간", type: "number", suffix: "일" },
    ],
  },
];

const HOT_RELOAD_FIELDS: Record<string, Set<string>> = {
  risk: new Set([
    "stop_loss_pct", "take_profit_pct", "trailing_stop_pct",
    "max_daily_trades", "consecutive_loss_limit", "cooldown_minutes",
  ]),
  strategy: new Set(["min_confidence"]),
  screening: new Set([
    "min_volume_krw", "min_volatility_pct", "max_volatility_pct",
    "max_coins", "always_include",
  ]),
};

function isHotReloadable(section: string, key: string): boolean {
  return HOT_RELOAD_FIELDS[section]?.has(key) ?? false;
}

function formatDisplay(section: string, key: string, value: unknown): string {
  if (key === "always_include" && Array.isArray(value)) return value.join(", ");
  if (key === "initial_balance" || key === "min_order_krw")
    return `\u20A9${Number(value).toLocaleString()}`;
  if (key === "min_volume_krw") return `\u20A9${Number(value).toLocaleString()}`;
  if (key.endsWith("_pct") && section !== "screening")
    return `${(Number(value) * 100).toFixed(2)}%`;
  if (key.endsWith("_pct") && section === "screening") return `${value}%`;
  return String(value);
}

export default function Settings() {
  const { get, post, postJson, patchJson } = useApi();
  const [status, setStatus] = useState<SystemStatus>("running");
  const [loading, setLoading] = useState(false);
  const [editMode, setEditMode] = useState(false);
  const [config, setConfig] = useState<ConfigValues | null>(null);
  const [form, setForm] = useState<ConfigValues | null>(null);
  const [showConfirm, setShowConfirm] = useState(false);
  const [hotEditMode, setHotEditMode] = useState(false);

  useEffect(() => {
    get<ConfigValues>("/api/control/config").then((data) => {
      setConfig(data);
      setForm(structuredClone(data));
    });
  }, [get]);

  const handlePause = async () => {
    setLoading(true);
    const res = await post<{ status: string }>("/api/control/pause");
    setStatus(res.status as SystemStatus);
    setLoading(false);
  };

  const handleResume = async () => {
    setLoading(true);
    const res = await post<{ status: string }>("/api/control/resume");
    setStatus(res.status as SystemStatus);
    setLoading(false);
  };

  const handleStartReset = async () => {
    await handlePause();
    setEditMode(true);
  };

  const handleCancelReset = async () => {
    setEditMode(false);
    setForm(config ? structuredClone(config) : null);
    await handleResume();
  };

  const handleStartHotEdit = () => {
    setHotEditMode(true);
    setForm(config ? structuredClone(config) : null);
  };

  const handleCancelHotEdit = () => {
    setHotEditMode(false);
    setForm(config ? structuredClone(config) : null);
  };

  const handleApplyHotReload = async () => {
    if (!form || !config) return;
    setLoading(true);

    const patch: Record<string, Record<string, unknown>> = {};
    for (const { section, fields } of FIELD_META) {
      for (const { key } of fields) {
        if (!isHotReloadable(section, key)) continue;
        const oldVal = (config[section] as Record<string, unknown>)[key];
        const newVal = (form[section] as Record<string, unknown>)[key];
        if (JSON.stringify(oldVal) !== JSON.stringify(newVal)) {
          if (!patch[section]) patch[section] = {};
          patch[section][key] = newVal;
        }
      }
    }

    if (Object.keys(patch).length === 0) {
      setHotEditMode(false);
      setLoading(false);
      return;
    }

    const res = await patchJson<{ status: string; config: ConfigValues }>("/api/control/config", patch);
    setConfig(res.config);
    setForm(structuredClone(res.config));
    setHotEditMode(false);
    setLoading(false);
  };

  const handleConfirmReset = async () => {
    if (!form) return;
    setShowConfirm(false);
    setLoading(true);
    const res = await postJson<{ status: string }>("/api/control/reset", form);
    setStatus(res.status as SystemStatus);
    setConfig(structuredClone(form));
    setEditMode(false);
    setLoading(false);
  };

  const updateField = useCallback(
    (section: keyof ConfigValues, key: string, value: string) => {
      setForm((prev) => {
        if (!prev) return prev;
        const next = structuredClone(prev);
        const sec = next[section] as Record<string, unknown>;
        if (key === "always_include") {
          sec[key] = value.split(",").map((s) => s.trim()).filter(Boolean);
        } else if (key === "db_path" || key === "model_dir") {
          sec[key] = value;
        } else {
          const num = Number(value);
          if (!isNaN(num)) sec[key] = num;
        }
        return next;
      });
    },
    [],
  );

  const inputValue = (section: keyof ConfigValues, key: string): string => {
    if (!form) return "";
    const sec = form[section] as Record<string, unknown>;
    const val = sec[key];
    if (key === "always_include" && Array.isArray(val)) return val.join(", ");
    return String(val ?? "");
  };

  return (
    <div>
      <div className="page-header">
        <h2>설정</h2>
        <div className="page-sub">시스템 제어 및 구성</div>
      </div>

      {/* ── System Control ─────────────────── */}
      <div className="panel">
        <div className="panel-header">
          <h3>시스템 제어</h3>
          <span
            className={`badge ${status === "running" ? "profit" : status === "paused" ? "warn" : "neutral"}`}
          >
            {status.toUpperCase()}
          </span>
        </div>
        <div className="panel-body">
          <div style={{ display: "flex", alignItems: "center", gap: 20, padding: "18px 0" }}>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 15, fontWeight: 600, color: "var(--text)", letterSpacing: "-0.01em" }}>
                모의매매 엔진
              </div>
              <div style={{ fontSize: 14, color: "var(--text-dim)", marginTop: 6, lineHeight: 1.5 }}>
                {editMode
                  ? "시스템이 일시 정지되었습니다. 설정을 조정한 후 적용하세요."
                  : status === "running"
                    ? "엔진이 시장을 모니터링하며 모의매매를 실행 중입니다."
                    : status === "paused"
                      ? "매매가 일시 중지되었습니다. 새로운 포지션이 개시되지 않습니다."
                      : "시스템 상태를 알 수 없습니다."}
              </div>
            </div>
            <div style={{ display: "flex", gap: 12 }}>
              {!editMode && (
                <>
                  {status === "running" ? (
                    <button className="btn btn-danger" onClick={handlePause} disabled={loading}>
                      {loading ? "..." : "일시정지"}
                    </button>
                  ) : (
                    <button className="btn btn-primary" onClick={handleResume} disabled={loading}>
                      {loading ? "..." : "재개"}
                    </button>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* ── Configuration ──────────────────── */}
      <div className="panel">
        <div className="panel-header">
          <h3>매매 설정</h3>
          {editMode ? (
            <span className="badge warn">초기화 편집 중</span>
          ) : hotEditMode ? (
            <span className="badge" style={{ background: "var(--accent)", color: "#fff" }}>설정 변경 중</span>
          ) : (
            <div style={{ display: "flex", gap: 8 }}>
              <button className="btn btn-primary" onClick={handleStartHotEdit} disabled={loading}>
                설정 변경
              </button>
              <button className="btn btn-danger" onClick={handleStartReset} disabled={loading}>
                초기화 &amp; 재설정
              </button>
            </div>
          )}
        </div>
        <div className="panel-body">
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: 8,
              fontFamily: "var(--font-mono)",
              fontSize: 14,
            }}
          >
            {FIELD_META.map(({ section, label, fields }) => (
              <div key={section} style={{ padding: "14px 0" }}>
                <div
                  style={{
                    fontSize: 12.5,
                    fontWeight: 700,
                    textTransform: "uppercase",
                    letterSpacing: "0.05em",
                    color: "var(--accent)",
                    marginBottom: 14,
                    fontFamily: "var(--font-ui)",
                  }}
                >
                  {label}
                </div>
                {fields.map(({ key, label: fieldLabel, type }) => (
                  <div
                    key={key}
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      padding: "8px 0",
                      borderBottom: "1px solid rgba(31, 45, 64, 0.4)",
                    }}
                  >
                    <span style={{ color: "var(--text-dim)" }}>{fieldLabel}</span>
                    {(editMode || hotEditMode) && form ? (
                      <input
                        type={type}
                        value={inputValue(section, key)}
                        onChange={(e) => updateField(section, key, e.target.value)}
                        disabled={hotEditMode && !isHotReloadable(section, key)}
                        style={{
                          width: 160,
                          padding: "4px 8px",
                          background: hotEditMode && !isHotReloadable(section, key)
                            ? "var(--bg)" : "var(--card)",
                          border: "1px solid var(--border)",
                          borderRadius: 4,
                          color: hotEditMode && !isHotReloadable(section, key)
                            ? "var(--text-dim)" : "var(--text)",
                          fontFamily: "var(--font-mono)",
                          fontSize: 13,
                          textAlign: "right",
                          opacity: hotEditMode && !isHotReloadable(section, key) ? 0.5 : 1,
                        }}
                      />
                    ) : (
                      <span style={{ color: "var(--text)" }}>
                        {config ? formatDisplay(section, key, (config[section] as Record<string, unknown>)[key]) : "..."}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            ))}
          </div>

          {(editMode || hotEditMode) && (
            <div
              style={{
                display: "flex",
                justifyContent: "flex-end",
                gap: 12,
                marginTop: 20,
                paddingTop: 16,
                borderTop: "1px solid var(--border)",
              }}
            >
              <button
                className="btn"
                onClick={editMode ? handleCancelReset : handleCancelHotEdit}
                disabled={loading}
              >
                취소
              </button>
              {editMode ? (
                <button
                  className="btn btn-primary"
                  onClick={() => setShowConfirm(true)}
                  disabled={loading}
                >
                  적용 &amp; 시작
                </button>
              ) : (
                <button
                  className="btn btn-primary"
                  onClick={handleApplyHotReload}
                  disabled={loading}
                >
                  적용
                </button>
              )}
            </div>
          )}
        </div>
      </div>

      {/* ── About ──────────────────────────── */}
      <div className="panel">
        <div className="panel-header">
          <h3>정보</h3>
        </div>
        <div className="panel-body">
          <div
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: 14,
              color: "var(--text-dim)",
              lineHeight: 2.0,
            }}
          >
            <div>Crypto Paper Trader v0.1.0</div>
            <div>Upbit ML Strategy &mdash; LightGBM / XGBoost</div>
            <div>
              6-Layer Architecture: types &rarr; config &rarr; repository &rarr; service &rarr;
              runtime &rarr; ui
            </div>
          </div>
        </div>
      </div>

      {/* ── Confirmation Modal ─────────────── */}
      {showConfirm && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0, 0, 0, 0.6)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 1000,
          }}
          onClick={() => setShowConfirm(false)}
        >
          <div
            style={{
              background: "var(--card)",
              border: "1px solid var(--border)",
              borderRadius: 12,
              padding: 32,
              maxWidth: 420,
              width: "90%",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <h3 style={{ margin: "0 0 12px", color: "var(--text)" }}>초기화 확인</h3>
            <p style={{ color: "var(--text-dim)", lineHeight: 1.6, margin: "0 0 24px" }}>
              잔고와 거래내역이 모두 초기화됩니다.
              <br />
              학습 데이터와 모델은 유지됩니다.
              <br />
              진행하시겠습니까?
            </p>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 12 }}>
              <button className="btn" onClick={() => setShowConfirm(false)}>
                취소
              </button>
              <button className="btn btn-danger" onClick={handleConfirmReset}>
                확인
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
