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

Repo hien tai la khung dang hinh thanh thanh cac lop nen tang:

- Backend FastAPI:
  - Entry point: `app/main.py`
  - Cau hinh: `app/core/config.py`
  - API hien co: `app/api/v1/home.py`, `app/api/v1/ingest.py`, `app/api/v1/embed.py`
  - AI Gateway: `app/ai_gateway/` da co loi xoay vong key/model qua `BaseRotator`, `KeyPool`, `EmbeddingRotator`, `LLMRotator`, va `errors.py`.
  - GraphRAG: `app/graphrag/` la noi dieu phoi ingestion/query pipeline, retrieval context, prompt, va goi embedding/LLM thong qua AI Gateway.
  - Services: `app/services/` la noi chua logic nghiep vu that, hien co nhom `app/services/ingestion/` cho document pipeline.
  - Core: `app/core/` gom config, logging, security, exceptions, middleware/lifespan cua ung dung.
  - `app/models`, `app/schemas`, `app/repositories` dung de tach model/payload/persistence khi he thong lon hon.
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

## Kien Truc Lop He Thong

Tu giai doan nay, he thong duoc phat trien theo ranh gioi lop ro rang:

- `app/core/`: lop nen tang cua app. Chi chua config, logging, security, middleware, exception mapping, lifespan, dependency chung. Khong dat logic xoay vong provider, GraphRAG retrieval, hay nghiep vu tenant/chat/document vao core.
- `app/ai_gateway/`: lop dieu phoi AI provider. Tra loi cac cau hoi: dung provider nao, dung key nao, key con quota khong, co bi rate limit khong, loi nay retry/xoay/dung, ghi usage ra sao, endpoint/model nao bi khoa. Lop nay khong quyet dinh tenant co quyen chat hay khong va khong dung prompt GraphRAG.
- `app/graphrag/`: lop GraphRAG engine/pipeline. Tra loi cac cau hoi: can embedding van ban nao, lay context nao tu vector/graph, prompt can lap ghep the nao, can LLM sinh cau tra loi the nao. Lop nay goi AI Gateway de thuc thi embedding/LLM, nhung khong tu chon key, tu xu ly quota, hay tu retry provider.
- `app/services/`: lop nghiep vu san pham. Tra loi cac cau hoi: tenant/app nao dang goi, session nao, user/admin co quyen khong, luu lich su chat o dau, document lifecycle di qua cac trang thai nao, API nen tra response/schema nao. Services co the goi GraphRAG, AI Gateway, repositories, va core dependencies.
- `app/repositories/` hoac `app/db/`: lop persistence. Chi doc/ghi database, cache, vector/graph metadata theo interface ro rang. Khong chua business workflow dai.
- `app/api/v1/`: lop HTTP adapter. Router nen mong: validate request, lay dependency/auth context, goi service, tra schema. Khong dat logic xoay key, retrieval, prompt, document pipeline truc tiep trong router.

Luon giu mot chieu phu thuoc de tranh tron trach nhiem: API -> Services -> GraphRAG/AI Gateway/Repositories -> Core utilities. GraphRAG co the dung AI Gateway de goi model; AI Gateway khong phu thuoc nguoc vao GraphRAG hoac Services.

## Ranh Gioi AI Gateway

`app/ai_gateway/` la loi he thong can hoan thien dau tien de co the nap nhieu API key/model va test that qua trang admin. Khi sua lop nay, giu cac quy uoc sau:

- AI Gateway chi nhan cac `KeyConfig`/model profile da duoc service/repository nap vao. Neu key luu trong DB thi phai decrypt truoc khi dua vao gateway; gateway khong hard-code secret va khong log secret.
- `BaseRotator` giu logic chung: acquire key, goi subclass, classify error, retry same key, rotate key, cooldown, disable, abort/admin notify, va tra `RotationResult`.
- `errors.py` la bang quyet dinh trung tam cho loi provider/litellm. Khi them provider/model moi, uu tien mo rong classify error tai day thay vi rai logic try/except trong tung service.
- `KeyPool` la runtime pool tach khoi DB. Trang thai DB/Redis ve quota, cooldown, disabled, usage, endpoint lock se duoc map vao/ra pool boi service/repository rieng.
- Phai tach 2 loai pool/rotator:
  - **Embedding AI API pool**: dung cho embedding document chunks va embedding query. Dung `EmbeddingRotator`. Phai rang buoc model/dimension/index profile ro rang; khong duoc xoay sang model embedding khac chieu voi LanceDB/vector index dang dung. Ho tro batch input va batch-size theo provider.
  - **LLM AI API pool**: dung cho sinh cau tra loi, synthesis, reranking LLM neu co, tool/structured output neu sau nay can. Dung `LLMRotator`. Quan ly generation params nhu temperature, max tokens, timeout, streaming/tool calling theo request/profile.
- Khong tron key embedding va key LLM trong cung mot pool. Mot provider co the co ca embedding va LLM key, nhung runtime profile phai tach theo `capability`/`model_type`: `embedding` hoac `llm`.
- Quota/usage can duoc ghi theo toi thieu: provider, key_id, model, capability, tenant/app neu request co scope, endpoint, token/input count neu co, latency, success/error verdict.
- Endpoint/model lock la chinh sach cua Platform Admin: admin co the khoa provider, key, model, endpoint, capability, hoac tenant/app mapping. Gateway phai ton trong lock truoc khi acquire key.
- Neu gap loi cau hinh can admin can thiep, gateway phai noi len platform admin dashboard thay vi am tham retry vo han.

## Ranh Gioi GraphRAG

GraphRAG khong phai noi quan ly key/provider. GraphRAG chi nen nam cac quyet dinh lien quan chat voi tai lieu:

- Tao embedding cho document chunks va query bang cach goi embedding profile cua AI Gateway.
- Doc context tu LanceDB/vector store va Kuzu/graph store theo tenant/app/document scope.
- Lap prompt/system instruction theo cau hoi, retrieved context, chat history, policy cua app, va citation/source metadata.
- Goi LLM profile qua AI Gateway de sinh cau tra loi.
- Neu khong co context, document chua ready, hoac retrieval fail, tra trang thai ro rang cho service de API khong hallucinate.
- Prompt/retrieval/reranking/synthesis nam trong `app/graphrag/` hoac service GraphRAG chuyen biet; khong dua vao AI Gateway.

## Ranh Gioi Services

Services la noi bieu dien nghiep vu GraphRAG-aaS va la lop ket noi cac he thong con:

- Xac dinh tenant/app/session/user/admin context tu API key, JWT claim, route scope, hoac dependency.
- Kiem tra quyen: platform operator, customer admin, end user.
- Quan ly document lifecycle: upload, parse, chunk, deduplicate, index, re-index, archive/delete, job status/progress.
- Quan ly chat session/history, audit log, rate limit theo tenant/app/end user neu can.
- Chon model profile/capability duoc phep cho tenant/app roi truyen danh sach key/model hop le vao AI Gateway.
- Dinh nghia response API va loi domain ro rang cho frontend/API client.

## Platform Admin Va Cau Hinh AI

Platform Admin UI/API la noi van hanh noi bo cua GraphRAG-as-a-Service. Khi bat dau them admin cho bo xoay vong API, uu tien cac nang luc sau:

- Quan ly provider/model profile theo `capability`: `embedding` va `llm`.
- Quan ly encrypted API keys, trang thai active/cooldown/disabled, quota, endpoint/model lock, allowed tenant/app mapping.
- Xem usage, latency, success/fail, verdict/reason, key health snapshot, va canh bao can admin xu ly.
- Test call rieng cho embedding va LLM de xac minh key/model truoc khi dung cho ingestion/chat.
- Cau hinh default model profile cho ingestion embedding, query embedding, chat synthesis, va cac tac vu phu nhu rerank neu co.

Customer Admin UI khong duoc quan ly provider key noi bo cua platform. Customer Admin chi quan ly tai lieu, ingestion status, va widget/chat config trong tenant/app cua ho.

## Backend Quy Uoc

- Framework hien tai: FastAPI + Pydantic Settings.
- Cau hinh moi nen them vao `app/core/config.py` va `.env.example`; khong hard-code secret/model key.
- Khong commit `.env`, document upload, DB files, vector index, graph DB, cache, logs.
- Neu them API versioned, uu tien `app/api/v1/...` va include router trong `main.py`.
- Dung response/request schema ro rang cho API public; tranh nhan tham so quan trong bang query string tuy tien neu body/schema phu hop hon.
- API chat public khong nen nhan raw `file_path` tu client. File path noi bo phai duoc quan ly boi document service.
- Khi can chay backend local:
  - `uvicorn app.main:app --reload`
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
  - `uvicorn app.main:app --reload`
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
