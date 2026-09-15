# agent-cost — จดว่า agent แต่ละรอบกินไปเท่าไหร่

ทุกครั้งที่ CodeBuddy CLI หรือ Claude Code ทำงานจบ 1 รอบ มันจะจดลงไฟล์เดียว (`ledger.jsonl`) ว่า
รอบนั้น **ใช้ credit / token เท่าไหร่ กี่วินาที เรียก tool อะไร แตะไฟล์ไหน สั่งว่าอะไร**
แล้วดูเป็น dashboard สด ๆ หรือสั่ง report ออกมาเทียบกันได้ว่างานแบบไหนใช้ตัวไหนคุ้มกว่า

เก็บด้วยสคริปต์ตัวเดียว นิยามเดียวกันทั้งสอง agent — ตัวเลขถึงเอามาเทียบกันได้จริง

**สำหรับทีม:** ทุกคนลงในเครื่องตัวเอง ledger อยู่ในเครื่องใครเครื่องมัน
ถ้าจะดูยอดรวมทีม ให้แต่ละคนส่งไฟล์มาให้คนรวม (ดูหัวข้อ [รวมยอดทั้งทีม](#รวมยอดทั้งทีม))

---

## 1. ติดตั้ง (2 นาที)

ต้องมี `python3` (macOS มีมาให้อยู่แล้ว)

```bash
mkdir -p ~/.claude/skills
git clone https://github.com/thanathe/agent-cost.git ~/.claude/skills/agent-cost
python3 ~/.claude/skills/agent-cost/scripts/install.py
```

ตัวติดตั้งจะถาม 2 ข้อ

1. **เก็บ ledger ไว้ที่ไหน** — Enter = `~/.agent-cost` (แนะนำ: อย่าเลือกโฟลเดอร์ที่อยู่ใน git repo)
2. **จะจด prompt ที่สั่งไปด้วยไหม** — ตอบ `n` ได้ถ้าไม่อยากให้มีข้อความที่พิมพ์อยู่ในไฟล์ จะเหลือแค่ตัวเลข

จากนั้นมันจะ

- ต่อ `Stop` hook เข้า `~/.claude/settings.json` และ `~/.codebuddy/settings.json` (hook เดิมอยู่ครบ + backup ให้)
- symlink skill นี้เข้า skills/ ของทั้งสองตัว เรียก `/agent-cost` ได้
- ลงซ้ำกี่รอบก็ไม่พัง เจอของตัวเองแล้วข้าม

อยากดูก่อนว่าจะแตะอะไร: `install.py --dry-run` · ลงแค่ตัวเดียว: `install.py --only claude` (หรือ `codebuddy`)

**เปิด session ใหม่** ของ agent แล้วมันจะเริ่มเก็บเอง (session ที่เปิดค้างอยู่ยังใช้ hook ชุดเก่า)

### อัปเดต

```bash
git -C ~/.claude/skills/agent-cost pull
python3 ~/.claude/skills/agent-cost/scripts/capture.py --rebuild   # คำนวณ ledger เดิมใหม่ด้วยกติกาล่าสุด (backup ให้ก่อน)
```

ledger ไม่โดน `git pull` แตะ (อยู่คนละที่ + gitignore) · `--rebuild` จำเป็นถ้าลงไว้ก่อน 14 ก.ย. 2026
(รุ่นก่อนหน้านับ token ของ Claude ไม่รวม cache และไม่นับ subagent)

---

## 2. ตั้งราคา (ทำครั้งเดียว ไม่ทำก็ได้)

Claude ไม่มี credit ใน transcript และ CodeBuddy ไม่บอกว่า credit ละกี่บาท — ถ้าไม่ตั้ง จะเห็นแค่ token กับ credit ไม่มีเงิน
สร้าง `pricing.json` ไว้ข้าง ๆ `ledger.jsonl` (โฟลเดอร์ที่เลือกตอนติดตั้ง):

```json
{
  "_plans": {
    "claude":    { "name": "Max 5x", "usd_per_month": 100, "days_per_month": 20 },
    "codebuddy": { "usd_per_credit": 0.005 }
  },
  "claude-opus-5":    { "input": 5,  "output": 25, "cache_read": 0.5,  "cache_write": 6.25 },
  "claude-fable-5-1": { "input": 10, "output": 50, "cache_read": 0.25, "cache_write": 12.5 }
}
```

| key | ใช้ทำอะไร |
|---|---|
| `_plans.claude.usd_per_month` | ค่าแพ็ก Claude ที่จ่ายจริงต่อเดือน (Pro / Max 5x / Max 20x) — ใช้แพ็กเหมาใส่อันนี้ |
| `_plans.claude.days_per_month` | ใส่ = คิดเฉพาะวันที่ใช้ วันละ ค่าแพ็ก ÷ จำนวนนี้ · ไม่ใส่ = หารทุกวันในปฏิทิน |
| `_plans.codebuddy.usd_per_credit` | ราคา 1 credit เป็น USD |
| `claude-*` ต่อ model | ราคา API ต่อ 1M token — ใช้แค่ดูว่า "ถ้าจ่ายตาม API จะเป็นเท่าไหร่" (ใช้ API key จ่ายตาม token จริงก็ใช้ตัวนี้แทนแพ็ก) |

ราคาในตัวอย่างเป็นของเดือน ก.ย. 2026 — เช็คกับหน้าราคาจริงก่อนใช้

---

## 3. ดูผล

### dashboard สด

```bash
python3 ~/.claude/skills/agent-cost/scripts/dashboard.py --open
```

เปิด http://127.0.0.1:8791 ทิ้งไว้ได้เลย ทำงานกับ agent เสร็จแต่ละรอบ ตัวเลขขึ้นเองภายในไม่กี่วินาที
(port ชนก็ `--port 9000`) · ใช้ CodeBuddy แบบแอป IDE ก็ขึ้นเอง dashboard ดึงให้ระหว่างเปิดอยู่

- เทียบ **เงินรวม** ในช่วงวันที่เลือก + ต่อรอบ / ต่อ output token / ต่อ token
- แยกว่า CodeBuddy รอบไหน **เราพิมพ์สั่งเอง** กับรอบไหน **Claude ส่งงานไปให้**
- รอบที่แพงสุด, แยกตาม repo, ข้อสังเกต (เช่นเปลี่ยน model กลาง session ทำให้ cache หลุด)

เปิดได้แค่ในเครื่องตัวเอง ข้อมูลไม่ออกนอกเครื่อง · ราคาที่พิมพ์ในหน้าจำไว้ใน browser ถ้าไม่พิมพ์จะใช้ `pricing.json`

### report เป็น markdown

```bash
R=~/.claude/skills/agent-cost/scripts/report.py
python3 $R                            # เดือนนี้
python3 $R --compare                  # แยกตาม repo
python3 $R --repo my-service          # เฉพาะ repo
python3 $R --since 2026-09-01 --agent codebuddy
python3 $R --month 2026-09 --write    # เขียน 2026-09.md ลงข้าง ๆ ledger
```

หรือถาม agent ตรง ๆ ว่า "เดือนนี้ใช้ credit ไปเท่าไหร่" — skill จะพาไปเอง

### CodeBuddy IDE (แอป desktop)

แอป IDE ไม่มี hook แต่เก็บ usage + credit ต่อรอบไว้ใน history ของมันเองในเครื่อง — `ide_sync.py` อ่านมาลง ledger

| เปิด dashboard อยู่ | ไม่ได้เปิด dashboard |
|---|---|
| ดึงให้เองทุก ~3 วิ ไม่ต้องทำอะไร | ก่อนดู report สั่ง `python3 ~/.claude/skills/agent-cost/scripts/ide_sync.py` |

```bash
S=~/.claude/skills/agent-cost/scripts
python3 $S/ide_sync.py --dry-run   # นับว่าจะเพิ่มกี่รอบ ไม่เขียน
python3 $S/ide_sync.py             # เขียน
python3 $S/ide_sync.py --watch     # ดึงวนทุก 3 วิ (ใช้แทน dashboard ได้)
```

- ลงเป็น `agent: "codebuddy"` + `source: "ide"` → **รวมยอดกับ CLI** · dashboard แยกสี CLI / IDE ในกราฟและตาราง
  และมีตัวเลือก **CodeBuddy: CLI + IDE / CLI เท่านั้น / IDE เท่านั้น** ไว้เทียบทีละแบบ
- ⚠️ **ดึง history ของ IDE ทั้งหมดที่อยู่ในเครื่อง ไม่มีวันเริ่ม** — ครั้งแรกอาจได้ย้อนไปหลายเดือน
  (ไม่ได้ขึ้นกับ `backfill --since`) · report / dashboard กรองตามวันอยู่แล้ว ถ้าจะเทียบกับ Claude ให้เลือกช่วงเดียวกัน
- รอบที่ IDE ยังทำงานไม่จบ ข้ามไว้ รอบหน้าค่อยเก็บ · รอบที่กดยกเลิกกลางทางยังนับ (credit ถูกหักจริง)
- request ที่ไม่มีคำตอบและไม่ถูกคิด credit (ส่งแล้วไม่มีอะไรเกิดขึ้น) **ข้าม ไม่ลง ledger**
- ใช้ **model ที่ตั้งเองใน IDE** (เช่น qwen ผ่าน gateway) → IDE ไม่จด usage ให้ ลงเป็น `agent: "codebuddy-custom"`
  นับจำนวนรอบได้แต่ไม่มี credit/token และ **ไม่ปนยอด CodeBuddy**
- chat ที่ไม่ได้เปิดโปรเจกต์ (IDE สร้างโฟลเดอร์ `~/CodeBuddy/<วันเวลา>` ให้) รวมเป็น repo `codebuddy-chat`
  (automation เป็น `codebuddy-automation`)
- เคย sync ด้วยรุ่นเก่าไว้ → `python3 $S/ide_sync.py --resync` ลบแถว IDE ทั้งหมดแล้วอ่าน history ใหม่ (backup ให้ก่อน)
- จำว่าไฟล์ history ไหนอ่านแล้วใน `.ide_sync.json` ข้าง ๆ ledger — ลบได้ถ้าอยากให้สแกนใหม่ (ไม่นับซ้ำ)
- แอปเก็บ history ไว้ที่ `~/Library/Application Support` (macOS) · `%APPDATA%` (Windows) · `~/.config` (Linux)
  ไม่เจอให้ชี้เอง: `CODEBUDDY_APPDATA=/path/to/appdata python3 $S/ide_sync.py`

### ย้อนเก็บของเก่า (backfill)

hook จดเฉพาะรอบที่จบ **หลัง** ติดตั้ง ของก่อนหน้านั้นยังอยู่ในเครื่อง ดึงเข้า ledger ได้ด้วยคำสั่งเดียว
อ่าน transcript ของ Claude Code + CodeBuddy CLI และ history ของ CodeBuddy IDE **ของเครื่องคนที่รัน** — ใครรันก็ได้ของตัวเอง

```bash
S=~/.claude/skills/agent-cost/scripts
L="$(python3 -c 'import sys,os;sys.path.insert(0,os.path.expanduser("~/.claude/skills/agent-cost/scripts"));import cost_paths;print(os.path.join(cost_paths.ledger_dir(),"ledger.jsonl"))')"

python3 $S/backfill.py --dry-run --since 2026-08-01   # 1) ดูก่อนว่าจะได้กี่รอบ / กี่ token / กี่ credit
cp "$L" "$L.bak-prebackfill"                          # 2) backup
python3 $S/backfill.py --since 2026-08-01             # 3) เขียนจริง
python3 $S/capture.py --rebuild                       # 4) (ออปชัน) เติม via: claude ให้รอบเก่า
```

| option | |
|---|---|
| `--since YYYY-MM-DD` | เอาเฉพาะตั้งแต่วันนี้ — **แนะนำให้ใส่** ไม่ใส่คือเอาทุกอย่างที่มีในเครื่อง |
| `--only claude\|codebuddy\|ide` | เลือกแหล่ง ใส่ซ้ำได้ (`--only claude --only ide`) |
| `--dry-run` | นับอย่างเดียว ไม่เขียน |

- **รันซ้ำได้ ไม่นับซ้ำ** — ใช้ turn key เดียวกับ hook รอบที่ hook จดไว้แล้วข้าม
- ข้ามรอบสุดท้ายของ transcript ที่เพิ่งมีการเขียนใน 10 นาที (อาจยังทำงานอยู่ ปล่อยให้ hook จดตอนจบ)
- token ของ subagent รวมเข้ารอบแม่ให้เหมือน hook · `via: claude` ดูจาก history ไม่ได้ → ต้อง `--rebuild` ต่อ
- **ใช้เวลาหลายนาที** ถ้ามี transcript เยอะ (ต้องอ่านทุกไฟล์) · เปิด agent / dashboard ทิ้งไว้ระหว่างรันได้
- **ledger จะโตขึ้นมาก** (ตัวอย่างจริง: 3 สัปดาห์ของ Claude Code ≈ 1,900 รอบ) report ยังเร็วอยู่
- **ข้อมูลแต่ละแหล่งเริ่มไม่พร้อมกัน** — เช่น CodeBuddy CLI เพิ่งเริ่มใช้ แต่ Claude มีย้อนหลังหลายเดือน
  เวลาเทียบให้ใช้ `--since` ของ report หรือเลือกช่วงวันใน dashboard ให้ครอบช่วงที่มีทั้งสองฝั่ง
- ใช้แพ็กเหมา Claude: ค่าแพ็กคิดตามวันที่มีข้อมูล → ย้อนไปช่วงที่ยังไม่ได้ใช้แพ็กนี้ ตัวเลขช่วงนั้นจะผิด ใส่ `--since` ตั้งแต่วันที่เริ่มแพ็กปัจจุบัน

### เขียนพร้อมกันหลายตัวได้

hook, dashboard (IDE sync), `backfill.py` และ `capture.py --rebuild` เขียน ledger พร้อมกันได้ —
ทุกตัวถือ lock สั้น ๆ (`.ledger.lock`) ตอนเขียน และ `--rebuild` เก็บแถวที่เข้ามาระหว่างที่มันคำนวณให้ ไม่หาย

---

## รวมยอดทั้งทีม

ไม่มี server กลาง — **ทุกคนส่งไฟล์ ledger ของตัวเองให้คนรวม** แล้วคนรวมสั่ง report ทีเดียว

### ฝั่งคนส่ง

ส่งแบบตัดข้อมูลส่วนตัวออก (แนะนำ) — เหลือตัวเลข ชื่อ repo และเวลา ไม่มี prompt / path ไฟล์:

```bash
L="$(python3 -c 'import sys,os;sys.path.insert(0,os.path.expanduser("~/.claude/skills/agent-cost/scripts"));import cost_paths;print(os.path.join(cost_paths.ledger_dir(),"ledger.jsonl"))')"
jq -c '.prompt="" | .files_touched=[] | del(.cwd, .transcript, .ide_history)' "$L" > ~/Desktop/ledger-<ชื่อเรา>.jsonl
```

ไม่มี `jq`: `brew install jq` · ส่งทั้งไฟล์ได้ แต่ข้างในจะมี **prompt ที่พิมพ์ + path ไฟล์ในเครื่อง** ติดไปด้วย

ตั้งชื่อไฟล์ว่า `ledger-<ชื่อ>.jsonl` — ชื่อตรงนั้นคือชื่อที่จะขึ้นใน report

### ฝั่งคนรวม

เอาไฟล์ทุกคนมากองไว้โฟลเดอร์เดียว (**นอก git repo**) แล้ว

```bash
R=~/.claude/skills/agent-cost/scripts/report.py
python3 $R --ledger 'team/ledger-*.jsonl' --month 2026-09            # สรุปรวม + แยกตามคนให้อัตโนมัติ
python3 $R --ledger 'team/ledger-*.jsonl' --owner somchai            # เจาะคนเดียว
python3 $R --ledger 'team/ledger-*.jsonl' --month 2026-09 --write    # เขียน range.md / 2026-09.md
```

- ไฟล์เดียวกันส่งมาซ้ำ (สองชื่อ / ส่งรอบใหม่ทับ) ไม่นับซ้ำ — dedupe ด้วย `turn_key`
- ส่งรอบใหม่ทั้งไฟล์ได้เลย ไม่ต้องตัดเฉพาะส่วนที่เพิ่ม
- **ค่าแพ็ก Claude คิดแยกคน** แล้วค่อยรวม (2 คนใช้ 5 วัน = 2 แพ็ก × 5 วัน) โดยใช้ `pricing.json` ของ **คนรวม**
  → ถ้าในทีมใช้แพ็กต่างกัน ตัวเลขรวมจะเป็นค่าประมาณ ให้ดูรายคนประกอบ
- dashboard อ่านได้แค่ ledger ของเครื่องตัวเอง — ยอดทีมดูผ่าน `report.py`

---

## เก็บอะไรได้ / ไม่ได้

| | CodeBuddy CLI (`cbc`) | CodeBuddy IDE | Claude Code |
|---|---|---|---|
| credit | ✅ ของจริงจาก transcript | ✅ ของจริงจาก history ของ IDE | ❌ ไม่มี (ใช้ `pricing.json`) |
| token / เวลา / tool / prompt | ✅ | ✅ | ✅ |
| เก็บด้วย | Stop hook | dashboard / `ide_sync.py` | Stop hook |
| ของก่อนติดตั้ง | `backfill.py --since` | ดึงทั้งหมดอัตโนมัติ (ไม่มีวันเริ่ม) | `backfill.py --since` |
| subagent (Agent tool) | — | — | ✅ รวมเข้ารอบที่เรียก |
| ถูก Claude เรียกแบบ headless | ✅ ติด `via: claude` | — | ✅ ติด `via: claude` |

- **CodeBuddy IDE ไม่มี hook** แต่เก็บ usage ต่อรอบไว้ในเครื่อง → ลงเป็น `codebuddy` เหมือน CLI (มี `source: "ide"` ไว้แยก)
- **Claude Code ที่ชี้ไป model อื่น** (เช่น gateway ของ qwen) จะขึ้นเป็น `claude-code:qwen` ไม่ปนยอด Claude
- 1 แถว = 1 รอบที่คนสั่ง (ไม่ใช่ 1 API call) — `/model`, `/clear` ระหว่างทางไม่ตัดรอบ

---

## ความเป็นส่วนตัว — อ่านก่อนแชร์

ledger ไม่ถูกส่งไปไหนเอง อยู่ในเครื่องคนใช้ล้วน ๆ แต่ในนั้นมี **prompt ที่พิมพ์ + path ไฟล์ที่ agent แตะ + ชื่อ repo**

- **อย่า commit ledger / `ledger.jsonl.bak-*` / report `.md` / `pricing.json` / `.ide_sync.json` เข้า git** — โดยเฉพาะ repo ที่แชร์กัน
  ถ้าเลือกที่เก็บไว้ใน git repo (เช่น wiki / notes) ใส่ `.gitignore` ก่อน:
  ```gitignore
  agent-cost/*.jsonl
  agent-cost/*.jsonl.*
  agent-cost/*.md
  agent-cost/pricing.json
  agent-cost/.ide_sync.json*
  agent-cost/.ledger.lock
  ```
  (`.ide_sync.json` มี path โฟลเดอร์ในเครื่อง)
  ⚠️ เคยโดนมาแล้ว: `git rm --cached ledger.jsonl && git commit -- ledger.jsonl` จะ **เพิ่มไฟล์กลับเข้าไป**
  (commit แบบระบุ path เอาไฟล์ในเครื่องมาใส่) ให้ `git commit` เฉย ๆ แล้วเช็ค `git ls-files` ว่าว่าง
- ไม่อยากให้จด prompt → `install.py --no-prompts` (มีผลกับรอบหลังจากนั้น) · รอบเก่าใช้ `jq` ตัดก่อนส่งตามด้านบน
- เปลี่ยนที่เก็บทีหลัง: แก้ `~/.config/agent-cost/config.json`
- repo นี้ public — มีแต่โค้ด ไม่มีข้อมูลของใคร

---

## ถอดออก

```bash
python3 ~/.claude/skills/agent-cost/scripts/install.py --uninstall
```

เอา hook กับ symlink ออก — ledger เดิมยังอยู่ ลบเองได้ถ้าไม่เอา

## ไม่ขึ้นเลย / ตัวเลขแปลก

```bash
# ยิง hook มือ ๆ ด้วย transcript ล่าสุด แล้วดูว่ามันบ่นอะไร
T=$(ls -t ~/.claude/projects/*/*.jsonl | head -1)
echo "{\"session_id\":\"test\",\"transcript_path\":\"$T\",\"cwd\":\"$PWD\"}" \
  | AGENT_COST_DEBUG=1 python3 ~/.claude/skills/agent-cost/scripts/capture.py
```

- `turn had no usage — skipped` = รอบนั้นไม่ได้ใช้อะไรจริง ปกติ
- ไม่มี output เลย = hook ยังไม่เข้า → รัน `install.py` ใหม่แล้วดูบรรทัด `settings:` แล้วเปิด session ใหม่
- dashboard ขึ้นแดง "ต่อ server ไม่ได้" = ปิด `dashboard.py` ไปแล้ว รันใหม่
- ตัวเลขดูผิดหลังอัปเดต → `capture.py --rebuild`
- ใช้ IDE แต่ไม่ขึ้น → `ide_sync.py --dry-run` ได้ 0 = หา history ไม่เจอ ลองชี้ `CODEBUDDY_APPDATA`
- backfill แล้วตัวเลข Claude พุ่ง → ย้อนไปก่อนเริ่มแพ็กปัจจุบันหรือเปล่า เอา backup คืนแล้วรันใหม่ด้วย `--since`
- hook พังยังไงก็ **ไม่ทำให้ agent สะดุด** สคริปต์ exit 0 เสมอ

## เจอบั๊ก / อยากได้อะไรเพิ่ม

ยินดีรับ [issue](https://github.com/thanathe/agent-cost/issues) และ PR ทุกขนาด — ตัวเลขผิด, รองรับ agent ตัวอื่น, README ตรงไหนอ่านแล้วงง ก็ส่งมาได้
วิธีส่ง PR + กติกา (สำคัญ: ห้ามมีข้อมูลส่วนตัว) อยู่ใน [CONTRIBUTING.md](CONTRIBUTING.md) — ทุก PR รีวิวก่อน merge

ถ้าเปิด issue เรื่องตัวเลขหรือ hook ไม่ขึ้น แนบ output ของคำสั่ง `AGENT_COST_DEBUG=1` ข้างบนมาด้วยจะช่วยได้มาก — **ลบ path, ชื่อ repo และข้อความ prompt ออกก่อน** (ดู [ความเป็นส่วนตัว](#ความเป็นส่วนตัว--อ่านก่อนแชร์))
