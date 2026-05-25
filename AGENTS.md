# AGENTS.md

Hướng dẫn này áp dụng cho toàn bộ repository `raas_graphrag_system`. Mỗi lần Codex làm việc trong dự án này, hãy đọc file này trước khi suy luận về kiến trúc, đặt tên API, thiết kế UI, hoặc thêm chức năng.

## Tổng Quan Sản Phẩm

Dự án này là một hệ thống **GraphRAG-as-a-Service**, không phải một ứng dụng GraphRAG đơn lẻ cho một sản phẩm cụ thể.

Hệ thống cung cấp nền tảng GraphRAG đa tenant cho nhiều phần mềm bên ngoài tích hợp. Mỗi phần mềm/khách hàng có tài liệu, cấu hình model, cấu hình giao diện chat, khóa API, vòng đời tài liệu, quota, và ngữ cảnh truy vấn riêng. Khi thiết kế tính năng mới, luôn ưu tiên ranh giới tenant, bảo mật dữ liệu, khả năng mở rộng API, khả năng vận hành nhiều provider/model, và khả năng nhúng giao diện vào sản phẩm bên thứ ba.

Ba nhóm trải nghiệm chính:

1. **Chat API + embeddable chat UI cho người dùng cuối của khách hàng**
   - Cho phép người dùng cuối chat với hệ thống dựa trên bộ tài liệu mà phần mềm/khách hàng đã cung cấp.
   - UI chat do hệ thống này cung cấp để nhúng vào sản phẩm bên ngoài, ví dụ iframe/script/widget.
   - Chat phải được ràng buộc theo tenant/app/document collection, không được rò rỉ ngữ cảnh giữa các khách hàng.

2. **Document Admin API + UI cho admin của khách hàng**
   - Cho phép admin bên khách hàng upload, quản lý, cập nhật, xóa, re-index, xem trạng thái xử lý và vòng đời tài liệu.
   - Sau khi tài liệu được nạp, hệ thống thực hiện pipeline GraphRAG: parse, chunk, trích xuất entities/relations, embed, lưu graph/vector metadata, và sẵn sàng cho API chat.
   - UI admin của khách hàng cần có ít nhất hai tab/phần lớn:
     - Quản lý tài liệu.
     - Quản lý giao diện chat embeddable: vị trí, kích thước, màu sắc, popup, hành vi hiển thị, kiểu khung chat, v.v.

3. **Platform Admin UI cho người vận hành hệ thống của ta**
   - Quản lý tenant/app đang sử dụng hệ thống.
   - Quản lý provider/model, API key, endpoint, pool xoay vòng, quota, trạng thái tenant/app, và cảnh báo vận hành.
   - Đây là trang quản trị nội bộ của hệ thống GraphRAG-as-a-Service, khác với UI admin của khách hàng.

## Hiện Trạng Source

Repo hiện tại đã tách rõ hơn thành các lõi nền tảng:

- Backend FastAPI:
  - Entry point: `app/main.py`.
  - Cấu hình: `app/core/config.py`.
  - Router hiện có được auto-include từ `app/api/v1/*.py` với prefix `/api/v1`.
  - API hiện có: `app/api/v1/home.py`, `app/api/v1/ingest.py`, `app/api/v1/chat.py`, `app/api/v1/embed.py`.
  - `home.py` và các route `feature1/feature2` trong embed vẫn là placeholder; khi mở rộng, ưu tiên tên domain thật.
- AI Gateway:
  - Thư mục: `app/ai_gateway/`.
  - Đã có lõi xoay vòng API qua `AIGateway`, `BaseRotator`, `KeyPool`, `EmbeddingRotator`, `LLMRotator`, `ModelProfile`, `GatewayRequestContext`, `UsageRecord`, và `errors.py`.
  - Đây là lõi cần hoàn thiện trước để có model embedding/LLM thật phục vụ test GraphRAG.
- GraphRAG:
  - Thư mục: `app/graphrag/`.
  - `GraphRAGAIClient` đã tồn tại để GraphRAG gọi embedding/LLM qua AI Gateway.
  - `engine.py`, `ingestion_pipeline.py`, và `query_pipeline.py` hiện vẫn là placeholder rỗng; chưa được coi là implementation GraphRAG hoàn chỉnh.
- Services:
  - `app/services/ingestion/`: document parsing/chunking/deduplication/fanout records.
  - `app/services/vector/`: embedding local hashing cho dev/test, LanceDB vector store, in-memory vector store cho unit test.
  - `app/services/retrieval/`: retrieval orchestrator hiện đang vector-only để sau này gắn hybrid vector + graph.
- Database/model:
  - `app/db/base.py`, `app/db/session.py`: SQLAlchemy base/session.
  - `app/models/platform.py`: platform users, tenants, customer apps.
  - `app/models/documents.py`: documents và ingestion jobs.
  - `app/models/ai_gateway.py`: provider, API key, model catalog, LLM rotation pools/profiles, embedding rotation pools/profiles, usage events.
  - Chưa thấy migration Alembic hoàn chỉnh tương ứng với toàn bộ model mới; nếu thêm/sửa DB schema thì cần xử lý migration thay vì chỉ sửa model.
- Core:
  - `app/core/config.py` đã có config DB, path runtime, LanceDB/vector, embedding local, CORS.
  - `app/core/lifespan.py`, `logging.py`, `security.py`, `exceptions.py` hiện còn rỗng hoặc rất nhẹ; không giả định chúng đã có middleware/auth/logging production.
- Frontend Vue/Vite:
  - Thư mục: `ui/`.
  - Entry point: `ui/src/main.ts`.
  - Root component: `ui/src/App.vue`.
  - Router: `ui/src/router/index.ts`.
  - Theme variables: `ui/src/styles/theme.css`.
  - Embed config composable: `ui/src/composables/useEmbedConfig.ts`.
- Storage/runtime:
  - PostgreSQL và Redis trong `docker-compose.yml`.
  - Kuzu graph DB path: `data/kuzu/graph.db`.
  - LanceDB path: `data/lancedb`.
  - Data/documents, graph DB, vector DB, cache, logs là runtime data và không nên commit.
- Static frontend build:
  - `ui/vite.config.ts` build Vue ra `app/static`.
  - FastAPI mount `/assets` và fallback SPA từ `app/static/index.html`.

Lưu ý quan trọng: các tên route cũ như `feature1`, `feature2`, hoặc code demo trong `home.py` chỉ là placeholder. Khi mở rộng sản phẩm, ưu tiên đặt tên theo domain thật: `chat`, `documents`, `tenants`, `apps`, `platform`, `admin`, `embed`, `widget`, `ingestion`, `ai-gateway`, `model-profiles`.

## Ưu Tiên Kiến Trúc Hiện Tại

Giai đoạn hiện tại ưu tiên hoàn thiện **lõi API xoay vòng model** trước khi dựng sâu GraphRAG. Lý do: nếu chưa có cơ chế gọi embedding/LLM thật, kiểm tra GraphRAG sẽ chỉ là kiểm tra giả lập và không phản ánh được quota, lỗi provider, model dimension, latency, và fallback runtime.

Thứ tự ưu tiên hợp lý:

1. Hoàn thiện AI Gateway cho hai capability tách biệt: `embedding` và `llm`.
2. Hoàn thiện Platform Admin/API để cấu hình provider, model, API key, endpoint, pool, lock, quota, usage, và test call.
3. Nối ingestion/query embedding vào embedding gateway theo profile đúng chiều vector.
4. Nối chat synthesis/rerank/tool/structured output vào LLM gateway.
5. Sau khi có gateway test được, mới mở rộng GraphRAG engine, graph retrieval, reranking, synthesis, citation, và hybrid retrieval.

## Hướng Kiến Trúc Cần Giữ

Thiết kế theo GraphRAG-as-a-Service đa tenant:

- Mỗi request quan trọng cần có ngữ cảnh tenant/app rõ ràng, ví dụ `tenant_id`, `app_id`, API key, JWT claim, hoặc scoped route.
- Không viết logic mặc định như thể chỉ có một bộ tài liệu toàn cục.
- Không trộn data của platform admin, customer admin, và end-user chat.
- API phải có ranh giới quyền:
  - Platform operator: quản lý tenant/app/provider/model/API key/pool/quota/lock.
  - Customer admin: quản lý tài liệu và cấu hình widget của app mình.
  - End user: chỉ chat với ngữ cảnh được phép của app/tenant đó.
- GraphRAG pipeline nên tách service:
  - Upload/document lifecycle.
  - Parsing/chunking.
  - Entity/relation extraction.
  - Embedding/vector indexing.
  - Graph storage/query.
  - Retrieval/reranking/synthesis.
  - Job status/progress.
- Business logic nên nằm trong `app/services/`, persistence trong `app/db/`/`app/repositories/`, API schema/model riêng khi dự án lớn hơn.

## Kiến Trúc Lớp Hệ Thống

Từ giai đoạn này, hệ thống được phát triển theo ranh giới lớp rõ ràng:

- `app/core/`: lớp nền tảng của app. Chỉ chứa config, logging, security, middleware, exception mapping, lifespan, dependency chung. Không đặt logic xoay vòng provider, GraphRAG retrieval, hay nghiệp vụ tenant/chat/document vào core.
- `app/ai_gateway/`: lớp điều phối AI provider/model/key. Trả lời các câu hỏi: dùng provider nào, dùng key nào, key còn quota không, có bị rate limit không, lỗi này retry/xoay/dừng, ghi usage ra sao, endpoint/model nào bị khóa. Lớp này không quyết định tenant có quyền chat hay không và không dựng prompt GraphRAG.
- `app/graphrag/`: lớp GraphRAG engine/pipeline. Trả lời các câu hỏi: cần embedding văn bản nào, lấy context nào từ vector/graph, prompt cần lắp ghép thế nào, cần LLM sinh câu trả lời thế nào. Lớp này gọi AI Gateway để thực thi embedding/LLM, nhưng không tự chọn key, tự xử lý quota, hay tự retry provider.
- `app/services/`: lớp nghiệp vụ sản phẩm. Trả lời các câu hỏi: tenant/app nào đang gọi, session nào, user/admin có quyền không, lưu lịch sử chat ở đâu, document lifecycle đi qua các trạng thái nào, API nên trả response/schema nào. Services có thể gọi GraphRAG, AI Gateway, repositories, và core dependencies.
- `app/repositories/` hoặc `app/db/`: lớp persistence. Chỉ đọc/ghi database, cache, vector/graph metadata theo interface rõ ràng. Không chứa workflow nghiệp vụ dài.
- `app/api/v1/`: lớp HTTP adapter. Router nên mỏng: validate request, lấy dependency/auth context, gọi service, trả schema. Không đặt logic xoay key, retrieval, prompt, document pipeline trực tiếp trong router nếu logic đó bắt đầu lớn.

Luôn giữ chiều phụ thuộc rõ để tránh trộn trách nhiệm: API -> Services -> GraphRAG/AI Gateway/Repositories -> Core utilities. GraphRAG có thể dùng AI Gateway để gọi model; AI Gateway không phụ thuộc ngược vào GraphRAG hoặc Services.

## Ranh Giới AI Gateway

`app/ai_gateway/` là lõi hệ thống cần hoàn thiện đầu tiên để có thể nạp nhiều API key/model và test thật qua trang admin. Khi sửa lớp này, giữ các quy ước sau:

- AI Gateway chỉ nhận các `ModelProfile`/`KeyConfig` đã được service/repository nạp vào. Nếu key lưu trong DB thì phải decrypt trước khi đưa vào gateway; gateway không hard-code secret và không log secret.
- `AIGateway` là facade duy nhất cho GraphRAG/Services gọi model. Tránh để GraphRAG hoặc router gọi trực tiếp `litellm`, `EmbeddingRotator`, hoặc `LLMRotator` nếu không phải test cấp thấp.
- `BaseRotator` giữ logic chung: acquire key, gọi subclass, classify error, retry same key, rotate key, cooldown, disable, abort/admin notify, và trả `RotationResult`.
- `errors.py` là bảng quyết định trung tâm cho lỗi provider/litellm. Khi thêm provider/model mới, ưu tiên mở rộng classify error tại đây thay vì rải logic try/except trong từng service.
- `KeyPool` là runtime pool tách khỏi DB. Trạng thái DB/Redis về quota, cooldown, disabled, usage, endpoint lock sẽ được map vào/ra pool bởi service/repository riêng.
- Phải tách 2 loại pool/rotator:
  - **Embedding AI API pool**: dùng cho embedding document chunks và embedding query. Dùng `EmbeddingRotator`. Phải ràng buộc model/dimension/index profile rõ ràng; không được xoay sang model embedding khác chiều với LanceDB/vector index đang dùng. Hỗ trợ batch input và batch-size theo provider.
  - **LLM AI API pool**: dùng cho sinh câu trả lời, synthesis, reranking LLM nếu có, tool/structured output nếu sau này cần. Dùng `LLMRotator`. Quản lý generation params như temperature, max tokens, timeout, streaming/tool calling theo request/profile.
- Không trộn key embedding và key LLM trong cùng một pool. Một provider có thể có cả embedding và LLM key, nhưng runtime profile phải tách theo `capability`/`model_type`: `embedding` hoặc `llm`.
- DB model hiện đã tách `llm_rotation_pools`/`llm_model_profiles` và `embedding_rotation_pools`/`embedding_model_profiles`; khi thêm API/admin, không gộp hai nhóm này lại vì cấu hình và rủi ro khác nhau.
- Quota/usage cần được ghi theo tối thiểu: provider, key_id, model, capability, tenant/app nếu request có scope, endpoint, input/token count nếu có, latency, success/error verdict.
- Endpoint/model lock là chính sách của Platform Admin: admin có thể khóa provider, key, model, endpoint, capability, hoặc tenant/app mapping. Gateway phải tôn trọng lock trước khi acquire key.
- Nếu gặp lỗi cấu hình cần admin can thiệp, gateway phải nổi lên platform admin dashboard thay vì âm thầm retry vô hạn.
- `health_snapshot()` không được trả secret. Các API/debug endpoint tương lai cũng không được expose `api_key` hoặc `encrypted_api_key`.

## Ranh Giới GraphRAG

GraphRAG không phải nơi quản lý key/provider. GraphRAG chỉ nên nắm các quyết định liên quan chat với tài liệu:

- Tạo embedding cho document chunks và query bằng cách gọi embedding profile của AI Gateway.
- Đọc context từ LanceDB/vector store và Kuzu/graph store theo tenant/app/document scope.
- Lắp prompt/system instruction theo câu hỏi, retrieved context, chat history, policy của app, và citation/source metadata.
- Gọi LLM profile qua AI Gateway để sinh câu trả lời.
- Nếu không có context, document chưa ready, hoặc retrieval fail, trả trạng thái rõ ràng cho service để API không hallucinate.
- Prompt/retrieval/reranking/synthesis nằm trong `app/graphrag/` hoặc service GraphRAG chuyên biệt; không đưa vào AI Gateway.
- Hiện `app/graphrag/engine.py`, `ingestion_pipeline.py`, `query_pipeline.py` còn rỗng. Không ghi tài liệu như thể các pipeline này đã hoàn chỉnh.

## Ranh Giới Services

Services là nơi biểu diễn nghiệp vụ GraphRAG-aaS và là lớp kết nối các hệ thống con:

- Xác định tenant/app/session/user/admin context từ API key, JWT claim, route scope, hoặc dependency.
- Kiểm tra quyền: platform operator, customer admin, end user.
- Quản lý document lifecycle: upload, parse, chunk, deduplicate, index, re-index, archive/delete, job status/progress.
- Quản lý chat session/history, audit log, rate limit theo tenant/app/end user nếu cần.
- Chọn model profile/capability được phép cho tenant/app rồi truyền danh sách key/model hợp lệ vào AI Gateway.
- Định nghĩa response API và lỗi domain rõ ràng cho frontend/API client.

## Vector Retrieval Và Hybrid Sau Này

Hiện tại retrieval service đang vector-only:

- `app/services/vector/embeddings.py` có `HashingTextEmbeddingService` để dev/test không cần secret. Đây không phải embedding production.
- `app/services/vector/store.py` có `LanceDBVectorStore` và `InMemoryVectorStore`.
- `app/services/retrieval/orchestrator.py` là điểm hứng retrieval trước khi synthesis. Chat API nên gọi orchestrator/service, không gọi thẳng LanceDB.
- Khi chuyển sang embedding provider thật, ingest embedding và query embedding phải dùng cùng embedding profile hoặc profile tương thích dimension với index.
- Khi thêm GraphDB/Kuzu retrieval, mở rộng orchestrator để hợp nhất kết quả vector + graph, rerank, và trả citation/source metadata. Không bẻ chat API sang gọi trực tiếp hai DB.

## Platform Admin Và Cấu Hình AI

Platform Admin UI/API là nơi vận hành nội bộ của GraphRAG-as-a-Service. Khi bắt đầu thêm admin cho bộ xoay vòng API, ưu tiên các năng lực sau:

- Quản lý provider/model catalog theo `capability`: `embedding` và `llm`.
- Quản lý encrypted API keys, trạng thái active/cooldown/disabled, quota, endpoint/model lock, allowed tenant/app mapping.
- Quản lý LLM rotation pools và embedding rotation pools tách biệt, có default pool theo platform/tenant/app.
- Xem usage, latency, success/fail, verdict/reason, key health snapshot, và cảnh báo cần admin xử lý.
- Test call riêng cho embedding và LLM để xác minh key/model trước khi dùng cho ingestion/chat.
- Cấu hình default model profile cho ingestion embedding, query embedding, chat synthesis, và các tác vụ phụ như rerank nếu có.

Customer Admin UI không được quản lý provider key nội bộ của platform. Customer Admin chỉ quản lý tài liệu, ingestion status, và widget/chat config trong tenant/app của họ.

Hiện trạng Platform Admin AI UI:

- `ui/src/views/PlatformAdminView.vue` chỉ là container/layout cho màn hình quản trị AI nội bộ; các page con nằm trong `ui/src/pages/admin_system/`.
- `ui/src/pages/admin_system/ProvidersPage.vue` quản lý bảng `ai_providers` và gọi API thật dưới `/api/v1/platform/ai/providers`.
- `ui/src/pages/admin_system/ModelProfilesPage.vue` là trang quản lý LLM model profile hiện tại; không dựng form riêng để admin tự tạo pool runtime thủ công trên UI nếu chưa có thiết kế rõ.
- Raw provider API key phải lưu qua bảng `ai_api_keys` bằng backend API, backend hash key vào `key_hash`, encrypt key vào `encrypted_api_key`, và frontend chỉ được nhận preview đã mask.
- Không nhập raw API key vào `llm_model_profiles.api_key_id`. Cột `api_key_id` trong `llm_model_profiles` là khóa ngoại tới `ai_api_keys.id`; `provider_id` là khóa ngoại tới `ai_providers.id`.
- Từ migration `202605250001`, model profile và pool runtime đã tách lớp nhưng không thêm bảng entry: `llm_model_profiles`/`embedding_model_profiles` chỉ giữ cấu hình masterdata của model/key/provider; `llm_rotation_pools`/`embedding_rotation_pools` là bảng runtime trực tiếp, mỗi dòng pool trỏ tới một profile qua `profile_id` và giữ `rotation_order`, `weight`, `current_position`, `is_enabled`, `is_locked`, `lock_reason`, `today_quota_exhausted`, `quota_exhausted_until`, `rate_limited_until`, `last_used_at`, `daily_request_count`, `minute_request_count`, `success_count`, `failure_count`.
- `current_position` trong bảng pool là marker 0/1 cho biết dòng runtime nào đang tới lượt gọi tiếp theo; vòng xoay đi theo `rotation_order`.
- Redis runtime sau này hydrate từ các bảng `*_rotation_pools` join sang `*_model_profiles`. Khi cooldown/quota hết hạn hoặc Redis bị flush/restart, worker/lifespan/service cần rehydrate hoặc reconcile Redis từ PostgreSQL theo bảng pool runtime.
- `status` trên danh sách model profile/API key/provider chỉ là trạng thái vận hành để hiển thị active/disabled/locked/cooldown; thao tác đổi trạng thái phải đi qua nút action và endpoint backend, không biến status thành ô chọn tự do trong bảng.

## Backend Quy Ước

- Framework hiện tại: FastAPI + Pydantic Settings + SQLAlchemy.
- Cấu hình mới nên thêm vào `app/core/config.py` và `.env.example`; không hard-code secret/model key.
- Không commit `.env`, document upload, DB files, vector index, graph DB, cache, logs, hoặc `__pycache__`.
- Nếu thêm API versioned, ưu tiên `app/api/v1/...`; hiện `app/main.py` auto-include router từ `app/api/v1/*.py`.
- Router prefix phải bắt đầu bằng `/`. Tránh include trùng router theo cả cách manual và auto.
- Dùng response/request schema rõ ràng cho API public; tránh nhận tham số quan trọng bằng query string tùy tiện nếu body/schema phù hợp hơn.
- API chat public không nên nhận raw `file_path` từ client. File path nội bộ phải được quản lý bởi document service.
- Khi thêm/sửa SQLAlchemy model, cập nhật migration Alembic hoặc ghi rõ migration chưa có. Không chỉ sửa model rồi coi như DB đã sẵn sàng.
- Khi cần chạy backend local:
  - `uvicorn app.main:app --reload`
- Khi cần hạ tầng local:
  - `docker compose up -d`

## Frontend Quy Ước

- Frontend hiện dùng Vue + Vite + Pinia + Vue Router.
- `ui/vite.config.ts` proxy `/api` và `/embed` về backend `http://localhost:8000`.
- Build frontend bằng:
  - `cd ui && npm run build`
- Chạy dev server bằng:
  - `cd ui && npm run dev`
- UI cần phân biệt rõ ba khu vực:
  - Platform Admin UI nội bộ.
  - Customer Admin UI cho document lifecycle và chat widget builder.
  - Embeddable Chat UI cho end user.
- Phần Platform Admin cho AI Gateway cần tách màn hình/luồng cho embedding profiles và LLM profiles.
- Chat widget builder cần lưu cấu hình theo tenant/app, không chỉ apply theme client-side tạm thời.
- Embed UI phải thân thiện với iframe/script nhúng: kích thước ổn định, theming qua config, postMessage có validate origin khi có auth/security thật.

## API Domain Đề Xuất

Khi thay placeholder, ưu tiên các namespace sau:

- `/api/v1/platform/...` cho admin nội bộ của hệ thống.
- `/api/v1/platform/ai/...` hoặc `/api/v1/ai-gateway/...` cho provider/model/key/pool/test-call/usage nội bộ.
- `/api/v1/apps/...` hoặc `/api/v1/tenants/...` cho đăng ký và cấu hình phần mềm khách hàng.
- `/api/v1/documents/...` cho upload, lifecycle, status, re-index.
- `/api/v1/chat/...` cho query/chat completion có ngữ cảnh tenant/app.
- `/api/v1/widget-config/...` cho cấu hình giao diện chat.
- `/embed/chat/...` cho giao diện chat embeddable.
- `/admin/...` hoặc route SPA tương ứng cho UI quản trị.

Đây chỉ là định hướng; nếu source đã có chuẩn mới trong tương lai, ưu tiên chuẩn hiện hữu hơn file này.

## Data Và Storage

- PostgreSQL: metadata hệ thống, tenant/app, users/admins, API keys, provider/model catalog, rotation pools/profiles, usage events, document metadata, job status, widget config, audit log.
- Kuzu: graph entities/relations phục vụ GraphRAG.
- LanceDB: vector embeddings/chunks/retrieval index.
- Redis: cache, queue/job coordination, rate limit, session tạm thời nếu cần.
- `data/` là runtime data, không commit.
- Mỗi bản ghi document/chunk/entity/vector/usage nên có tenant/app/document hoặc endpoint scope rõ ràng khi phù hợp.

## Bảo Mật Và Tích Hợp

- API key/JWT phải được hash/lưu an toàn khi đi vào production; không log secret.
- API key provider phải được mã hóa khi lưu DB. Chỉ decrypt ở service/repository trước khi đưa vào `KeyConfig`.
- Không trả `api_key`, `encrypted_api_key`, hoặc secret trong health snapshot, API response, log, fixture, hoặc AGENTS.md.
- CORS hiện đang mở `["*"]` để tiện embed/dev. Khi làm production, cần scoped origins theo tenant/app.
- Embed/postMessage phải tính tới validate origin, allowed domains, và không tin raw event data.
- Admin của khách hàng chỉ được xem/sửa tài liệu và widget config của app/tenant mình.
- End-user chat API cần rate limit, audit, và guardrails phù hợp vì đây là API public-facing.

## Chat/GraphRAG Behavior

- Chat response nên dựa trên retrieved context từ tài liệu của đúng tenant/app.
- Nếu không có ngữ cảnh, tài liệu chưa sẵn sàng, hoặc model gateway không có profile/key khả dụng, API nên trả trạng thái/lỗi rõ ràng thay vì hallucinate.
- Nên lưu citation/source metadata để UI có thể hiển thị nguồn.
- Document lifecycle cần có trạng thái như uploaded, parsing, indexing, ready, failed, archived/deleted.
- Pipeline nên idempotent ở các bước để có thể retry job.

## Kiểm Tra Và Chất Lượng

Test hiện có dùng `unittest` trong thư mục `test/`.

Các lệnh kiểm tra có sẵn/hợp lý:

- Backend unit tests:
  - `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s test`
- Frontend type check/build:
  - `cd ui && npm run build`
- Backend smoke run:
  - `uvicorn app.main:app --reload`
- Hạ tầng local:
  - `docker compose up -d`

Khi thêm logic có rủi ro, thêm test tương ứng trong `test/`. Các test AI Gateway nên ưu tiên fake/mock rotator hoặc test logic pool/classification trước; chỉ chạy provider thật khi có cấu hình rõ và không làm lộ secret.

Nếu thêm tool mới như pytest, ruff, alembic migrations, hay task queue, cập nhật file này và README/script liên quan.

## Quy Ước Làm Việc Cho Codex

- Luôn coi đây là sản phẩm platform/API-first, không phải demo chatbot đơn tenant.
- Trước khi sửa kiến trúc, quét source hiện tại và giữ pattern đang có nếu hợp lý.
- Không overwrite thay đổi người dùng đã làm.
- Khi tạo file/chức năng mới, đặt tên theo domain GraphRAG-aaS thật thay vì `feature1/feature2`.
- Khi sửa frontend, đảm bảo route/component tồn tại thật và build được.
- Khi sửa backend, đảm bảo router prefix/path hợp lệ; tránh lỗi path thiếu dấu `/`.
- Không đưa secret vào code, log, fixture, hoặc AGENTS.md.
- Nếu yêu cầu liên quan OpenAI/API/model mới nhất, phải kiểm tra tài liệu chính thức trước khi kết luận.
