import { useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";

interface Props {
  onLogin: (email: string, password: string) => Promise<void>;
}

const ERROR_MESSAGES: Record<string, string> = {
  "Invalid credentials": "이메일 또는 비밀번호가 올바르지 않습니다",
  "Account is deactivated": "비활성화된 계정입니다",
  "User not found or inactive": "사용자를 찾을 수 없거나 비활성 상태입니다",
  "Failed to fetch": "서버에 연결할 수 없습니다",
  "Network request failed": "네트워크 연결을 확인해주세요",
};

function toKoreanError(message: string): string {
  return ERROR_MESSAGES[message] ?? "로그인에 실패했습니다. 다시 시도해주세요";
}

export default function Login({ onLogin }: Props) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await onLogin(email, password);
    } catch (err: any) {
      setError(toKoreanError(err.message));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-container">
      <div className="auth-card">
        <h1 className="auth-title">
          PAPER<span className="auth-title-accent">&nbsp;TRADER</span>
        </h1>
        <p className="auth-subtitle">계정에 로그인하세요</p>
        <form onSubmit={handleSubmit}>
          {error && <div className="auth-error">{error}</div>}
          <div className="form-group">
            <label>이메일</label>
            <input
              type="email"
              placeholder="you@example.com"
              value={email}
              onChange={e => setEmail(e.target.value)}
              required
              autoFocus
            />
          </div>
          <div className="form-group">
            <label>비밀번호</label>
            <input
              type="password"
              placeholder="••••••••"
              value={password}
              onChange={e => setPassword(e.target.value)}
              required
            />
          </div>
          <button type="submit" className="btn btn-primary auth-btn" disabled={loading}>
            {loading ? "로그인 중..." : "로그인"}
          </button>
        </form>
        <div className="auth-divider">또는</div>
        <p className="auth-link">
          계정이 없으신가요? <Link to="/register">회원가입</Link>
        </p>
      </div>
    </div>
  );
}
