# Git Command Policy: Read-Only

## Strict Constraints:
1. **Only read-only git commands are permitted**:
   - Allowed: `git status`, `git diff`, `git log`, `git show`, `git branch`.
2. **Never run state-modifying git commands**:
   - Strictly forbidden: `git add`, `git restore`, `git reset`, `git commit`, `git checkout`, `git switch`, `git rm`, `git push`, `git pull`, `git merge`, `git rebase`, `git stash`.
3. **User Exclusivity**:
   - All staging, unstaging, and committing must be handled exclusively by the user.
