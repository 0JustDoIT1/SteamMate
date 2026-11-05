import { execFileSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";

import type { FullConfig } from "@playwright/test";

/**
 * 로그인 테스트용 세션 쿠키를 만든다. 백엔드의 SessionManager를 그대로 써서(백엔드 Python이 backend/.env의
 * SESSION_SECRET을 읽는다) 실제 Steam 로그인 콜백이 발급하는 것과 같은 쿠키를 만든다.
 * - 쿠키 값은 화면·로그에 출력하지 않고 e2e/.auth/user.json(커밋 금지)에만 쓴다.
 * - E2E_STEAMID가 없으면 빈 상태를 쓰고 로그인 테스트는 건너뛴다.
 * - 운영 구성(8080)도 같은 backend/.env 비밀값을 쓰므로 같은 쿠키가 통한다.
 */
const AUTH_FILE = path.join(__dirname, ".auth", "user.json");
const BACKEND_DIR = path.join(__dirname, "..", "..", "backend");
const PYTHON =
  process.env.E2E_PYTHON ??
  path.join(BACKEND_DIR, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");

const ISSUE = [
  "import sys",
  "from app.auth.session import SessionManager",
  "from app.config import get_settings",
  "s = get_settings()",
  "sys.stdout.write(SessionManager(s.session_secret, s.session_max_age_seconds).issue(sys.argv[1]))",
].join("\n");

export default function globalSetup(config: FullConfig) {
  mkdirSync(path.dirname(AUTH_FILE), { recursive: true });
  const steamId = process.env.E2E_STEAMID ?? "";
  if (!/^\d{17}$/.test(steamId)) {
    writeFileSync(AUTH_FILE, JSON.stringify({ cookies: [], origins: [] }));
    return;
  }
  const token = execFileSync(PYTHON, ["-c", ISSUE, steamId], { cwd: BACKEND_DIR, encoding: "utf-8" }).trim();
  const { hostname } = new URL(config.projects[0].use.baseURL ?? "http://localhost:3000");
  writeFileSync(
    AUTH_FILE,
    JSON.stringify({
      cookies: [
        {
          name: "sm_session",
          value: token,
          domain: hostname,
          path: "/",
          httpOnly: true,
          secure: false,
          sameSite: "Lax",
          expires: Math.floor(Date.now() / 1000) + 3600,
        },
      ],
      origins: [],
    }),
  );
}
