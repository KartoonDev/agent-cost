# ส่ง PR

ยินดีรับทุกขนาด — แก้ตัวเลข, รองรับ agent ใหม่, README ตรงไหนงง

1. fork แล้วแตก branch จาก `main`
2. แก้ แล้วลองกับ ledger ของตัวเองจริง ๆ (`--dry-run` มีให้เกือบทุกคำสั่ง)
3. เปิด PR เข้า `main` — CI จะเช็ค compile + ไม่มีไฟล์ข้อมูลส่วนตัว
4. maintainer รีวิวก่อน merge ทุก PR

## กติกา

- **ห้ามมีข้อมูลของใครใน repo** — ledger, backup, report `.md`, `pricing.json`, `.ide_sync.json`,
  prompt, path ในเครื่อง, ชื่อ repo / โปรเจกต์ของที่ทำงาน, token หรือ key (repo นี้ public)
- ตัวอย่างใน doc ใช้ชื่อสมมติ เช่น `somchai`, `my-service`
- **hook ต้องไม่ทำให้ agent สะดุด** — `capture.py` exit 0 เสมอ, อะไรที่อาจช้าต้องมี timeout
- **ใช้แค่ standard library ของ Python 3.9+** ไม่เพิ่ม dependency
- ทุกตัวที่เขียน ledger ถือ `cost_paths.ledger_lock`
- เปลี่ยนนิยามตัวเลข (token, credit, elapsed, turn) → อัปเดต README / SKILL.md และบอกในคำอธิบาย PR ว่าคนใช้ต้อง `capture.py --rebuild` หรือ `ide_sync.py --resync` ไหม
- commit message: `type(scope): สรุป` เช่น `fix(ide_sync): skip empty requests`

ส่ง PR = ยินยอมให้โค้ดที่ส่งมาใช้ [MIT License](LICENSE) เดียวกับ repo
