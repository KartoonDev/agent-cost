## เปลี่ยนอะไร / ทำไม

<!-- สั้น ๆ พอ: แก้ปัญหาอะไร หรือเพิ่มอะไร -->

## ทดสอบยังไง

<!-- เช่น รัน report.py / dashboard.py / ide_sync.py --dry-run กับ ledger ของตัวเอง แล้วตัวเลขเป็นยังไง -->

## เช็คก่อนส่ง

- [ ] ไม่มี `ledger.jsonl`, `*.bak-*`, report `.md`, `pricing.json`, `.ide_sync.json` ติดมา
- [ ] ไม่มี prompt, path ในเครื่อง, ชื่อ repo / โปรเจกต์ของที่ทำงาน, token หรือ key ใน code, commit message หรือ PR นี้
- [ ] ถ้าเปลี่ยนนิยามตัวเลข (token, credit, elapsed, turn) อัปเดต README / SKILL.md แล้ว และบอกว่าต้อง `--rebuild` / `--resync` ไหม
- [ ] hook (`capture.py`) ยัง exit 0 เสมอ ไม่ทำให้ agent ค้าง
