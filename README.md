# RaaS GraphRAG System

Nền tảng GraphRAG-as-a-Service đa tenant cho phép phần mềm bên ngoài nạp tài liệu, cấu hình AI provider/model, trực quan hóa vector và knowledge graph, rồi nhúng giao diện chat hỏi đáp theo tài liệu.

## Năng Lực Hiện Có

- Platform Admin quản lý provider, API key, embedding profile và LLM profile.
- Ingest tài liệu: lưu registry PostgreSQL, parse, chunk, embed qua Gemini, index LanceDB và ghi graph Kuzu.
- Chunking strategy theo request: semantic grouping bằng sentence embedding, sliding window theo token có overlap, hoặc parent-child với child index và parent context expansion khi retrieval.
- GraphRAG semantic extraction: dùng LLM trích xuất entity/relation theo ontology allowlist.
- Document Admin: upload, danh sách tài liệu, xóa tài liệu và mở Visualization.
- Vector Visualization: search debugger, cosine similarity, distance, metadata và embedding health.
- Graph Visualization: payload từ Kuzu và biểu đồ Cytoscape.js cho structure graph lẫn semantic graph.
- Embeddable Chat: retrieval embedding-first, mở rộng context bằng graph, policy grounded answer/social/refusal, citation và SSE streaming từng ký tự.

## Kiến Trúc

```text
Vue/Vite UI
  -> FastAPI /api/v1
    -> Services
      -> AI Gateway
        -> Gemini embedding adapter
        -> LiteLLM LLM rotation pool
      -> GraphRAG
        -> LanceDB vector index
        -> Kuzu structure + semantic graph
      -> PostgreSQL metadata
```

Redis đã có trong hạ tầng local để phục vụ cache/runtime coordination về sau. Auth, rate limit và job queue production vẫn chưa hoàn thiện.

## Yêu Cầu

- Python 3.13 hoặc phiên bản tương thích với `requirements.txt`
- Node.js `^20.19.0` hoặc `>=22.12.0`
- Docker + Docker Compose
- PostgreSQL và Redis từ `docker-compose.yml`

## Cài Đặt

Backend:

```bash
python -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
docker compose up -d
.venv/bin/alembic upgrade head
```

Frontend:

```bash
cd ui
npm install
```

Runtime data nằm trong `data/documents`, `data/lancedb` và `data/kuzu/graph.db`. Không commit các thư mục này.

## Chạy Dev

Backend:

```bash
. .venv/bin/activate
uvicorn app.main:app --reload
```

Frontend:

```bash
cd ui
npm run dev
```

- Backend: `http://localhost:8000`
- Frontend: `http://localhost:5173`
- Vite proxy `/api` và `/embed` về backend `http://localhost:8000`

## Cấu Hình AI Bắt Buộc

Trước khi ingest hoặc chat, mở `http://localhost:5173/platform` và cấu hình:

1. Tạo provider embedding Gemini, ví dụ `code=gemini`.
2. Nhập API key thật.
3. Tạo embedding model profile và khai báo đúng `embedding_dimensions`.
4. Tạo LLM model profile dùng cho semantic extraction và chat synthesis.
5. Đảm bảo provider, key và profile đang enabled, không bị locked.

Embedding runtime dùng profile Gemini mới nhất trực tiếp, không xoay key. LLM runtime dùng pool riêng qua LiteLLM. Document embedding và query embedding phải dùng profile tương thích cùng chiều vector.

## Luồng Sử Dụng

1. Vào `/platform` cấu hình provider, key và model profile.
2. Vào `/admin/documents`, upload tài liệu.
3. Pipeline lưu document registry, parse/chunk theo strategy đã chọn, index LanceDB, ghi graph structure Kuzu và tùy chọn semantic extraction qua LLM. Semantic chunking và semantic graph extraction là hai bước độc lập.
4. Mở Visualization:
   - Tab `Vector`: kiểm tra search debugger và embedding health.
   - Tab `Graph`: kiểm tra graph Cytoscape theo document.
5. Vào `/embed/chat` để chat theo scope `tenant_id`, `app_id`, `collection_id`.

Chat dùng workflow embedding-first:

1. Hard-block nội dung bị policy chặn ngay tại backend.
2. Embed câu hỏi và search LanceDB.
3. Chỉ giữ context đạt similarity threshold cấu hình backend.
4. Mở rộng context qua Kuzu khi có semantic graph.
5. Gọi một LLM để chọn `grounded_answer`, `social` hoặc `refuse`.
6. Validate policy và citation trước khi trả kết quả.
7. Stream answer đã validate xuống UI qua SSE.

## SSE Chat

UI `/embed/chat` gọi:

```text
POST /api/v1/chat/completions/stream
Content-Type: application/json
Accept: text/event-stream
```

Request body:

```json
{
  "tenant_id": "tenant-a",
  "app_id": "app-a",
  "collection_id": null,
  "session_id": "optional-session-id",
  "message": "Câu hỏi của người dùng",
  "history": []
}
```

Response SSE:

```text
event: metadata
data: {"strategy":"vector_semantic_graph","response_type":"grounded_answer","citations":[]}

event: delta
data: {"text":"K"}

event: delta
data: {"text":"ế"}

event: done
data: {"finish_reason":"stop"}
```

`metadata` còn chứa scope và usage. Mỗi `delta` chứa một ký tự. Backend chỉ bắt đầu stream sau khi answer đã đi qua retrieval, policy parser và citation validation; đây không phải passthrough token thô trực tiếp từ provider.

Endpoint JSON cũ vẫn được giữ để tương thích:

```text
POST /api/v1/chat/completions
```

## Route Chính

UI:

- `/platform`: Platform Admin
- `/admin/documents`: Document Admin + Visualization
- `/admin/widget`: Widget builder
- `/embed/chat`: Embeddable chat UI

API:

- `POST /api/v1/ingest`
- `GET /api/v1/documents`
- `DELETE /api/v1/documents/{document_id}`
- `POST /api/v1/visualize/vector/search`
- `POST /api/v1/visualize/vector/health`
- `POST /api/v1/visualize/graph`
- `POST /api/v1/chat/completions`
- `POST /api/v1/chat/completions/stream`
- `POST /api/v1/chat/retrieve`
- `/api/v1/platform/ai/...`

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

## Phần Còn Lại Cho Production

- Auth và permission boundary cho Platform Admin, Customer Admin và End User.
- Rate limit, audit log và quota enforcement cho public chat API.
- Persistence chat session/history.
- Job queue/background worker cho ingestion.
- Redis rehydrate/reconcile runtime đầy đủ.
- CORS, allowed origins và `postMessage` hardening cho widget nhúng.
- Community detection, community summaries và reranking nâng cao.
