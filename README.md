# RaaS GraphRAG System

Hệ thống GraphRAG-as-a-Service đang ở giai đoạn hoàn thiện luồng nền tảng: cấu hình AI provider/model, ingest tài liệu, lưu vector vào LanceDB, lưu graph structure vào Kuzu, visualize/debug retrieval, rồi tiến tới chat từ tài liệu.

## Yêu Cầu

- Python 3.13 hoặc phiên bản tương thích với `requirements.txt`
- Node.js `^20.19.0` hoặc `>=22.12.0`
- Docker + Docker Compose
- PostgreSQL/Redis chạy qua `docker-compose.yml`

## Cài Đặt Backend

Tạo virtualenv và cài package Python:

```bash
python -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Tạo file môi trường:

```bash
cp .env.example .env
```

Kiểm tra các biến PostgreSQL trong `.env` khớp với `docker-compose.yml`, tối thiểu:

```env
POSTGRES_USER=graphrag_user
POSTGRES_PASSWORD=your_password_here
POSTGRES_DB=graphrag_db
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
```

## Chạy Database

```bash
docker compose up -d
```

Chạy migration:

```bash
.venv/bin/alembic upgrade head
```

Runtime data sẽ nằm trong:

- `data/documents`
- `data/lancedb`
- `data/kuzu/graph.db`

Không commit các thư mục runtime này.

## Cài Đặt Frontend

```bash
cd ui
npm install
```

## Chạy Dự Án Khi Dev

Terminal 1, chạy backend:

```bash
. .venv/bin/activate
uvicorn app.main:app --reload
```

Backend mặc định chạy ở:

```text
http://localhost:8000
```

Terminal 2, chạy frontend:

```bash
cd ui
npm run dev
```

Frontend mặc định chạy ở:

```text
http://localhost:5173
```

Vite đã proxy `/api` và `/embed` về backend `http://localhost:8000`.

## Bước Bắt Buộc Trước Khi Ingest/Chat

Trước khi upload tài liệu hoặc test chat, phải vào:

```text
http://localhost:5173/platform
```

Tại `/platform`, cấu hình AI theo thứ tự:

1. Tạo provider Gemini với `code=gemini` cho embedding.
2. Nhập một Gemini API key thật.
3. Tạo một embedding model profile Gemini, ví dụ model `gemini-embedding-001`, và chốt `embedding_dimensions` cho LanceDB index.
4. Tạo LLM model profile.
5. Đảm bảo profile/key/provider đang enabled và không bị locked.

Lý do: ingest tài liệu hiện gọi Gemini embedding qua package `google-genai` để tạo vector và lưu vào LanceDB. Embedding runtime chỉ hydrate đúng một Gemini profile/API key, không xoay key và không trộn provider/model. LLM vẫn dùng pool xoay vòng riêng qua LiteLLM. Nếu chưa có embedding profile/API key hợp lệ, các route ingest/search/chat sẽ không có model để chạy.

## Luồng Kiểm Tra Hiện Tại

1. Vào `/platform` cấu hình provider/API key/model profiles.
2. Vào `/admin/documents`.
3. Upload tài liệu.
4. Sau khi ingest xong, mở khung `Visualization`.
5. Tab `Vector`:
   - Nhập một câu hỏi test.
   - Hệ thống embed câu hỏi, search LanceDB, trả top matches.
   - Xem similarity, distance, chunk text, metadata và graph context nếu có.
   - Xem bảng embedding health để kiểm tra dimension, số chunk đã embed và chunk thiếu embedding.
6. Tab `Graph` hiển thị document/chunk/entity graph từ Kuzu và cho phép lọc, đổi layout, xem chi tiết node/edge.

## Route Chính

- Platform admin UI: `/platform`
- Document admin UI: `/admin/documents`
- Embeddable chat UI: `/embed/chat`
- Provider/model/key API: `/api/v1/platform/ai/...`
- Ingest API: `POST /api/v1/ingest`
- Query vector debug cũ: `POST /api/v1/ingest/query`
- Visualize vector search: `POST /api/v1/visualize/vector/search`
- Visualize vector health: `POST /api/v1/visualize/vector/health`

## Kiểm Tra

Backend:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s test
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m compileall -q app
```

Frontend:

```bash
cd ui
npm run build
```

## Báo Cáo Trạng Thái 23:50 29/05/2026

Đã thực hiện:

- Hoàn thiện một phần Platform Admin cho AI Gateway:
  - Quản lý provider.
  - Quản lý LLM/embedding model profiles.
  - Nhập raw API key bằng input và lưu qua backend.
  - Cho phép cùng một key dùng cho nhiều capability/model.
- Hoàn thiện embedding gateway runtime đủ để ingest/search dùng provider thật.
- Nối ingest tài liệu vào LanceDB:
  - Parse/chunk tài liệu.
  - Embed chunk qua AI Gateway.
  - Lưu vector/chunk metadata vào LanceDB.
- Dựng Kuzu graph database:
  - Lưu Document/Element/Chunk.
  - Lưu quan hệ document/chunk/source/next/parent.
  - Query graph context theo chunk id.
- Nối ingest đồng thời vào Kuzu.
- Tạo route visualize:
  - `/api/v1/visualize/vector/search`
  - `/api/v1/visualize/vector/health`
- Tạo UI Visualization trong `/admin/documents`:
  - Tab `Vector` đã hiển thị search debugger và embedding health.
  - Tab `Graph` mới là khung rỗng.
- Cải thiện AI Gateway error handling:
  - Không còn trả lỗi mơ hồ `Vượt quá max_attempts=...`.
  - Trả lỗi cuối có ý nghĩa hơn khi provider/model/key/request fail.
- Dọn một số TODO backend theo kiến trúc:
  - `home.py` không còn là placeholder demo cũ.
  - GraphRAG pipeline files có wrapper tối thiểu.
  - Rotator không còn TODO rỗng cho các nhánh chính.
- Các kiểm tra đã pass:
  - Backend unittest.
  - Backend compileall.
  - Frontend build.

Chưa hoàn thành:

- Chưa có Graph Visualization UI thật.
- Chưa có chat GraphRAG hoàn chỉnh gọi LLM để synthesize answer từ retrieved context.
- Chưa có entity/relation extraction ngữ nghĩa sâu trong Kuzu.
- Chưa có background worker/job queue cho ingestion.
- Chưa có auth/permission production cho platform/customer/end-user.
- Chưa có document lifecycle persistence đầy đủ trong PostgreSQL cho luồng ingest chính.
- Chưa có dashboard usage/quota/alert hoàn chỉnh.

Việc nên làm tiếp:

1. Cấu hình provider + embedding/LLM profiles thật trên `/platform`.
2. Ingest tài liệu thật và kiểm tra Vector Visualization.
3. Làm Graph Visualization.
4. Hoàn thiện chat endpoint theo chuỗi GraphRAG: vector + graph retrieval, prompt, LLM synthesis, citation.
5. Thêm document lifecycle/job status và background worker.
6. Sau khi luồng đơn giản chạy thông, mới siết tenant/auth/quota production.
