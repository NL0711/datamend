# Replace the `anshu` branch with the MCP work and push it (Windows PowerShell)

The old content of the `anshu` branch is an unrelated project, so a pull request from it into `main` would show thousands of unrelated changes. The clean way is to **rebuild `anshu` from the latest `main`**, add only the new files, and overwrite the remote `anshu` branch. Only `anshu` is touched; `main` and the other branches are not.

You need: Git installed, and write access to `NL0711/datamend` (ask the owner to add you as a collaborator; otherwise fork the repo and use your fork's URL in step 1).

New items in this contribution (copy only these; do not copy the whole zip over a checkout, because if `main` has moved on since the zip was made you would overwrite your teammates' newer work):

```
mcp-service/                               (folder)
docs/mcp/                                  (folder)
docs/contracts/narrator-confirmation-v1.md
Dockerfile.mcp
docker-compose.mcp.yml
```

## 1. Get the repository and tell Git who you are

```powershell
cd C:\Users\<you>\Projects
git clone https://github.com/NL0711/datamend.git datamend-anshu
cd datamend-anshu
git config user.name  "Anshu Jadhav"
git config user.email "<the email of your GitHub account>"
git branch -a                      # you should see remotes/origin/anshu and remotes/origin/main
```

## 2. (Recommended) keep a copy of what is on `anshu` now

```powershell
git push origin origin/anshu:refs/heads/anshu-old-backup
```

This stores the old content under another branch name, so nothing is lost. Skip it only if you are sure you do not need it.

## 3. Recreate `anshu` from the latest `main`

```powershell
git checkout main
git pull origin main
git checkout -B anshu              # creates anshu (or resets your local copy of it) at the current main
git log --oneline -3               # should show main's latest commits, not the old project
```

## 4. Copy in the new files

Unzip `datamend-anshu-branch.zip` somewhere else first, for example `C:\temp\anshu-zip`, then:

```powershell
$src = "C:\temp\anshu-zip\datamend-anshu"
Copy-Item "$src\mcp-service"  .        -Recurse -Force
Copy-Item "$src\docs\mcp"     .\docs\  -Recurse -Force
Copy-Item "$src\docs\contracts\narrator-confirmation-v1.md" .\docs\contracts\
Copy-Item "$src\Dockerfile.mcp", "$src\docker-compose.mcp.yml" .
git status                         # only new (untracked) files should be listed, nothing "modified"
```

## 5. Check it before you push

```powershell
cd mcp-service
python -m unittest discover -s tests -t .      # expect: OK (skipped=1) until the backend's packages are installed
cd ..
```

Better still, once, with the real platform: `pip install -r requirements.txt`, start the backend, start the narrator (`cd mcp-service; python -m datamend_mcp narrator`), set `NARRATOR_URL` and `NARRATOR_TOKEN` in `.env`, restart the backend, and press **Explain (AI)** on a flagged row. With the backend's packages installed, the skipped test also runs and checks the platform's own client against the narrator.

## 6. Commit and push

```powershell
git add mcp-service docs/mcp docs/contracts/narrator-confirmation-v1.md Dockerfile.mcp docker-compose.mcp.yml
git commit -m "Add MCP service: read-only DataMend MCP server and AI narrator"
git push --force-with-lease origin anshu
```

`--force-with-lease` overwrites the remote `anshu` (that is what you want here) but refuses if someone else pushed to it since you cloned. If GitHub answers that the branch is protected, delete `anshu` on GitHub (Branches page, trash icon) and run `git push -u origin anshu` instead.

## 7. Hand over to your friend

On GitHub, open the repository, **Pull requests**, **New pull request**, base `main`, compare `anshu`. The "Files changed" tab should show only the new files listed above (no deleted or modified files). Create the pull request; your friend reviews and presses **Merge pull request**. Paste the section "For the person merging into `main`" of `docs/mcp/ANSHU_BRANCH_DOCUMENTATION.md` into the description.

Or from a terminal, for the person merging:

```powershell
git checkout main
git pull origin main
git merge --no-ff origin/anshu -m "Merge anshu: MCP service"
git push origin main
```

## If something goes wrong

* `git status` shows "modified" files in step 4: you copied too much. `git restore <file>` for each, keep only the new items.
* Wrong branch pushed: `git branch --show-current` before every push.
* Undo the local commit before pushing: `git reset --soft HEAD~1`.
