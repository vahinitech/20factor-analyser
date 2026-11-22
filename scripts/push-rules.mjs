#!/usr/bin/env node
/* SPDX-License-Identifier: AGPL-3.0-only
   © 2026 Vahini Technologies. All rights reserved.

   Push rules (owner, 2026-11-21). A pull request fails the required
   `pr-base` check when:

   1. its branch starts with claude, codex or code (claude/..., codex-...,
      code_...), or is not named <type>/<topic>, such as fix/privacy-notice
      or feat/language-chooser, with a topic of at least three letters.
      Long-lived branches named in LONG_LIVED are allowed as they are.
   2. a commit, the title or the description carries an AI tool's mark:
      a Co-authored-by line naming Claude, Anthropic, Codex, OpenAI or
      ChatGPT, a Claude-Session line, a "Generated with Claude Code" or
      Codex line, or a link to a Claude or Codex session.
   3. a commit's author or committer is Claude, Codex or ChatGPT, or has an
      anthropic.com or openai.com address.

   Usage:
     node scripts/push-rules.mjs --pr <file.json>    CI: {branch, title, body, commits}
     node scripts/push-rules.mjs --local [base]      before a push: this branch against
                                       base (default origin/main)
*/
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

export const AI_BRANCH = /^(claude|codex|code)(?:[/._-]|$)/i;
export const BRANCH = /^[a-z0-9][a-z0-9._-]*\/[a-z0-9][a-z0-9._/-]*$/;
export const LONG_LIVED = new Set(["main", "dpdp_2027"]);
export const MARKS = [
  [/co-authored-by:[^\n]*(claude|anthropic|codex|openai|chatgpt)/i, "a Co-authored-by line naming an AI tool"],
  [/claude-session:/i, "a Claude-Session line"],
  [/generated (?:with|by) \[?(?:claude|codex|chatgpt)/i, "a \"Generated with\" line naming an AI tool"],
  [/claude\.ai\/code\/session_/i, "a link to a Claude session"],
  [/chatgpt\.com\/codex|codex\.openai\.com/i, "a link to a Codex task"],
];
const AI_PERSON = /\b(?:claude|codex|chatgpt)\b|anthropic\.com|openai\.com/i;

export function checkBranch(name) {
  const branch = String(name || "");
  if (LONG_LIVED.has(branch)) return [];
  if (AI_BRANCH.test(branch)) {
    return [`branch "${branch}" starts with claude, codex or code: name it <type>/<topic>, such as fix/privacy-notice`];
  }
  const topic = branch.split("/").slice(1).join("/");
  if (!BRANCH.test(branch) || topic.replace(/[^a-z]/g, "").length < 3) {
    return [`branch "${branch}" is not <type>/<topic> in lower case, such as fix/privacy-notice or feat/language-chooser`];
  }
  return [];
}

export function checkText(where, text) {
  const value = String(text || "");
  return MARKS.filter(([re]) => re.test(value)).map(([, what]) => `${where} has ${what}`);
}

export function checkPerson(where, person) {
  const who = `${person && person.name ? person.name : ""} <${person && person.email ? person.email : ""}>`;
  return AI_PERSON.test(who) ? [`${where} is ${who}: commit as a person, not as an AI tool`] : [];
}

export function check({ branch, title, body, commits = [] }) {
  const problems = [...checkBranch(branch), ...checkText("the title", title), ...checkText("the description", body)];
  for (const c of commits) {
    const id = `commit ${String(c.sha || "").slice(0, 7) || "?"}`;
    problems.push(
      ...checkText(`${id} message`, c.message),
      ...checkPerson(`${id} author`, c.author),
      ...checkPerson(`${id} committer`, c.committer)
    );
  }
  return problems;
}

function localPr(base) {
  const git = (...args) => execFileSync("git", args, { encoding: "utf8" });
  const branch = git("rev-parse", "--abbrev-ref", "HEAD").trim();
  const log = git("log", "--format=%H%x1f%an%x1f%ae%x1f%cn%x1f%ce%x1f%B%x1e", `${base}..HEAD`);
  const commits = log.split("\x1e").map((r) => r.replace(/^\n/, "")).filter(Boolean).map((r) => {
    const [sha, an, ae, cn, ce, message] = r.split("\x1f");
    return { sha, message, author: { name: an, email: ae }, committer: { name: cn, email: ce } };
  });
  return { branch, title: "", body: "", commits };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const [mode, arg] = process.argv.slice(2);
  let pr;
  if (mode === "--pr" && arg) pr = JSON.parse(readFileSync(arg, "utf8"));
  else if (mode === "--local") pr = localPr(arg || "origin/main");
  else {
    console.error("usage: push-rules.mjs --pr <file.json> | --local [base]");
    process.exit(2);
  }
  const problems = check(pr);
  for (const p of problems) console.log(`FAIL ${p}`);
  console.log(problems.length ? `\n${problems.length} push rule(s) broken (CLAUDE.md, "Push rules").` : `push rules: ok (${pr.commits.length} commit(s), branch ${pr.branch})`);
  process.exit(problems.length ? 1 : 0);
}
