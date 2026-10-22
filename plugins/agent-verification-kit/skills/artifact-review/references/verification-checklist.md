# Verification checklist

One row per claim type: the read-only check, and the signal that confirms or refutes the claim.

| Claim in the artifact | Check | Confirms | Refutes |
|---|---|---|---|
| "File `X` exists" | `ls -la X` | The file is listed | `No such file` |
| "Directory `D` is empty or absent" | `ls -A D` | No output, or `No such file` | Any listed entry |
| "Function `f` is in `X`" | `grep -n "def f\|function f\|f = " X` | A definition line | No match, or a match in another file |
| "Module `M` is the one loaded" | `grep -rn "import.*M\|from .* import" <entrypoint>`; in Python, `python -c "import M; print(M.__file__)"` from the project root | The imported path equals the claimed path | A different file is imported |
| "Line N does Y" | `sed -n 'N-3,N+3p' X` | Line N shows Y | Line numbers drifted; search for the text instead |
| "Command C succeeds" | Run C if it is read-only; else read what C calls | Exit code 0 and the expected output | Non-zero exit, or exit 0 with wrong output |
| "Count is N" | Recount from the source (`wc -l`, `grep -c`, a query) | Same N | A different number |
| "A + B = Total" | Add them | Matches | Does not add up |
| "Config key K is set to V" | `grep -n "K" <config>`; for env, `printenv K` (never print secret values) | V | Missing or different |
| "Version is V" | `<tool> --version`, `pip show <pkg>`, `npm ls <pkg>` | V | Another version |
| "Git state is S" (clean, on branch B, pushed) | `git status -sb`, `git log -1 --oneline`, `git rev-parse --abbrev-ref HEAD` | Matches S | Dirty tree, other branch, ahead or behind |
| "URL or endpoint responds" | `curl -s -o /dev/null -w "%{http_code}" URL`, then read the body | Expected status **and** the expected content | Wrong status, or a 200 that is an error page or a cached reply |
| "Already handled elsewhere" | Find the handling code and read it | The code does exactly that | A comment or TODO only, or a different case |
| "Target is reachable" (for example 95% pass) | Compare the target with the baseline and the input size | Same scale, arithmetically possible | Different units, or above what the input allows |

Rules for every row:

- Read-only checks only. If confirming a claim needs a state change, flag it as unverified instead of running it.
- A 200, an exit code 0 or an empty grep is a proxy, not proof. Confirm the effect (the content, the row, the file) where it matters.
- Record the exact output that settled each claim, so a fix can quote it.
