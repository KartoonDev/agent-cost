---
name: ตัวเลขผิด / hook ไม่ขึ้น
about: รายงานบั๊ก
---

**เกิดอะไรขึ้น / คาดว่าควรเป็นยังไง**

**agent ที่ใช้** (Claude Code / CodeBuddy CLI / CodeBuddy IDE) และ OS

**output ของ debug** — ลบ path, ชื่อ repo และข้อความ prompt ออกก่อนแปะ

```
T=$(ls -t ~/.claude/projects/*/*.jsonl | head -1)
echo "{\"session_id\":\"test\",\"transcript_path\":\"$T\",\"cwd\":\"$PWD\"}" \
  | AGENT_COST_DEBUG=1 python3 ~/.claude/skills/agent-cost/scripts/capture.py
```
