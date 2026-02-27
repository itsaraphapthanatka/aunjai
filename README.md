# Nong Unjai Video Editor & Knowledge Base 🐘

โปรเจกต์นี้ประกอบด้วย 3 ส่วนหลัก:
1. **Video Editor (Web UI)**: สำหรับค้นหาคลิปจากฐานข้อมูล, ดึงและตัดคลิปอัตโนมัติจาก YouTube URL ผ่าน OpenClaw AI พร้อมสร้าง Quiz เข้า Pinecone
2. **MAAC Webhook Middleware**: จัดการ webhook จาก Crescendo Lab (LINE MAAC) ไปยัง Unjai AI agent
3. **Knowledge Base / Vector Store**: นำ transcript ของวิดีโอไปทำ Chunking, สร้าง Embeddings และจัดเก็บลง Pinecone

---

## 🛠️ ข้อควรระวังและการจัดเตรียม Requirements

โปรแกรมจำเป็นต้องใช้แพ็กเกจเหล่านี้ (อยู่ใน `requirements.txt`):
```bash
pip install -r requirements.txt
```

### การตั้งค่า Environment (`.env`)
ให้ก็อปปี้ไฟล์ `.env.example` เป็น `.env` (ถ้ายังไม่มีให้สร้างไฟล์ `.env` ตามข้อมูลตัวอย่างด้านล่าง) และแก้ไขค่าต่างๆ:

```env
# === Pinecone Configuration ===
PINECONE_API_KEY=your_pinecone_api_key
PINECONE_INDEX_NAME=aunjai-knowledge

# === OpenClaw Configuration ===
OPENCLAW_API_URL=http://your_openclaw_url:port
OPENCLAW_AGENT_ID=unjai
OPENCLAW_API_KEY=your_openclaw_key
```

### การตั้งค่า FFmpeg
การตัดวิดีโอต้องพึ่งพาคลิปวิดีโอ (FFmpeg) โปรเจกต์นี้ติดตั้งแพ็กเกจ `imageio-ffmpeg` ไว้แล้ว ซึ่งจะติดตั้ง binary ของ FFmpeg มาให้ในตัว ทำให้ **ไม่จำเป็น** ต้องติดตั้ง FFmpeg ในระดับ OS เอง (แต่ถ้าคุณมีอยู่แล้ว โปรแกรมก็จะใช้ตัวที่มีได้เช่นกัน)

---

## 🚀 วิธีการรันระบบ (How to Run)

1. เปิด Terminal / Command Prompt
2. เข้าไปในโฟลเดอร์ของโปรเจกต์:
   ```bash
   cd c:/project/aunjai
   ```
3. รันเซิร์ฟเวอร์ด้วย `uvicorn` (หรือคำสั่งรันจาก Python โดยตรง):
   ```bash
   # หากใช้งานใน Virtual Environment (.venv) อย่าลืม Activate ก่อน
   uvicorn api_server:app --reload --host 127.0.0.1 --port 8000
   ```
4. เปิดเบราว์เซอร์และเข้าไปที่:
   **[http://127.0.0.1:8000/editor](http://127.0.0.1:8000/editor)**

---

## 📋 ฟีเจอร์ของ Video Editor UI

- **ค้นหาคลิป**: ค้นหาวิดีโอเก่าที่ถูกตัดไว้อยู่แล้ว (จาก Pinecone) 
- **นำเข้า (Import Pipeline)**: โหลดวิดีโอ YouTube ลง Chunk, แปลง Embedding, และบันทึกลงคลัสเตอร์หลัก
- **วิเคราะห์ Highlight (OpenClaw)**: ส่ง Transcript ให้ Agent วิเคราะห์ว่าจุดไหนคือ Shot เด็ด พร้อมตัดคลิปช่วงนั้นให้ดาวน์โหลดและสร้างคำถาม Quiz
- **ดึงวิดีโอจาก Channel**: ดึงข้อมูลและรายการวิดีโอทั้งหมดของ YouTube Channel ที่กำหนด และสามารถ "วิเคราะห์ทั้งหมด" เป็นคิว (Batch Processing) ได้
