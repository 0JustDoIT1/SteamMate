// PostToolUse(Edit|Write): 수정된 파일에 lint를 실행하고, 문제가 있으면 Claude에게 알린다.
// backend/**/*.py → ruff, frontend/**/*.ts(x) → eslint. 도구가 없으면 조용히 통과한다.
const { spawnSync } = require("child_process");
const fs = require("fs");
const path = require("path");

let raw = "";
process.stdin.on("data", (c) => (raw += c));
process.stdin.on("end", () => {
  let file = "";
  try {
    const input = JSON.parse(raw);
    file = input.tool_input?.file_path ?? input.tool_response?.filePath ?? "";
  } catch {
    process.exit(0);
  }
  if (!file) process.exit(0);

  const root = process.env.CLAUDE_PROJECT_DIR || process.cwd();
  const rel = path.relative(root, path.resolve(file)).split(path.sep).join("/");
  let result = null;

  if (/^backend\/.*\.py$/.test(rel)) {
    const ruff = path.join(root, "backend", ".venv", "Scripts", "ruff.exe");
    if (!fs.existsSync(ruff)) process.exit(0);
    result = spawnSync(ruff, ["check", path.relative(path.join(root, "backend"), file)], {
      cwd: path.join(root, "backend"),
      encoding: "utf8",
    });
  } else if (/^frontend\/.*\.(ts|tsx)$/.test(rel)) {
    const eslint = path.join(root, "frontend", "node_modules", ".bin", "eslint.cmd");
    if (!fs.existsSync(eslint)) process.exit(0);
    result = spawnSync(eslint, [path.relative(path.join(root, "frontend"), file)], {
      cwd: path.join(root, "frontend"),
      encoding: "utf8",
      shell: true,
    });
  } else {
    process.exit(0);
  }

  if (result.status !== 0) {
    process.stderr.write(`lint 실패 (${rel}):\n${result.stdout}${result.stderr}`);
    process.exit(2);
  }
  process.exit(0);
});
