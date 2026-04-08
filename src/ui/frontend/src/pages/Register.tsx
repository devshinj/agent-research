import { useState, useEffect } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

const API_BASE = import.meta.env.VITE_API_URL || "";

interface Props {
  onRegister: (
    email: string, password: string, nickname: string, inviteCode: string,
  ) => Promise<any>;
}

export default function Register({ onRegister }: Props) {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [nickname, setNickname] = useState("");
  const [inviteCode, setInviteCode] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [inviteRequired, setInviteRequired] = useState(true);

  useEffect(() => {
    fetch(`${API_BASE}/api/auth/info`)
      .then(r => r.json())
      .then(data => setInviteRequired(data.invite_required))
      .catch(() => {});
  }, []);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    if (password.length < 8) {
      setError("비밀번호는 8자 이상이어야 합니다");
      return;
    }
    setLoading(true);
    try {
      await onRegister(email, password, nickname, inviteCode);
      navigate("/login");
    } catch (err: any) {
      setError(err.message);
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
        <p className="auth-subtitle">새 계정을 만드세요</p>
        <form onSubmit={handleSubmit}>
          {error && <div className="auth-error">{error}</div>}
          <div className="form-group">
            <label>이메일</label>
            <input type="email" placeholder="you@example.com" value={email} onChange={e => setEmail(e.target.value)} required autoFocus />
          </div>
          <div className="form-group">
            <label>닉네임</label>
            <input type="text" placeholder="트레이더 닉네임" value={nickname} onChange={e => setNickname(e.target.value)} required />
          </div>
          <div className="form-group">
            <label>비밀번호</label>
            <input type="password" placeholder="••••••••" value={password} onChange={e => setPassword(e.target.value)} required minLength={8} />
          </div>
          {inviteRequired && (
            <div className="form-group">
              <label>초대 코드</label>
              <input type="text" placeholder="INVITE-XXXX" value={inviteCode} onChange={e => setInviteCode(e.target.value)} required />
            </div>
          )}
          <button type="submit" className="btn btn-primary auth-btn" disabled={loading}>
            {loading ? "가입 중..." : "가입하기"}
          </button>
        </form>
        <div className="auth-divider">또는</div>
        <p className="auth-link">
          이미 계정이 있으신가요? <Link to="/login">로그인</Link>
        </p>
      </div>
    </div>
  );
}
