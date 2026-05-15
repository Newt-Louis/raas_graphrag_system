# AGENTS.md

Huong dan nay ap dung cho toan bo repository `raas_graphrag_system`. Moi lan Codex lam viec trong du an nay, hay doc file nay truoc khi suy luan ve kien truc, dat ten API, thiet ke UI, hoac them chuc nang.

## Tong Quan San Pham

Du an nay la mot he thong **GraphRAG-as-a-Service**, khong phai mot ung dung GraphRAG don le cho mot san pham cu the.

He thong cung cap nen tang GraphRAG da-tenant cho nhieu phan mem ben ngoai tich hop. Moi phan mem/khach hang co tai lieu, cau hinh model, cau hinh giao dien chat, khoa API, vong doi tai lieu, va ngu canh truy van rieng. Khi thiet ke tinh nang moi, luon uu tien ranh gioi tenant, bao mat du lieu, kha nang mo rong API, va kha nang nhung giao dien vao san pham ben thu ba.

Ba nhom trai nghiem chinh:

1. **Chat API + embeddable chat UI cho nguoi dung cuoi cua khach hang**
   - Cho phep nguoi dung cuoi chat voi he thong dua tren bo tai lieu ma phan mem/khach hang da cung cap.
   - UI chat do he thong nay cung cap de nhung vao san pham ben ngoai, vi du iframe/script/widget.
   - Chat phai duoc rang buoc theo tenant/app/document collection, khong duoc ro ri ngu canh giua cac khach hang.

2. **Document Admin API + UI cho admin cua khach hang**
   - Cho phep admin ben khach hang upload, quan ly, cap nhat, xoa, re-index, xem trang thai xu ly va vong doi tai lieu.
   - Sau khi tai lieu duoc nap, he thong thuc hien pipeline GraphRAG: parse, chunk, extract entities/relations, embed, luu graph/vector metadata, va san sang cho API chat.
   - UI admin cua khach hang can co it nhat hai tab/phan lon:
     - Quan ly tai lieu.
     - Quan ly giao dien chat embeddable: vi tri, kich thuoc, mau sac, popup, hanh vi hien thi, kieu khung chat, v.v.

3. **Platform Admin UI cho nguoi van hanh he thong cua ta**
   - Quan ly phan mem/khach hang dang ky su dung he thong.
   - Quan ly API key, model provider/model, cau hinh LLM/embedding, quota, trang thai tenant/app.
   - Day la trang quan tri noi bo cua he thong GraphRAG-as-a-Service, khac voi UI admin cua khach hang.

## Hien Trang Source

Repo hien tai la khung ban dau:

- Backend FastAPI:
  - Entry point: `main.py`
  - Cau hinh: `app/core/config.py`
  - API hien co: `app/api/v1/home.py`, `app/api/v1/ingest.py`, `app/api/v1/embed.py`
  - Cac package `app/db`, `app/services`, `alembic`, `scripts`, `test` dang ton tai nhu thu muc nhung chua co implementation dang ke.
- Frontend Vue/Vite:
  - Thu muc: `ui/`
  - Entry point: `ui/src/main.ts`
  - Root component: `ui/src/App.vue`
  - Router: `ui/src/router/index.ts`
  - Theme variables: `ui/src/styles/theme.css`
  - Embed config composable: `ui/src/composables/useEmbedConfig.ts`
- Storage/runtime:
  - PostgreSQL va Redis trong `docker-compose.yml`.
  - Kuzu graph DB path: `data/kuzu/graph.db`.
  - LanceDB path: `data/lancedb`.
  - Data/documents duoc gitignore va khong nen commit.
- Static frontend build:
  - `ui/vite.config.ts` build Vue ra `app/static`.
  - FastAPI mount `/assets` va fallback SPA tu `app/static/index.html`.

Luu y quan trong: cac ten route hien tai nhu `feature1`, `feature2`, `Embed1View`, `Embed2View` chi la placeholder. Khi mo rong san pham, uu tien dat ten theo domain that: `chat`, `documents`, `tenants`, `apps`, `admin`, `embed`, `widget`, `ingestion`.

## Huong Kien Truc Can Giu

Thiet ke theo GraphRAG-as-a-Service da-tenant:

- Moi request quan trong can co ngu canh tenant/app ro rang, vi du `tenant_id`, `app_id`, API key, JWT claim, hoac scoped route.
- Khong viet logic mac dinh nhu the chi co mot bo tai lieu toan cuc.
- Khong tron data cua platform admin, customer admin, va end-user chat.
- API phai co ranh gioi quyen:
  - Platform operator: quan ly tenant/app/provider/model/API key.
  - Customer admin: quan ly tai lieu va cau hinh widget cua app minh.
  - End user: chi chat voi ngu canh duoc phep cua app/tenant do.
- GraphRAG pipeline nen tach service:
  - Upload/document lifecycle.
  - Parsing/chunking.
  - Entity/relation extraction.
  - Embedding/vector indexing.
  - Graph storage/query.
  - Retrieval/reranking/synthesis.
  - Job status/progress.
- Nen dat business logic trong `app/services/`, persistence trong `app/db/`, API schema/model rieng khi du an bat dau lon hon.

## Backend Quy Uoc

- Framework hien tai: FastAPI + Pydantic Settings.
- Cau hinh moi nen them vao `app/core/config.py` va `.env.example`; khong hard-code secret/model key.
- Khong commit `.env`, document upload, DB files, vector index, graph DB, cache, logs.
- Neu them API versioned, uu tien `app/api/v1/...` va include router trong `main.py`.
- Dung response/request schema ro rang cho API public; tranh nhan tham so quan trong bang query string tuy tien neu body/schema phu hop hon.
- API chat public khong nen nhan raw `file_path` tu client. File path noi bo phai duoc quan ly boi document service.
- Khi can chay backend local:
  - `uvicorn main:app --reload`
- Khi can ha tang local:
  - `docker compose up -d`

## Frontend Quy Uoc

- Frontend hien dung Vue + Vite + Pinia + Vue Router.
- `ui/vite.config.ts` proxy `/api` va `/embed` ve backend `http://localhost:8000`.
- Build frontend bang:
  - `cd ui && npm run build`
- Chay dev server bang:
  - `cd ui && npm run dev`
- UI can phan biet ro ba khu vuc:
  - Platform Admin UI noi bo.
  - Customer Admin UI cho document lifecycle va chat widget builder.
  - Embeddable Chat UI cho end user.
- Chat widget builder can luu cau hinh theo tenant/app, khong chi apply theme client-side tam thoi.
- Embed UI phai than thien voi iframe/script nhung: kich thuoc on dinh, theming qua config, postMessage co validate origin khi co auth/security that.

## API Domain De Xuat

Khi thay placeholder, uu tien cac namespace sau:

- `/api/v1/platform/...` cho admin noi bo cua he thong.
- `/api/v1/apps/...` hoac `/api/v1/tenants/...` cho dang ky va cau hinh phan mem khach hang.
- `/api/v1/documents/...` cho upload, lifecycle, status, re-index.
- `/api/v1/chat/...` cho query/chat completion co ngu canh tenant/app.
- `/api/v1/widget-config/...` cho cau hinh giao dien chat.
- `/embed/chat/...` cho giao dien chat embeddable.
- `/admin/...` hoac route SPA tuong ung cho UI quan tri.

Day chi la de xuat dinh huong; neu source da co chuan moi trong tuong lai, uu tien chuan dang hien huu hon file nay.

## Data Va Storage

- PostgreSQL: metadata he thong, tenant/app, users/admins, API keys, document metadata, job status, widget config, audit log.
- Kuzu: graph entities/relations phuc vu GraphRAG.
- LanceDB: vector embeddings/chunks/retrieval index.
- Redis: cache, queue/job coordination, rate limit, session tam thoi neu can.
- `data/` la runtime data, khong commit.
- Moi ban ghi document/chunk/entity/vector nen co tenant/app/document scope ro rang.

## Bao Mat Va Tich Hop

- API key/JWT phai duoc hash/luu an toan khi di vao production; khong log secret.
- CORS hien dang mo `["*"]` de tien embed/dev. Khi lam production, can scoped origins theo tenant/app.
- Embed/postMessage phai tinh toi validate origin, allowed domains, va khong tin raw event data.
- Admin cua khach hang chi duoc xem/sua tai lieu va widget config cua app/tenant minh.
- End-user chat API can rate limit, audit, va guardrails phu hop vi day la API public-facing.

## Chat/GraphRAG Behavior

- Chat response nen dua tren retrieved context tu tai lieu cua dung tenant/app.
- Neu khong co ngu canh hoac tai lieu chua san sang, API nen tra trang thai/loi ro rang thay vi hallucinate.
- Nen luu citation/source metadata de UI co the hien thi nguon.
- Document lifecycle can co trang thai nhu uploaded, parsing, indexing, ready, failed, archived/deleted.
- Pipeline nen idempotent o cac buoc de co the retry job.

## Kiem Tra Va Chat Luong

Hien repo chua co test runner ro rang cho backend. Khi them logic co rui ro, nen them test tuong ung trong `test/` hoac thu muc test chuan cua framework duoc chon.

Cac lenh kiem tra co san/hop ly:

- Frontend type check/build:
  - `cd ui && npm run build`
- Backend smoke run:
  - `uvicorn main:app --reload`
- Ha tang local:
  - `docker compose up -d`

Neu them tool moi nhu pytest, ruff, alembic migrations, hay task queue, cap nhat file nay va README/script lien quan.

## Quy Uoc Lam Viec Cho Codex

- Luon coi day la san pham platform/API-first, khong phai demo chatbot don tenant.
- Truoc khi sua kien truc, quet source hien tai va giu pattern dang co neu hop ly.
- Khong overwrite thay doi nguoi dung da lam.
- Khi tao file/chuc nang moi, dat ten theo domain GraphRAG-aaS that thay vi `feature1/feature2`.
- Khi sua frontend, dam bao route/component ton tai that va build duoc.
- Khi sua backend, dam bao router prefix/path hop le; tranh loi path thieu dau `/`.
- Khong dua secret vao code, log, fixture, hoac AGENTS.md.
- Neu yeu cau lien quan OpenAI/API/model moi nhat, phai kiem tra tai lieu chinh thuc truoc khi ket luan.

