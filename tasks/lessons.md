# KeyForge Lessons

> Append-only log of corrections from Domenic. After ANY redirect, add a row with date, the situation, and the rule to apply going forward.

| Date | Situation | Lesson |
|------|-----------|--------|
| 2026-04-26 | Domenic asked whether KeyForge generates keys; the answer is no. He stated the goal is non-technical users + key generation. | The goal is category-change (vault to issuer), not polish. Evaluate every proposed change against "does this help a non-technical user get and use a credential without ever seeing the word PAT?" |
| 2026-05-03 | While picking a host port for the frontend override, I suggested `3001` without checking what was actually in use; Domenic said "Check the ports before assigning." | Before recommending any port number, run `docker ps` AND `Get-NetTCPConnection -State Listen` (or `netstat -ano`) and survey the candidate range. Recommendations made without survey may collide with whatever else is running on the dev machine. |
