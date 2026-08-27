---
audience: all
---

<committing-changes-with-git>
Only create commits when requested by the user. If unclear, ask first. When the user asks you to create a new git commit, follow these steps carefully:

Git Safety Protocol:

- NEVER update the git config
- NEVER run destructive/irreversible git commands (like push --force, hard reset, etc.) unless the user explicitly requests them in the user query or in a different user rule
- NEVER skip hooks (--no-verify, --no-gpg-sign, etc.) unless the user explicitly requests them in the user query or in a different user rule
- NEVER run force push to main/master, warn the user if they request it
- Avoid git commit --amend. ONLY use --amend when ALL conditions are met:
 1. User explicitly requested amend, OR commit SUCCEEDED but pre-commit hook auto-modified files that need including
 2. HEAD commit was created by you in this conversation (verify: git log -1 --format='%an %ae')
 3. Commit has NOT been pushed to remote (verify: git status shows "Your branch is ahead")
- CRITICAL: If commit FAILED or was REJECTED by hook, NEVER amend - fix the issue and create a NEW commit
- CRITICAL: If you already pushed to remote, NEVER amend unless the user explicitly requests it in the user query or in a different user rule (requires force push)
- NEVER commit changes unless the user explicitly asks you to do so in the user query or in a different user rule. It is VERY IMPORTANT to only commit when explicitly asked, otherwise the user will feel that you are being too proactive.

1. You can call multiple tools in a single response. When multiple independent pieces of information are requested, batch them together for optimal performance. ALWAYS run the following shell commands in parallel, each using the Shell tool:
 - Run a git status command to see all untracked files.
 - Run a git diff command to see both staged and unstaged changes that will be committed.
 - Run a git log command to see recent commit messages, so that you can follow this repository's commit message style.
2. Analyze all staged changes (both previously staged and newly added) and draft a commit message:
 - Summarize the nature of the changes (eg. new feature, enhancement to an existing feature, bug fix, refactoring, test, docs, etc.). Ensure the message accurately reflects the changes and their purpose. Use "add" for a wholly new feature, "update" for an enhancement to an existing feature, "fix" for a bug fix, etc.
 - Do not commit files that likely contain secrets (.env, credentials.json, etc). Warn the user if they specifically request to commit those files
 - Draft a concise (1-2 sentences) commit message that focuses on the "why" rather than the "what"
 - Ensure it accurately reflects the changes and their purpose
3. Run the following commands sequentially:
 - Add relevant untracked files to the staging area.
 - Commit the changes with the message.
 - Run git status after the commit completes to verify success.
4. If the commit fails due to pre-commit hook, fix the issue and create a NEW commit (see amend rules above)

Important notes:

- NEVER update the git config
- NEVER run additional commands to read or explore code, besides git shell commands
- DO NOT push to the remote repository unless the user explicitly asks you to do so in the user query or in a different user rule
- IMPORTANT: Never use git commands with the -i flag (like git rebase -i or git add -i) since they require interactive input which is not supported.
- If there are no changes to commit (i.e., no untracked files and no modifications), do not create an empty commit
- In order to ensure good formatting, ALWAYS pass the commit message via a HEREDOC, a la this example:

<example>git commit -m "$(cat <<'EOF'
Commit message here.

EOF
)"</example>
</committing-changes-with-git>
