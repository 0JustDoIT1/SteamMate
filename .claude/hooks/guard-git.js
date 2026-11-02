// PreToolUse(Bash): 승인 없이 실행하면 안 되는 git 명령을 차단한다 (CLAUDE.md Git 규칙).
// exit 2 = 도구 실행 차단, stderr 메시지가 Claude에게 전달된다.
let raw = "";
process.stdin.on("data", (c) => (raw += c));
process.stdin.on("end", () => {
  let cmd = "";
  try {
    cmd = JSON.parse(raw).tool_input?.command ?? "";
  } catch {
    process.exit(0);
  }

  const rules = [
    [/\bgit\s+push\b/, "git push"],
    [/\bgit\s+reset\s+[^;&|]*--hard\b/, "git reset --hard"],
    [/\bgit\s+rebase\b/, "git rebase"],
    [/\bgit\s+branch\s+[^;&|]*(-D\b|--delete\b|-d\b)/, "git branch 삭제"],
    [/\bgit\s+commit\s+[^;&|]*--amend\b/, "git commit --amend"],
    [/\bgit\s+[^;&|]*(--force\b|--force-with-lease\b)/, "--force"],
    [/\bgit\s+clean\s+[^;&|]*-[a-zA-Z]*f/, "git clean -f"],
  ];

  const hit = rules.find(([re]) => re.test(cmd));
  if (hit) {
    process.stderr.write(
      `차단됨: '${hit[1]}'은(는) 사용자 사전 승인이 필요합니다 (CLAUDE.md Git 규칙). 사용자에게 직접 실행하거나 승인해 달라고 요청하세요.`
    );
    process.exit(2);
  }
  process.exit(0);
});
